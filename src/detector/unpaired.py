"""
UnpairedDetector — 不成对符号检测器

检测「和」数量不匹配的情况。用栈匹配算法定位多余的或缺失的符号。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from src.core.error_record import ErrorRecord
from src.core.text import TextDoc
from .base import BaseDetector


LEFT = "「"
RIGHT = "」"


class UnpairedDetector(BaseDetector):
    """
    检测「和」不成对的情况。

    用栈匹配算法：
    - 遇到「入栈
    - 遇到」出栈（如果栈为空，则这个」是多余的）
    - 扫描完毕后，栈中剩余的「就是缺失对应」的
    """

    name = "unpaired_detector"
    priority = 2  # P0: 高优先级

    def detect(self, text: TextDoc) -> List[ErrorRecord]:
        """扫描全文，返回所有不成对符号的错误记录。"""
        errors: List[ErrorRecord] = []
        full_text = text.text

        # 第一遍：计数总数
        left_count = full_text.count(LEFT)
        right_count = full_text.count(RIGHT)

        if left_count == right_count:
            return errors  # 数量相等，不需要进一步分析

        # 第二遍：用栈匹配找出具体位置
        stack: List[int] = []  # 存储「的偏移量
        extra_rights: List[int] = []  # 多余的」

        for offset, ch in enumerate(full_text):
            if ch == LEFT:
                stack.append(offset)
            elif ch == RIGHT:
                if stack:
                    stack.pop()  # 匹配到一个「」
                else:
                    extra_rights.append(offset)  # 多余的」

        # stack 中剩余的「是未匹配的
        unmatched_lefts = stack[:]

        # 生成 ErrorRecord
        for offset in extra_rights:
            line_num = text.offset_to_line(offset)
            errors.append(ErrorRecord(
                error_type="unpaired",
                line_number=line_num,
                offset=offset,
                context_before=full_text[offset - 80:offset],
                context_after=full_text[offset + 1:offset + 81],
                original_text=full_text[max(0, offset - 3):offset + 4],
            ))

        for offset in unmatched_lefts:
            line_num = text.offset_to_line(offset)
            errors.append(ErrorRecord(
                error_type="unpaired",
                line_number=line_num,
                offset=offset,
                context_before=full_text[offset - 80:offset],
                context_after=full_text[offset + 1:offset + 81],
                original_text=full_text[max(0, offset - 3):offset + 4],
            ))

        return errors
