"""
ConsecutiveDetector — 连续相同符号检测器

检测「「 和 」」连续出现的问题。
正确的交替模式应该是：…」他说道。「…
如果出现 …」他说道。」… 或 …「他说道。「… 则说明有错误。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from src.core.error_record import ErrorRecord
from src.core.text import TextDoc
from .base import BaseDetector


LEFT = "「"
RIGHT = "」"


class ConsecutiveDetector(BaseDetector):
    """
    检测全文中连续出现的相同「」符号。

    扫描逻辑：
    - 用 last_char 记录上一个出现的符号（初始为 RIGHT，期望第一个对话以 LEFT 开头）
    - 当遇到 LEFT 或 RIGHT 时，检查是否与 last_char 相同
    - 如果相同 → 连续符号错误
    - 如果不同 → 更新 last_char，继续
    """

    name = "consecutive_detector"
    priority = 1  # P0: 高优先级

    def detect(self, text: TextDoc) -> List[ErrorRecord]:
        """扫描全文，返回所有连续符号错误的记录。"""
        errors: List[ErrorRecord] = []
        full_text = text.text
        # 从 RIGHT 开始（期待第一个遇到的是 LEFT）
        last_char: Optional[str] = RIGHT
        last_offset: Optional[int] = None

        for offset, ch in enumerate(full_text):
            if ch not in (LEFT, RIGHT):
                continue

            if ch == last_char:
                # 发现了连续相同符号
                line_num = text.offset_to_line(offset)
                context_start = max(0, offset - 80)
                context_end = min(len(full_text), offset + 80)

                errors.append(ErrorRecord(
                    error_type="consecutive",
                    line_number=line_num,
                    offset=offset,
                    context_before=full_text[offset - 80:offset],
                    context_after=full_text[offset + 1:offset + 81],
                    original_text=full_text[max(0, offset - 5):offset + 6],
                ))

            # 更新状态
            last_char = ch
            last_offset = offset

        return errors
