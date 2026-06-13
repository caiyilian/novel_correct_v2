"""
CorrectionVerifier — 纠正确认器

验证 LLM 的每一次修正是否合理。检查维度：
1. 修改范围是否仅限于「」符号
2. 修改后「和」是否成对
3. 修改在上下文中是否语义合理
4. 是否保持了原文的其他内容不变
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.error_record import ErrorRecord, VerifierVerdict
from src.model.client import ChatMessage, OpenAICompatibleClient


VERDICTS = {"pass", "fail", "uncertain"}


@dataclass
class VerifierResult:
    """Verifier 的判定结果。"""
    verdict: str          # pass / fail / uncertain
    reason: str           # 判定理由
    confidence: str = "medium"  # high / medium / low
    details: Dict[str, Any] = None


class CorrectionVerifier:
    """
    纠正确认器。

    验证 LLM 的修正是否合理。有两种模式：
    1. Rule Verifier（默认）：纯规则校验，不调用 LLM，速度快
    2. LLM Verifier（可选）：调用 LLM 进行语义级验证
    """

    def __init__(self, model_client: Optional[OpenAICompatibleClient] = None):
        self._model = model_client

    # ── 主接口 ────────────────────────────────────────

    def verify(
        self,
        error: ErrorRecord,
        original_text: str,
        modified_text: str,
        fix_detail: Optional[dict] = None,
    ) -> VerifierResult:
        """
        验证一次修正是否合理。

        Args:
            error: 被修正的错误记录。
            original_text: 修正前的完整文本。
            modified_text: 修正后的完整文本。
            fix_detail: 修正操作的详细信息（可选）。

        Returns:
            VerifierResult：pass / fail / uncertain。
        """
        # 第一层：规则验证（不调 LLM）
        rule_result = self._rule_check(error, original_text, modified_text)
        if rule_result.verdict == "fail":
            return rule_result

        # 第二层：语义验证（调 LLM，可选）
        if self._model and rule_result.verdict != "fail":
            llm_result = self._llm_check(error, original_text, modified_text)
            return llm_result

        return rule_result

    # ── 规则验证 ────────────────────────────────────────

    def _rule_check(
        self,
        error: ErrorRecord,
        original_text: str,
        modified_text: str,
    ) -> VerifierResult:
        """纯规则校验。不调 LLM。"""
        issues: List[str] = []

        # 1. 检查修改前后长度变化是否合理（防止大量内容被替换）
        orig_len = len(original_text)
        mod_len = len(modified_text)
        len_ratio = mod_len / orig_len if orig_len > 0 else 1.0
        if len_ratio < 0.5 or len_ratio > 2.0:
            issues.append(
                f"Text length changed by {(len_ratio - 1) * 100:.0f}% "
                f"({orig_len} → {mod_len})"
            )

        # 2. 检查「和」数量是否成对
        orig_left = original_text.count("「")
        orig_right = original_text.count("」")
        mod_left = modified_text.count("「")
        mod_right = modified_text.count("」")

        # 修正应该只改变符号，所以「和」的增减应该平衡
        left_delta = mod_left - orig_left
        right_delta = mod_right - orig_right

        if left_delta != right_delta:
            issues.append(
                f"Unbalanced bracket change: 「{left_delta:+d}, 」{right_delta:+d}"
            )

        # 2b. 检查「」总数不应减少（修正只会增加或保持，不会删除对话符号）
        orig_total_brackets = orig_left + orig_right
        mod_total_brackets = mod_left + mod_right
        if mod_total_brackets < orig_total_brackets:
            # 但缺失符号补全的情况是增加，删除符号是减少
            # 只有非成对减少才算问题
            if error.error_type != "unpaired":  # unpaired 可能涉及删除多余符号
                issues.append(
                    f"Bracket count decreased: {orig_total_brackets} → {mod_total_brackets}"
                )

        # 3. 检查修改后的文本是否还有连续符号错误
        if self._has_consecutive_brackets(modified_text):
            issues.append("Modified text still has consecutive brackets")

        # 4. 验证错误类型的特定检查
        type_issue = self._check_by_type(error, original_text, modified_text)
        if type_issue:
            issues.append(type_issue)

        if issues:
            return VerifierResult(
                verdict="fail",
                reason="; ".join(issues[:3]),
                confidence="high",
                details={"issues": issues},
            )

        return VerifierResult(
            verdict="pass",
            reason="All rule checks passed",
            confidence="high",
        )

    @staticmethod
    def _has_consecutive_brackets(text: str) -> bool:
        """检查文本中是否有连续相同的「」符号。"""
        last = "」"
        for ch in text:
            if ch in ("「", "」"):
                if ch == last:
                    return True
                last = ch
        return False

    def _check_by_type(
        self,
        error: ErrorRecord,
        original_text: str,
        modified_text: str,
    ) -> Optional[str]:
        """错误类型特定的检查。"""
        etype = error.error_type

        if etype == "wrong_symbol":
            # 检查非标准符号是否已被替换
            non_standard = set('[]【】［］{}《》""\u201c\u201d')
            orig_count = sum(1 for ch in original_text if ch in non_standard)
            mod_count = sum(1 for ch in modified_text if ch in non_standard)
            if orig_count == mod_count and orig_count > 0:
                return "Non-standard symbols not replaced"

        elif etype == "consecutive":
            # 验证连续符号是否真的被修好了
            if error.fix_applied and "「" not in error.fix_applied and "」" not in error.fix_applied:
                return "Fix doesn't contain bracket symbols"

        elif etype == "long_dialogue":
            # 验证超长对话的上下文变化合理
            orig_content = original_text.strip()
            mod_content = modified_text.strip()
            if abs(len(mod_content) - len(orig_content)) > 200:
                return "Dialogue split changed too much content"

        return None

    # ── LLM 验证 ──────────────────────────────────────

    def _llm_check(
        self,
        error: ErrorRecord,
        original_text: str,
        modified_text: str,
    ) -> VerifierResult:
        """调用 LLM 进行语义验证。"""
        if not self._model:
            return VerifierResult(
                verdict="uncertain",
                reason="No LLM verifier configured",
                confidence="low",
            )

        prompt = self._build_verifier_prompt(error, original_text, modified_text)

        try:
            response = self._model.chat(
                messages=[
                    ChatMessage(role="system", content=(
                        "You are a correction verifier. Your only job is to check "
                        "whether a bracket correction is valid. "
                        "Return JSON only: {\"verdict\":\"pass|fail|uncertain\",\"reason\":\"...\",\"confidence\":\"high|medium|low\"}"
                    )),
                    ChatMessage(role="user", content=prompt),
                ],
                temperature=0.0,
                max_tokens=300,
            )
        except Exception as e:
            return VerifierResult(
                verdict="uncertain",
                reason=f"LLM call failed: {e}",
                confidence="low",
            )

        return self._parse_llm_response(response.content)

    def _build_verifier_prompt(
        self,
        error: ErrorRecord,
        original: str,
        modified: str,
    ) -> str:
        """构建 Verifier 的 prompt。"""
        json_shape = '{"verdict":"pass|fail|uncertain","reason":"short explanation","confidence":"high|medium|low"}'
        return (
            f"Verify the following bracket correction:\n\n"
            f"Error type: {error.error_type}\n"
            f"Location: line {error.line_number}\n\n"
            f"Before: {original[:200]}\n\n"
            f"After:  {modified[:200]}\n\n"
            f"Rules:\n"
            f"- Only bracket symbols should change, never text content\n"
            f"- Just after the correction 「 and 」 must be properly paired\n"
            f"- The fix should make sense in the dialog/narrative context\n\n"
            f"Return JSON: {json_shape}"
        )

    @staticmethod
    def _parse_llm_response(content: str) -> VerifierResult:
        """解析 LLM 的 JSON 响应。"""
        # 尝试提取 JSON
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if len(lines) >= 3:
                content = "\n".join(lines[1:-1]).strip()
                if content.startswith("json"):
                    content = content[4:].strip()

        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return VerifierResult(
                verdict="uncertain",
                reason="LLM response not valid JSON",
                confidence="low",
            )

        try:
            data = json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            return VerifierResult(
                verdict="uncertain",
                reason="LLM response JSON parse failed",
                confidence="low",
            )

        verdict = data.get("verdict", "uncertain")
        if verdict not in VERDICTS:
            verdict = "uncertain"

        return VerifierResult(
            verdict=verdict,
            reason=data.get("reason", "No reason provided"),
            confidence=data.get("confidence", "medium"),
            details={"raw_llm": content[start:end + 1]},
        )
