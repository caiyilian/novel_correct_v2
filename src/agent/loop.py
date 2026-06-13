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
    ChatResult,
    ModelConfig,
    OpenAICompatibleClient,
    ToolCall,
)
from src.model.protocol import ToolSpec
from src.agent.tools import CorrectionToolset


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
    ):
        self._text = text_doc
        self._queue = error_queue
        self._model = model_client
        self._tracker = tracker
        self._verifier = verifier  # Stage 14 实现，暂时为 None
        self._max_retries = max_retries

        # 工具集（每次处理新错误时重新创建）
        self._tools: Optional[CorrectionToolset] = None

        # 系统提示词
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """构建系统提示词。"""
        return """你是一个小说文本纠错专家。你的任务是对小说中人物对话的包裹符号进行纠错。

## 核心规则
1. 小说人物对话的唯一合法包裹符号是成对的全角直角引号「」
2. 你需要修复以下类型的错误：
   a. 「「 或 」」连续出现（其中一个符号应为其他符号）
   b. [ ]、【】等非「」符号包裹了对话
   c. 对话内部缺失「或」，导致对话与旁白被错误合并
   d. 成对不匹配（有「无」或有」无「）

## 你的职责范围（严格遵守）
1. 你的任务是修正——不是发现错误。错误位置已经由规则检测器定位好了
2. 每次只处理一个错误。用 get_next_error 获取
3. 只修改指定的错误位置，不要改其他地方
4. 如果不确定，用工具多读上下文，不要猜

## 工作流程
1. 调用 get_next_error 获取当前错误
2. 调用 read_lines 或 read_offset 阅读上下文
3. 如有需要，调用 search_text 搜索关键词
4. 确认错误后，调用 apply_fix 执行修正
5. 如果确认不是错误，调用 skip_error 跳过
6. 如果修错了，可以调用 revert_fix 回滚

## 注意事项
- 每次修正后会自动验证，请确保修正合理
- 只修改对话包裹符号，不修改原文内容
- 修改范围要保持最小"""

    def _build_error_prompt(self, error: ErrorRecord) -> str:
        """为当前错误构建 user prompt。"""
        msg = f"请处理以下错误：\n\n"
        msg += f"错误 ID: {error.error_id}\n"
        msg += f"错误类型: {error.error_type}\n"
        msg += f"位置: 第{error.line_number}行 (offset {error.offset})\n"
        msg += f"错误内容: {error.original_text[:80]}\n"
        msg += f"上文: ...{error.context_before[-60:]}\n"
        msg += f"下文: {error.context_after[:60]}...\n\n"

        type_hints = {
            "consecutive": "检测到连续相同的符号（「「 或 」」），请判断哪个符号是错的并修正。",
            "unpaired": "检测到「和」数量不匹配，可能需要补上缺失的符号或删除多余的符号。",
            "wrong_symbol": "检测到非标准符号（如 [ ] 【】 "" 等），请判断是否应替换为「」。",
            "long_dialogue": "检测到超长对话，可能因缺失符号导致旁白被合并到对话中，请判断是否需要拆分。",
            "missing_bracket": "该行包含对话特征词（说道：问：等）但缺少「」，请判断是否应补充。",
        }
        hint = type_hints.get(error.error_type, "")
        if hint:
            msg += f"提示: {hint}\n\n"

        msg += "请使用工具分析上下文并处理此错误。"
        return msg

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

        while self._queue.remaining() > 0:
            error = self._queue.next_pending()
            if error is None:
                break

            processed += 1
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
                # 保存 checkpoint
                self._tracker.save_correction(error)

                # 如果 fix_applied 不为空，同步到错误队列
                if result.fix_applied and result.verdict == "pass":
                    self._queue.mark_fixed(
                        error.error_id,
                        fix=result.fix_applied,
                        verdict="pass",
                        reason=result.reason,
                    )
                elif result.verdict == "uncertain":
                    self._queue.mark_skipped(error.error_id, reason=result.reason)

                return result

            # 失败了，重试
            error.retry_count = attempt

        # 所有重试都失败
        result.verdict = "fail"
        result.reason = f"All {self._max_retries} attempts failed"
        self._queue.mark_failed(error.error_id, reason=result.reason)
        self._tracker.save_correction(error)
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
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=self._build_error_prompt(error)),
        ]

        tool_specs = CorrectionToolset.tool_specs()

        # 与 LLM 对话循环
        round_count = 0
        max_rounds = 15  # 防止无限循环

        while round_count < max_rounds:
            round_count += 1

            try:
                response = self._model.chat(
                    messages=messages,
                    tools=tool_specs,
                    temperature=0.0,
                    max_tokens=2000,
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
            result.reason = "No terminating tool call in response"

        return result
