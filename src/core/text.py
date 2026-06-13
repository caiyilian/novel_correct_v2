"""
TextDoc — 文本文档的核心数据结构

存储加载后的文本全文、按行拆分的列表以及检测到的编码信息。
提供按行号访问、全文访问等基础操作。
"""

from __future__ import annotations

from typing import List, Optional


class TextDoc:
    """表示一份已加载的文本文档。"""

    def __init__(self, text: str, encoding: str = "utf-8", path: str = ""):
        # 原始全文（已归一化：\r\n → \n，无 BOM）
        self._text = text
        # 检测到的编码
        self._encoding = encoding
        # 源文件路径
        self._path = path
        # 按行拆分（缓存）
        self._lines: Optional[List[str]] = None

    # ─── 属性 ─────────────────────────────────────────────

    @property
    def text(self) -> str:
        """返回全文。"""
        return self._text

    @property
    def encoding(self) -> str:
        """返回检测到的编码名称。"""
        return self._encoding

    @property
    def path(self) -> str:
        """返回源文件路径。"""
        return self._path

    # ─── 行操作 ───────────────────────────────────────────

    def _ensure_lines(self) -> List[str]:
        if self._lines is None:
            self._lines = self._text.splitlines()
        return self._lines

    def lines(self) -> List[str]:
        """返回所有行的列表（不含换行符）。"""
        return list(self._ensure_lines())

    def line_count(self) -> int:
        """返回总行数。"""
        return len(self._ensure_lines())

    def __getitem__(self, index: int) -> str:
        """按行号访问（1-based）。"""
        lines = self._ensure_lines()
        if not lines:
            raise IndexError("TextDoc is empty")
        if isinstance(index, slice):
            # 支持切片
            start = index.start or 1
            stop = index.stop or (len(lines) + 1)
            step = index.step or 1
            # 转换为 0-based
            zero_start = start - 1
            zero_stop = stop - 1
            result = lines[zero_start:zero_stop:step]
            return "\n".join(result)
        if index < 1 or index > len(lines):
            raise IndexError(
                f"line number {index} out of range (1..{len(lines)})"
            )
        return lines[index - 1]

    def line_range(self, start: int, end: int) -> str:
        """返回 [start, end] 行号范围内的文本（含两端，1-based）。"""
        return self[start:end + 1]

    # ─── 工具 ─────────────────────────────────────────────

    def get_line_with_context(self, line_num: int, context: int = 3) -> str:
        """获取指定行及其上下文的文本片段。"""
        lines = self._ensure_lines()
        start = max(1, line_num - context)
        end = min(len(lines), line_num + context)
        result: List[str] = []
        for i in range(start, end + 1):
            prefix = ">>>" if i == line_num else "   "
            result.append(f"{prefix} {i}: {lines[i - 1]}")
        return "\n".join(result)

    def offset_to_line(self, offset: int) -> int:
        """将字符偏移量转换为行号（1-based）。"""
        if offset < 0 or offset > len(self._text):
            raise IndexError(
                f"offset {offset} out of range (0..{len(self._text)})"
            )
        return self._text[:offset].count("\n") + 1

    def line_to_offset(self, line_num: int) -> int:
        """将行号（1-based）转换为该行首个字符在全文中的偏移量。"""
        lines = self._ensure_lines()
        if line_num < 1 or line_num > len(lines):
            raise IndexError(
                f"line number {line_num} out of range (1..{len(lines)})"
            )
        # 前面 line_num-1 行 + 它们之间的换行符
        return sum(len(l) + 1 for l in lines[:line_num - 1])

    def __repr__(self) -> str:
        return (
            f"TextDoc(lines={self.line_count()}, "
            f"chars={len(self._text)}, "
            f"encoding={self._encoding})"
        )
