"""
MissingBracketDetector — 缺失包裹符号检测器

启发式检测：某些文本行看起来像是对话（含说、道、问、答等特征词），
但没有任何包裹符号，可能是在 OCR 过程中丢失了「」。
"""

from __future__ import annotations

import re
from typing import List

from src.core.error_record import ErrorRecord
from src.core.text import TextDoc
from .base import BaseDetector


# 对话特征词（中文）
DIALOGUE_KEYWORDS = [
    "说", "道", "问", "答", "喊", "叫", "嚷", "骂", "吼",
    "告诉", "回答", "问道", "说道", "大喊", "小声说", "自言自语",
    "解释", "补充道", "接着说", "开口道", "应道", "笑道",
]

# 对话特征模式：某人道：「...」 或 某人说："..."
DIALOGUE_PATTERN = re.compile(
    r'(?:' + '|'.join(re.escape(k) for k in DIALOGUE_KEYWORDS) + r')[的着了过]?[：:\s]'
)

# 引号类符号（包括标准和非标准）
QUOTE_CHARS = set('「」""''\u201c\u201d\u2018\u2019【】[]（）()')


class MissingBracketDetector(BaseDetector):
    """
    检测疑似缺失包裹符号的对话。

    策略：对每一行文本，如果：
    1. 行内包含对话特征词（说、道、问等）
    2. 但没有任何引号类符号
    3. 行的长度适中（太长可能是叙述，太短可能是独立词）
    → 标记为"疑似缺失包裹符号"
    """

    name = "missing_bracket_detector"
    priority = 5  # P3: 低优先级

    # 最小行长度（太短不可能是对话）
    MIN_LINE_LENGTH = 8
    # 最大行长度（太长可能是叙述段落）
    MAX_LINE_LENGTH = 200

    def detect(self, text: TextDoc) -> List[ErrorRecord]:
        """扫描全文，返回疑似缺失包裹符号的错误记录。"""
        errors: List[ErrorRecord] = []
        full_text = text.text
        lines = text.lines()

        for line_num_0, line in enumerate(lines):
            line_num = line_num_0 + 1  # 1-based
            stripped = line.strip()

            # 长度过滤
            if len(stripped) < self.MIN_LINE_LENGTH:
                continue
            if len(stripped) > self.MAX_LINE_LENGTH:
                continue

            # 已包含引号 → 跳过
            if any(ch in stripped for ch in QUOTE_CHARS):
                continue

            # 检测特征词
            if not self._has_dialogue_keyword(stripped):
                continue

            # 检测是否像对话（以特征词结尾 + 冒号）
            if self._looks_like_dialogue_line(stripped):
                # 计算该行在全文中的偏移
                offset = sum(len(l) + 1 for l in lines[:line_num_0])
                errors.append(ErrorRecord(
                    error_type="missing_bracket",
                    line_number=line_num,
                    offset=offset,
                    context_before=full_text[offset - 80:offset],
                    context_after=full_text[offset + 1:offset + 81],
                    original_text=stripped[:100],
                ))

        return errors

    def _has_dialogue_keyword(self, text: str) -> bool:
        """检查文本是否包含对话特征词。"""
        return bool(DIALOGUE_PATTERN.search(text))

    def _looks_like_dialogue_line(self, text: str) -> bool:
        """
        进一步判断是否像对话行。

        特征：
        - 以"说道："、"问："、"回答："等模式结尾
        - 或包含"「"前常见的结构
        """
        # 以对话特征词 + 冒号结尾（如 "说道："、"问："）
        if DIALOGUE_PATTERN.search(text):
            # 检查冒号前后
            for keyword in DIALOGUE_KEYWORDS:
                idx = text.find(keyword)
                if idx != -1:
                    # 关键词后面有冒号或空格
                    after = text[idx + len(keyword):]
                    if after and after[0] in (":", "：", " ", "　"):
                        return True
        return False
