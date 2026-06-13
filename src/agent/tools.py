"""
CorrectionToolset — LLM 在纠错中可以调用的工具集

每个工具都有对应的 ToolSpec（OpenAI function calling 格式），
通过 apply_fix / skip_error 等工具修改文本，通过 read_lines / search_text 等工具阅读文本。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.core.text import TextDoc
from src.model.protocol import ToolSpec


@dataclass
class SearchMatch:
    """搜索结果中的一条匹配记录。"""
    line_number: int
    line: str

    def to_dict(self) -> dict:
        return {"line_number": self.line_number, "line": self.line}


class CorrectionToolset:
    """
    LLM 可调用的纠错工具集。

    所有工具操作都在内存中进行（修改 TextDoc 的内部状态），
    只在 checkpoint 时才写入磁盘。
    """

    def __init__(self, text_doc: TextDoc, error_queue: ErrorQueue):
        self._text = text_doc
        self._queue = error_queue
        self._current_text: Optional[str] = text_doc.text  # 可变的文本副本
        # 回滚栈：[(error_id, original_slice, new_slice), ...]
        self._history: List[Dict[str, Any]] = []

    # ── 工具定义（用于生成 ToolSpec） ─────────────────────

    @classmethod
    def tool_specs(cls) -> List[ToolSpec]:
        """返回所有工具的 ToolSpec 列表。"""
        return [
            ToolSpec(
                name="read_lines",
                description="Read the source novel by 1-based inclusive line range. Returns text with line numbers.",
                parameters={
                    "type": "object",
                    "properties": {
                        "start": {"type": "integer", "minimum": 1,
                                  "description": "Start line number (1-based)"},
                        "end": {"type": "integer", "minimum": 1,
                                "description": "End line number (inclusive)"},
                    },
                    "required": ["start", "end"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="read_offset",
                description="Read text centered at a specific character offset with surrounding context.",
                parameters={
                    "type": "object",
                    "properties": {
                        "offset": {"type": "integer", "minimum": 0,
                                   "description": "Character offset in the full text"},
                        "context": {"type": "integer", "minimum": 50,
                                    "description": "Characters of context on each side (default 200)"},
                    },
                    "required": ["offset"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="search_text",
                description="Search the novel for a keyword and return matching line numbers and content.",
                parameters={
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "minLength": 1,
                                    "description": "Keyword to search for"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50,
                                  "description": "Max results to return (default 20)"},
                    },
                    "required": ["keyword"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="get_next_error",
                description="Get the next pending error that needs fixing. Returns error details including type, location, and surrounding context.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="apply_fix",
                description="Apply a text replacement fix at the specified offset range. Use after analyzing the error context.",
                parameters={
                    "type": "object",
                    "properties": {
                        "error_id": {"type": "string",
                                     "description": "The error ID to fix"},
                        "start_offset": {"type": "integer", "minimum": 0,
                                         "description": "Start offset of the text to replace"},
                        "end_offset": {"type": "integer", "minimum": 0,
                                       "description": "End offset (exclusive) of the text to replace"},
                        "replacement": {"type": "string",
                                        "description": "The replacement text"},
                    },
                    "required": ["error_id", "start_offset", "end_offset", "replacement"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="skip_error",
                description="Skip an error that upon inspection is not actually an error. Provide a reason.",
                parameters={
                    "type": "object",
                    "properties": {
                        "error_id": {"type": "string",
                                     "description": "The error ID to skip"},
                        "reason": {"type": "string",
                                   "description": "Why this is not an error"},
                    },
                    "required": ["error_id", "reason"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="revert_fix",
                description="Revert the most recent fix applied to a specific error. Call this when you realize a previous fix was wrong.",
                parameters={
                    "type": "object",
                    "properties": {
                        "error_id": {"type": "string",
                                     "description": "The error ID whose fix to revert"},
                    },
                    "required": ["error_id"],
                    "additionalProperties": False,
                },
            ),
        ]

    # ── 文本阅读工具 ────────────────────────────────────

    def read_lines(self, start: int, end: int) -> str:
        """按行号范围读取文本。"""
        try:
            return self._text.line_range(start, end)
        except IndexError as e:
            return f"Error: {e}"

    def read_offset(self, offset: int, context: int = 200) -> str:
        """以指定偏移为中心读取上下文。"""
        text = self._current_text or self._text.text
        start = max(0, offset - context)
        end = min(len(text), offset + context)
        line_num = self._text.offset_to_line(offset)
        return (
            f"[context around offset {offset} (line {line_num})]\n"
            f"{text[start:end]}"
        )

    def search_text(self, keyword: str, limit: int = 20) -> Dict[str, Any]:
        """搜索关键词，返回匹配行号和内容。"""
        matches: List[SearchMatch] = []
        total_matches = 0

        for line_num, line in enumerate(self._text.lines(), start=1):
            if keyword in line:
                total_matches += 1
                if len(matches) < limit:
                    matches.append(SearchMatch(
                        line_number=line_num,
                        line=f"{line_num}: {line[:120]}{'...' if len(line) > 120 else ''}"
                    ))

        return {
            "keyword": keyword,
            "matches": [m.to_dict() for m in matches],
            "total_matches": total_matches,
            "truncated": total_matches > len(matches),
        }

    # ── 错误处理工具 ────────────────────────────────────

    def get_next_error(self) -> Dict[str, Any]:
        """获取下一个待处理的错误。"""
        error = self._queue.next_pending()
        if error is None:
            return {"status": "done", "message": "All errors have been processed."}
        return {
            "status": "pending",
            "error_id": error.error_id,
            "error_type": error.error_type,
            "line_number": error.line_number,
            "offset": error.offset,
            "context_before": error.context_before[-100:],
            "context_after": error.context_after[:100],
            "original_text": error.original_text[:80],
        }

    def get_progress(self) -> Dict[str, Any]:
        """返回当前纠错进度。"""
        return self._queue.progress()

    def skip_error(self, error_id: str, reason: str) -> Dict[str, Any]:
        """标记一个错误为跳过。"""
        error = self._queue.get(error_id)
        if error is None:
            return {"status": "error", "message": f"Unknown error_id: {error_id}"}
        self._queue.mark_skipped(error_id, reason)
        return {
            "status": "ok",
            "error_id": error_id,
            "action": "skipped",
            "reason": reason,
        }

    def apply_fix(self, error_id: str, start_offset: int,
                  end_offset: int, replacement: str) -> Dict[str, Any]:
        """在文本中执行替换修正。"""
        error = self._queue.get(error_id)
        if error is None:
            return {"status": "error", "message": f"Unknown error_id: {error_id}"}

        text = self._current_text or self._text.text

        if start_offset < 0 or end_offset > len(text) or start_offset >= end_offset:
            return {
                "status": "error",
                "message": f"Invalid offsets: [{start_offset}, {end_offset}) "
                           f"for text length {len(text)}",
            }

        # 保存回滚信息
        original_slice = text[start_offset:end_offset]
        self._history.append({
            "error_id": error_id,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "original": original_slice,
        })

        # 执行替换
        self._current_text = text[:start_offset] + replacement + text[end_offset:]

        # 标记错误为已修复（暂定，Verifier 确认后才能最终标记）
        error.fix_applied = replacement[:100]

        return {
            "status": "ok",
            "error_id": error_id,
            "action": "fix_applied",
            "original": original_slice[:80],
            "replacement": replacement[:80],
        }

    def revert_fix(self, error_id: str) -> Dict[str, Any]:
        """回滚指定错误的最新一次修正。"""
        # 从历史中查找该 error_id 的最新记录
        for i in range(len(self._history) - 1, -1, -1):
            entry = self._history[i]
            if entry["error_id"] == error_id:
                text = self._current_text or self._text.text
                start = entry["start_offset"]
                end = entry["end_offset"]
                original = entry["original"]

                # 回滚
                self._current_text = text[:start] + original + text[end:]
                self._history.pop(i)

                # 重置错误状态
                error = self._queue.get(error_id)
                if error:
                    error.fix_applied = ""
                    error.status = "pending"

                return {
                    "status": "ok",
                    "error_id": error_id,
                    "action": "reverted",
                    "restored": original[:80],
                }

        return {
            "status": "error",
            "message": f"No fix history found for error_id: {error_id}",
        }

    # ── 工具分发 ────────────────────────────────────────

    def execute(self, tool_name: str, arguments: dict) -> Any:
        """根据工具名和执行参数调用对应的工具方法。"""
        handler = {
            "read_lines": self.read_lines,
            "read_offset": self.read_offset,
            "search_text": self.search_text,
            "get_next_error": self.get_next_error,
            "get_progress": self.get_progress,
            "skip_error": self.skip_error,
            "apply_fix": self.apply_fix,
            "revert_fix": self.revert_fix,
        }
        func = handler.get(tool_name)
        if func is None:
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}
        return func(**arguments)

    @property
    def current_text(self) -> str:
        """返回当前（可能已修改过的）文本。"""
        return self._current_text or self._text.text

    @property
    def history(self) -> List[Dict[str, Any]]:
        """返回所有修改历史。"""
        return list(self._history)
