"""
Candidate-decision correction agent.

This is the default qwen3:4b-friendly path: rules generate concrete patches,
the model only chooses whether to apply one.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from src.agent.candidates import CandidateGenerator, CorrectionCandidate
from src.agent.loop import AgentResult
from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.core.progress import ProgressTracker
from src.core.text import TextDoc
from src.detector.pipeline import DetectorPipeline
from src.model.client import ChatMessage, OpenAICompatibleClient
from src.model.protocol import ToolSpec
from src.model.token_tracker import TokenTracker


NON_STANDARD_SYMBOLS = set('[]【】［］{}《》“”"')


@dataclass(frozen=True)
class CandidateDecision:
    """Parsed model decision for a generated candidate list."""

    decision: str  # apply / skip / uncertain
    choice_id: str = ""
    reason: str = ""


class CandidateDecisionAgent:
    """Apply deterministic correction candidates selected by an LLM."""

    def __init__(
        self,
        text_doc: TextDoc,
        error_queue: ErrorQueue,
        model_client: OpenAICompatibleClient,
        tracker: ProgressTracker,
        verifier: Optional[Any] = None,
        max_decision_retries: int = 2,
        candidate_generator: Optional[CandidateGenerator] = None,
        rule_precheck: bool = False,
        llm_fallback: bool = True,
        token_tracker: Optional[TokenTracker] = None,
    ):
        self._text = text_doc
        self._queue = error_queue
        self._model = model_client
        self._tracker = tracker
        self._verifier = verifier
        self._max_decision_retries = max_decision_retries
        self._generator = candidate_generator or CandidateGenerator()
        self._rule_precheck = rule_precheck
        self._llm_fallback = llm_fallback
        self._pipeline = DetectorPipeline() if rule_precheck else None
        self._token_tracker = token_tracker

    def run_all(self, progress_callback: Optional[Callable] = None) -> List[AgentResult]:
        results: List[AgentResult] = []
        # Apply text edits from the end of the document to the beginning so
        # insertions/deletions do not invalidate offsets for later items.
        pending_errors = sorted(
            self._queue.pending(),
            key=lambda item: item.offset,
            reverse=True,
        )
        total = len(pending_errors)
        processed = 0
        processed_ids: set[str] = set()

        for error in pending_errors:
            if error.status != "pending":
                continue
            if error.error_id in processed_ids:
                self._queue.mark_failed(error.error_id, "stuck")
                continue

            processed += 1
            processed_ids.add(error.error_id)
            result = self._process_one_error(error)
            if progress_callback:
                progress_callback(processed, total, result)
            results.append(result)

        return results

    def _process_one_error(self, error: ErrorRecord) -> AgentResult:
        start_time = time.time()
        result = AgentResult(error_id=error.error_id, verdict="fail", retry_count=0)
        candidates = self._generator.generate(self._text, error)
        if not candidates:
            result.verdict = "uncertain"
            result.reason = "No rule candidates generated"
            result.duration = time.time() - start_time
            self._queue.mark_skipped(error.error_id, reason=result.reason)
            self._tracker.save_correction(error)
            return result

        if self._rule_precheck:
            selected, before_total, after_total = self._select_reducing_candidate(candidates)
            reason_prefix = "规则预检选择候选"
            if selected is None:
                selected, before_total, after_total = self._select_standardizing_candidate(
                    error, candidates, before_total)
                reason_prefix = "规则标准化选择候选"
            if selected is None:
                selected, before_total, after_total = self._select_unpaired_balancing_candidate(
                    error, candidates, before_total)
                reason_prefix = "规则配平孤立引号选择候选"
            if selected is None:
                selected, before_total, after_total = self._select_balanced_quote_candidate(
                    error, candidates, before_total)
                reason_prefix = "规则平衡拆分选择候选"
            if selected is not None:
                applied = self._apply_candidate(
                    error,
                    selected,
                    f"{reason_prefix}，检测错误数 {before_total} -> {after_total}",
                )
                applied.retry_count = 0
                applied.tool_calls = [
                    {
                        "name": "rule_precheck",
                        "arguments": {
                            "candidate_id": selected.candidate_id,
                            "before_total": before_total,
                            "after_total": after_total,
                        },
                    }
                ]
                applied.duration = time.time() - start_time
                return applied
            if not self._llm_fallback:
                result.verdict = "uncertain"
                result.reason = "No candidate reduced detector errors"
                result.duration = time.time() - start_time
                self._queue.mark_skipped(error.error_id, reason=result.reason)
                self._tracker.save_correction(error)
                return result

        for attempt in range(1, self._max_decision_retries + 1):
            result.retry_count = attempt
            try:
                response = self._model.chat(
                    messages=[
                        ChatMessage(role="system", content=self._system_prompt()),
                        ChatMessage(role="user", content=self._user_prompt(error, candidates)),
                    ],
                    tools=self._decision_tool_specs(),
                    temperature=0.0,
                    max_tokens=8192,
                )
                if self._token_tracker:
                    self._token_tracker.record(
                        source="candidate_decision",
                        error_id=error.error_id,
                        error_type=error.error_type,
                        usage=response.usage,
                    )
            except Exception as exc:
                result.reason = f"Model call failed: {exc}"
                break

            result.llm_response += response.content
            decision = self._parse_response_decision(response)
            if decision is None:
                result.reason = "Model did not return valid decision JSON"
                continue

            result.tool_calls.append(
                {
                    "name": "candidate_decision",
                    "arguments": {
                        "decision": decision.decision,
                        "choice_id": decision.choice_id,
                        "reason": decision.reason,
                    },
                }
            )

            if decision.decision in ("skip", "uncertain"):
                result.verdict = "uncertain"
                result.reason = decision.reason or decision.decision
                self._queue.mark_skipped(error.error_id, reason=result.reason)
                self._tracker.save_correction(error)
                result.duration = time.time() - start_time
                return result

            if decision.decision == "apply":
                candidate = self._find_candidate(candidates, decision.choice_id)
                if candidate is None:
                    result.reason = f"Unknown choice_id: {decision.choice_id}"
                    continue
                applied = self._apply_candidate(error, candidate, decision.reason)
                applied.retry_count = attempt
                applied.llm_response = result.llm_response
                applied.tool_calls = result.tool_calls
                applied.duration = time.time() - start_time
                return applied

        result.verdict = "uncertain"
        result.reason = result.reason or "No usable candidate decision"
        result.duration = time.time() - start_time
        self._queue.mark_skipped(error.error_id, reason=result.reason)
        self._tracker.save_correction(error)
        return result

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是小说对话符号纠错的候选判断器。规则程序已经生成候选修复，"
            "你只需要判断是否应用其中一个候选。不要自己编写 offset 或 replacement。"
            "如果有工具可用，必须调用 choose_candidate、skip_error 或 mark_uncertain 中的一个。"
            "如果没有工具，只输出 JSON：{\"decision\":\"apply|skip|uncertain\","
            "\"choice_id\":\"c1\",\"reason\":\"简短理由\"}。"
        )

    @staticmethod
    def _decision_tool_specs() -> list[ToolSpec]:
        return [
            ToolSpec(
                name="choose_candidate",
                description="Choose one generated correction candidate to apply.",
                parameters={
                    "type": "object",
                    "properties": {
                        "choice_id": {"type": "string", "description": "Candidate ID, e.g. c1"},
                        "reason": {"type": "string", "description": "Short reason"},
                    },
                    "required": ["choice_id", "reason"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="skip_error",
                description="Skip this error because none of the candidates should be applied.",
                parameters={
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "Short reason"},
                    },
                    "required": ["reason"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="mark_uncertain",
                description="Mark this error uncertain when the candidates are insufficient.",
                parameters={
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "Short reason"},
                    },
                    "required": ["reason"],
                    "additionalProperties": False,
                },
            ),
        ]

    def _user_prompt(self, error: ErrorRecord, candidates: list[CorrectionCandidate]) -> str:
        payload = {
            "error": {
                "error_id": error.error_id,
                "error_type": error.error_type,
                "line_number": error.line_number,
                "offset": error.offset,
                "original_text": error.original_text,
                "context_before": error.context_before[-120:],
                "context_after": error.context_after[:120],
            },
            "candidates": [candidate.preview(self._text) for candidate in candidates],
            "required_output": {
                "decision": "apply | skip | uncertain",
                "choice_id": "candidate_id when decision=apply, otherwise empty",
                "reason": "short Chinese explanation",
            },
        }
        return (
            json.dumps(payload, ensure_ascii=False, indent=2)
            + "\n\n请立即调用 choose_candidate、skip_error 或 mark_uncertain 工具中的一个；"
            "不要输出普通文本，不要自己编写 offset 或 replacement。"
        )

    @classmethod
    def _parse_response_decision(cls, response: Any) -> Optional[CandidateDecision]:
        for tool_call in getattr(response, "tool_calls", []) or []:
            args = tool_call.arguments
            if tool_call.name == "choose_candidate":
                return CandidateDecision(
                    decision="apply",
                    choice_id=str(args.get("choice_id", "")).strip(),
                    reason=str(args.get("reason", "")).strip(),
                )
            if tool_call.name == "skip_error":
                return CandidateDecision(
                    decision="skip",
                    reason=str(args.get("reason", "")).strip(),
                )
            if tool_call.name == "mark_uncertain":
                return CandidateDecision(
                    decision="uncertain",
                    reason=str(args.get("reason", "")).strip(),
                )
        return cls._parse_json_decision(getattr(response, "content", ""))

    @staticmethod
    def _parse_json_decision(content: str) -> Optional[CandidateDecision]:
        raw = _extract_json_object(content)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None

        decision = str(data.get("decision", "")).strip().lower()
        if decision not in {"apply", "skip", "uncertain"}:
            return None
        return CandidateDecision(
            decision=decision,
            choice_id=str(data.get("choice_id", "")).strip(),
            reason=str(data.get("reason", "")).strip(),
        )

    @staticmethod
    def _find_candidate(
        candidates: list[CorrectionCandidate],
        choice_id: str,
    ) -> Optional[CorrectionCandidate]:
        for candidate in candidates:
            if candidate.candidate_id == choice_id:
                return candidate
        return None

    def _apply_candidate(
        self,
        error: ErrorRecord,
        candidate: CorrectionCandidate,
        reason: str,
    ) -> AgentResult:
        result = AgentResult(
            error_id=error.error_id,
            verdict="fail",
            reason=reason,
            fix_applied=candidate.replacement,
        )

        original_slice = candidate.original(self._text)
        # 候选由规则生成，结构已保证正确，无需 Verifier 校验
        # 直接应用修正

        self._text.replace_range(
            candidate.start_offset,
            candidate.end_offset,
            candidate.replacement,
        )
        self._queue.mark_fixed(
            error.error_id,
            fix=candidate.replacement,
            verdict="pass",
            reason=reason or candidate.description,
        )
        self._tracker.save_correction(
            error,
            fix_result={
                "candidate_id": candidate.candidate_id,
                "start_offset": candidate.start_offset,
                "end_offset": candidate.end_offset,
                "original": original_slice,
                "replacement": candidate.replacement,
                "description": candidate.description,
            },
        )
        result.verdict = "pass"
        result.reason = reason or candidate.description
        return result

    def _select_reducing_candidate(
        self,
        candidates: list[CorrectionCandidate],
    ) -> tuple[Optional[CorrectionCandidate], int, int]:
        if self._pipeline is None:
            return None, 0, 0

        before_total = self._detected_total(self._text)
        best: Optional[CorrectionCandidate] = None
        best_total = before_total
        for candidate in candidates:
            candidate_text = TextDoc(self._text.text)
            candidate_text.replace_range(
                candidate.start_offset,
                candidate.end_offset,
                candidate.replacement,
            )
            after_total = self._detected_total(candidate_text)
            if after_total < best_total:
                best = candidate
                best_total = after_total
        return best, before_total, best_total

    def _select_balanced_quote_candidate(
        self,
        error: ErrorRecord,
        candidates: list[CorrectionCandidate],
        before_total: int,
    ) -> tuple[Optional[CorrectionCandidate], int, int]:
        if self._pipeline is None or error.error_type != "long_dialogue":
            return None, before_total, before_total

        best: Optional[CorrectionCandidate] = None
        best_total = before_total
        best_span = 10**9
        for candidate in candidates:
            original = candidate.original(self._text)
            left_delta = candidate.replacement.count("「") - original.count("「")
            right_delta = candidate.replacement.count("」") - original.count("」")
            if left_delta <= 0 or left_delta != right_delta:
                continue

            candidate_text = TextDoc(self._text.text)
            candidate_text.replace_range(
                candidate.start_offset,
                candidate.end_offset,
                candidate.replacement,
            )
            after_total = self._detected_total(candidate_text)
            span = candidate.end_offset - candidate.start_offset
            if best is None or after_total < best_total or (
                after_total == best_total and span < best_span
            ):
                best = candidate
                best_total = after_total
                best_span = span

        return best, before_total, best_total

    def _select_standardizing_candidate(
        self,
        error: ErrorRecord,
        candidates: list[CorrectionCandidate],
        before_total: int,
    ) -> tuple[Optional[CorrectionCandidate], int, int]:
        if self._pipeline is None or error.error_type != "wrong_symbol":
            return None, before_total, before_total

        best: Optional[CorrectionCandidate] = None
        best_total = before_total
        best_span = 10**9
        for candidate in candidates:
            original = candidate.original(self._text)
            before_non_standard = self._non_standard_count(original)
            after_non_standard = self._non_standard_count(candidate.replacement)
            if before_non_standard == 0 or after_non_standard >= before_non_standard:
                continue

            candidate_text = TextDoc(self._text.text)
            candidate_text.replace_range(
                candidate.start_offset,
                candidate.end_offset,
                candidate.replacement,
            )
            span = candidate.end_offset - candidate.start_offset
            after_total = self._detected_total(candidate_text)
            is_single_symbol_standardization = (
                span == 1 and candidate.replacement in {"「", "」"}
            )
            if after_total > before_total and not is_single_symbol_standardization:
                continue

            if best is None or after_total < best_total or (
                after_total == best_total and span < best_span
            ):
                best = candidate
                best_total = after_total
                best_span = span

        return best, before_total, best_total

    def _select_unpaired_balancing_candidate(
        self,
        error: ErrorRecord,
        candidates: list[CorrectionCandidate],
        before_total: int,
    ) -> tuple[Optional[CorrectionCandidate], int, int]:
        if self._pipeline is None or error.error_type != "unpaired":
            return None, before_total, before_total

        before_balance = self._quote_balance_score(self._text.text)
        best: Optional[CorrectionCandidate] = None
        best_total = before_total
        best_balance = before_balance
        best_span = 10**9
        for candidate in candidates:
            original = candidate.original(self._text)
            if (
                self._non_standard_count(candidate.replacement)
                > self._non_standard_count(original)
            ):
                continue

            candidate_text = TextDoc(self._text.text)
            candidate_text.replace_range(
                candidate.start_offset,
                candidate.end_offset,
                candidate.replacement,
            )
            balance = self._quote_balance_score(candidate_text.text)
            if balance >= before_balance:
                continue

            after_total = self._detected_total(candidate_text)
            span = candidate.end_offset - candidate.start_offset
            if best is None or balance < best_balance or (
                balance == best_balance
                and (
                    after_total < best_total
                    or (after_total == best_total and span < best_span)
                )
            ):
                best = candidate
                best_total = after_total
                best_balance = balance
                best_span = span

        return best, before_total, best_total

    @staticmethod
    def _non_standard_count(text: str) -> int:
        return sum(1 for ch in text if ch in NON_STANDARD_SYMBOLS)

    @staticmethod
    def _quote_balance_score(text: str) -> int:
        return abs(text.count("「") - text.count("」"))

    def _detected_total(self, text: TextDoc) -> int:
        if self._pipeline is None:
            return 0

        counter = ErrorRecord._id_counter
        try:
            return self._pipeline.run(text).total
        finally:
            ErrorRecord._id_counter = counter


def _extract_json_object(content: str) -> Optional[str]:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    return stripped[start:end + 1]
