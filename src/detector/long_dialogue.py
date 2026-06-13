"""
LongDialogueDetector — 超长对话检测器

检测因漏符号导致旁白被错误合并到对话中的超长「」。
只负责找出这些超长对话的位置，是否拆分由 LLM 判断。
"""

from __future__ import annotations

import re
from typing import List, Optional

from src.core.error_record import ErrorRecord
from src.core.text import TextDoc
from .base import BaseDetector


# 匹配「」包裹的内容（含符号本身）
DIALOGUE_PATTERN = re.compile(r"「([^」]*)」")

# 默认的"超长"阈值（字符数，不含符号本身）
DEFAULT_MAX_LENGTH = 80


class LongDialogueDetector(BaseDetector):
    """
    检测超长「」对话。

    轻小说的对话通常较短。如果一段「」内的内容很长（>80 字符），
    很可能是因为中间缺失了」和「，导致旁白被错误地合并进了对话。

    注：这个检测器的结果不会直接给 LLM 修，而是作为一个
    "需要深度分析"的错误类型。LLM 需要阅读上下文后判断
    是否真的需要拆分。
    """

    name = "long_dialogue_detector"
    priority = 4  # P2: 中低优先级

    def __init__(self, max_length: int = DEFAULT_MAX_LENGTH, top_k: int = 20):
        """
        Args:
            max_length: 超过此长度的对话被视为"超长"
            top_k: 只返回最长的 top_k 个（防止噪声太多）
        """
        self.max_length = max_length
        self.top_k = top_k

    def detect(self, text: TextDoc) -> List[ErrorRecord]:
        """扫描全文，返回超长对话的错误记录。"""
        full_text = text.text

        # 提取所有「」对话
        dialogues: List[dict] = []
        for match in DIALOGUE_PATTERN.finditer(full_text):
            content = match.group(1)
            length = len(content)
            if length > self.max_length:
                offset = match.start()
                line_num = text.offset_to_line(offset)
                dialogues.append({
                    "content": content,
                    "length": length,
                    "offset": offset,
                    "line_number": line_num,
                    "end_offset": match.end(),
                })

        # 按长度降序排列，取 Top K
        dialogues.sort(key=lambda d: d["length"], reverse=True)
        top_dialogues = dialogues[:self.top_k]

        # 生成 ErrorRecord
        errors: List[ErrorRecord] = []
        for d in top_dialogues:
            offset = d["offset"]
            errors.append(ErrorRecord(
                error_type="long_dialogue",
                line_number=d["line_number"],
                offset=offset,
                context_before=full_text[offset - 80:offset],
                context_after=full_text[d["end_offset"]:d["end_offset"] + 80],
                original_text=full_text[offset:min(offset + 60, d["end_offset"])],
            ))

        return errors
