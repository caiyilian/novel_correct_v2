"""
Agent Loop — 纠错 Agent 的核心循环

每轮处理一个错误：获取错误 → 调用 LLM → LLM 调用工具 → Verifier 确认 → checkpoint。
一轮只处理一个错误，完成后重置会话，防止上下文窗口膨胀。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.core.progress import ProgressTracker
from src.core.text import TextDoc
from src.model.client import (
    ChatMessage,
    OpenAICompatibleClient,
)
from src.agent.tools import CorrectionToolset
from src.agent.prompts import build_system_prompt, build_user_prompt


@dataclass
class AgentResult:
    """一次 Agent 处理的完整结果。"""
    error_id: str
    verdict: str  # pass / fail / uncertain
    reason: str = ""
    fix_applied: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    llm_response: str = ""
    duration: float = 0.0
    retry_count: int = 0


class CorrectionAgent:
    """
    纠错 Agent。

    用法：
        agent = CorrectionAgent(text_doc, error_queue, model_client, tracker)
        results = agent.run_all()  # 处理所有待处理错误
    """

    def __init__(
        self,
        text_doc: TextDoc,
        error_queue: ErrorQueue,
        model_client: OpenAICompatibleClient,
        tracker: ProgressTracker,
        verifier: Optional[Any] = None,
        max_retries: int = 3,
        max_rounds: int = 5,
    ):
        self._text = text_doc
        self._queue = error_queue
        self._model = model_client
        self._tracker = tracker
        self._verifier = verifier  # Stage 14 实现，暂时为 None
        self._max_retries = max_retries
        self._max_rounds = max_rounds

        # 工具集（每次处理新错误时重新创建）
        self._tools: Optional[CorrectionToolset] = None

    # ── 主循环 ──────────────────────────────────────────

    def run_all(self, progress_callback: Optional[Callable] = None) -> List[AgentResult]:
        """
        处理所有待处理错误。

        Args:
            progress_callback: 每处理完一个错误后调用，参数为 (当前序号, 总数, AgentResult)

        Returns:
            所有错误的处理结果列表。
        """
        results: List[AgentResult] = []
        total = self._queue.remaining()
        processed = 0
        processed_ids: set[str] = set()  # 防止同一错误被重复处理

        while self._queue.remaining() > 0:
            error = self._queue.next_pending()
            if error is None:
                break

            # 防御：如果这个 error_id 已经处理过，跳过
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
        """
        处理单个错误。
        每轮都创建新的工具集和新的会话，防止上下文窗口膨胀。
        """
        start_time = time.time()
        self._tools = CorrectionToolset(self._text, self._queue)

        for attempt in range(1, self._max_retries + 1):
            result = self._attempt_one(error, attempt)

            # 如果成功或跳过了，直接返回
            if result.verdict in ("pass", "uncertain"):

                # 先更新状态，再保存（确保 checkpoint 中 status 正确）
                if result.fix_applied and result.verdict == "pass":
                    self._queue.mark_fixed(
                        error.error_id,
                        fix=result.fix_applied,
                        verdict="pass",
                        reason=result.reason,
                    )
                elif result.verdict == "uncertain":
                    self._queue.mark_skipped(error.error_id, reason=result.reason)

                # 状态更新后再保存 checkpoint
                self._tracker.save_correction(error)

                return result

            # 失败了，重试
            error.retry_count = attempt
            if result.reason.startswith("No terminating tool call"):
                break

        # 所有重试都失败
        result.verdict = "fail"
        if not result.reason or not result.reason.startswith("No terminating tool call"):
            result.reason = f"All {self._max_retries} attempts failed"
        # 直接强制修改状态（防止 queue.mark_failed 内部异常）
        try:
            error.status = "failed"
            error.fail_reason = result.reason
        except Exception:
            pass
        try:
            self._queue.mark_failed(error.error_id, reason=result.reason)
        except Exception as e:
            pass
        try:
            self._tracker.save_correction(error)
        except Exception as e:
            pass
        result.duration = time.time() - start_time
        return result

    def _attempt_one(self, error: ErrorRecord, attempt: int) -> AgentResult:
        """单次尝试处理一个错误。"""
        start_time = time.time()
        result = AgentResult(
            error_id=error.error_id,
            verdict="fail",
            duration=0.0,
            retry_count=attempt,
        )

        messages: List[ChatMessage] = [
            ChatMessage(role="system", content=build_system_prompt(error.error_type)),
            ChatMessage(role="user", content=build_user_prompt(error)),
        ]

        tool_specs = CorrectionToolset.tool_specs()

        # 与 LLM 对话循环
        round_count = 0

        while round_count < self._max_rounds:
            round_count += 1

            try:
                response = self._model.chat(
                    messages=messages,
                    tools=tool_specs,
                    temperature=0.0,
                    max_tokens=8192,
                )
            except Exception as e:
                result.reason = f"Model call failed: {e}"
                result.duration = time.time() - start_time
                return result

            # 记录 LLM 响应
            result.llm_response += response.content

            if response.tool_calls:
                # LLM 调用了工具
                for tc in response.tool_calls:
                    # 记录工具调用
                    tool_entry = {"name": tc.name, "arguments": tc.arguments}
                    result.tool_calls.append(tool_entry)

                    # 执行工具
                    tool_result = self._tools.execute(tc.name, tc.arguments)

                    # 将工具调用和结果加入消息
                    messages.append(
                        ChatMessage(
                            role="assistant",
                            content="",
                            tool_calls=[tc.to_openai_tool_call()],
                        )
                    )
                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=str(tool_result),
                            tool_call_id=tc.id,
                        )
                    )

                    # 检查是否是终止性工具调用
                    if tc.name == "apply_fix":
                        if not isinstance(tool_result, dict) or tool_result.get("status") != "ok":
                            result.verdict = "fail"
                            result.reason = (
                                f"apply_fix failed: "
                                f"{tool_result.get('message', 'unknown') if isinstance(tool_result, dict) else tool_result}"
                            )
                            messages.append(
                                ChatMessage(
                                    role="user",
                                    content=(
                                        f"{result.reason}. 请重新调用 apply_fix，"
                                        f"或在确认不是错误时调用 skip_error。"
                                    ),
                                )
                            )
                            continue
                        # 用 Verifier 验证修正
                        if self._verifier:
                            v_result = self._verifier.verify(
                                error=error,
                                original_text=tool_result.get("original_full", self._text.text),
                                modified_text=self._tools.current_text,
                                fix_detail={"replacement": tool_result.get("replacement", "")},
                            )
                            if v_result.verdict != "pass":
                                # Verifier 不通过，回滚
                                self._tools.revert_fix(error.error_id)
                                result.verdict = "fail"
                                result.reason = f"Verifier rejected: {v_result.reason}"
                                messages.append(
                                    ChatMessage(
                                        role="user",
                                        content=f"Verifier rejected the fix: {v_result.reason}. Please try a different approach.",
                                    )
                                )
                                continue  # 继续下一轮对话
                        result.verdict = "pass"
                        result.fix_applied = tool_result.get("replacement", "")
                        result.reason = tool_result.get("action", "fix applied")
                    elif tc.name == "skip_error":
                        result.verdict = "uncertain"
                        result.reason = tc.arguments.get("reason", "skipped")

                # 如果 LLM 调用了 apply_fix 或 skip_error，本轮已经完成
                if result.verdict in ("pass", "uncertain"):
                    break
            else:
                # LLM 没有调工具，直接返回文本
                # 可能是 LLM 在分析或说明，继续下一轮
                messages.append(
                    ChatMessage(role="user", content="请使用工具处理此错误，不要只回复文本。")
                )

        result.duration = time.time() - start_time

        # 没有调用终止性工具 → 视为失败
        if result.verdict not in ("pass", "uncertain"):
            result.reason = f"No terminating tool call within {self._max_rounds} rounds"

        return result
