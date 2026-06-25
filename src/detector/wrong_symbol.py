"""
WrongSymbolDetector — 非标准符号检测器

检测 [] 【】 ［］ “” "" 等非标准符号，这些符号可能是本应为「」
但被 OCR 识别错误或排版不当导致的。

注意：这些符号不一定都是对话包裹符，也可能是注释、标题、舞台指示等。
所以只负责检测和记录位置，是否替换由 LLM 判断。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from src.core.error_record import ErrorRecord
from src.core.text import TextDoc
from .base import BaseDetector


# 需要检测的非标准符号及其映射
# value 为 None 表示需要成对判断
TARGET_SYMBOLS: Dict[str, Optional[str]] = {
    "[": "「",       # 英文方括号开
    "]": "」",       # 英文方括号闭
    "【": "「",      # 中文方括号开（黑括号）
    "】": "」",      # 中文方括号闭
    "［": "「",      # 全角方括号开
    "］": "」",      # 全角方括号闭
    "{" : "「",       # 花括号开（偶尔 OCR 误识别）
    "}" : "」",       # 花括号闭
    "《": "「",      # 书名号开（偶尔误用）
    "》": "」",      # 书名号闭
    "\u201c": "「",   # 弯引号开（左双引号）
    "\u201d": "」",   # 弯引号闭（右双引号）
    '"' : None,       # ASCII 直引号（需要成对判断）
}

# 哪些开符号需要对应的闭符号才能算一对
PAIRED_OPENERS = {"[", "【", "［", "{", "《"}

# 对应的闭符号
CLOSER_MAP = {
    "[": "]", "【": "】", "［": "］",
    "{": "}", "《": "》",
}

CLOSER_TO_OPENER = {closer: opener for opener, closer in CLOSER_MAP.items()}

# 只跳过非常明确的非对话注释/标记。不要因为括号内容短就跳过，
# 小说对话里常见 [重要的事] 这类短文本，仍应交给后续流程判断。
EXPLICIT_COMMENT_LABELS = {"注", "插图", "图", "表", "序号"}


class WrongSymbolDetector(BaseDetector):
    """
    检测非标准符号（[] 【】 ［］ “” 等）。

    只记录位置和上下文，不直接替换。由 LLM 判断该符号在上下文中
    是否真的是对话包裹符。

    Stage 19b: 取消「」内部的跳过。所有非标准符号都标记，
    但通过 is_nested=True 区分（嵌套的降为低优先级）。
    """

    name = "wrong_symbol_detector"
    priority = 2  # P1: 中优先级

    def detect(self, text: TextDoc) -> List[ErrorRecord]:
        """扫描全文，返回所有非标准符号的错误记录。"""
        errors: List[ErrorRecord] = []
        full_text = text.text
        ascii_dq_open: Optional[int] = None  # ASCII 直引号配对的偏移量
        ascii_dq_open_nested: bool = False
        in_bracket_depth: int = 0  # 当前「」嵌套深度

        for offset, ch in enumerate(full_text):
            # 跟踪「」嵌套
            if ch == "「":
                in_bracket_depth += 1
                continue
            elif ch == "」":
                in_bracket_depth = max(0, in_bracket_depth - 1)
                continue
            # 判断当前符号是否在「」内部（Stage 19b: 不再跳过，只标记 is_nested）
            is_nested = in_bracket_depth > 0

            # 处理 ASCII 直引号（需要成对匹配）
            if ch == '"':
                if ascii_dq_open is None:
                    # 开引号
                    ascii_dq_open = offset
                    ascii_dq_open_nested = is_nested
                else:
                    # 闭引号，记录一对
                    close_offset = offset
                    open_offset = ascii_dq_open
                    ascii_dq_open = None
                    # 检查引号内是否包含中文（是才可能是对话）
                    content = full_text[open_offset + 1:close_offset]
                    if self._looks_like_dialogue(content):
                        errors.extend(self._make_ascii_dq_errors(
                            text, full_text, open_offset, close_offset, content, is_nested=is_nested))
                continue

            # 处理单个符号
            if ch in TARGET_SYMBOLS and ch != '"':
                # 跳过已知的成对括号内的内容（避免重复检测同一个括号两次）
                # 检查这个符号前后是否可能是对话
                if not self._should_skip(text, full_text, offset, ch):
                    errors.append(self._make_error(text, full_text, offset, ch, is_nested=is_nested))

        if ascii_dq_open is not None:
            errors.append(self._make_error(
                text, full_text, ascii_dq_open, '"', is_nested=ascii_dq_open_nested))

        return errors

    def _looks_like_dialogue(self, content: str) -> bool:
        """通过内容特征判断是否可能是对话。"""
        if not content:
            return False
        # 包含中文
        has_cjk = any('\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff'
                      for c in content)
        if not has_cjk:
            return False
        # 太长的内容可能是注释或段落，不是简短对话
        if len(content) > 200:
            return False
        return True

    def _looks_like_paired_bracket(self, text: str, offset: int, ch: str) -> bool:
        """检查符号是否是明确注释/标记（如 [1]、【注】）。"""
        if ch in PAIRED_OPENERS:
            closer = CLOSER_MAP.get(ch)
            if closer:
                rest = text[offset + 1:offset + 50]
                close_pos = rest.find(closer)
                if close_pos != -1 and close_pos < 20:
                    return self._is_explicit_comment_label(rest[:close_pos])
        elif ch in CLOSER_TO_OPENER:
            opener = CLOSER_TO_OPENER[ch]
            before = text[max(0, offset - 50):offset]
            open_pos = before.rfind(opener)
            if open_pos != -1 and len(before) - open_pos < 20:
                return self._is_explicit_comment_label(before[open_pos + 1:])
        return False

    @staticmethod
    def _is_explicit_comment_label(inner: str) -> bool:
        """只识别固定注释标签或纯数字脚注。"""
        label = inner.strip()
        return label.isdigit() or label in EXPLICIT_COMMENT_LABELS

    def _should_skip(self, text_doc: TextDoc, full_text: str,
                     offset: int, ch: str) -> bool:
        """判断是否应该跳过该符号（可能是注释/标题等非对话用途）。"""
        # 检查是否是成对短括号（如 [1]、【注】）
        if self._looks_like_paired_bracket(full_text, offset, ch):
            return True

        # 检查是否在明显的非对话上下文中
        before = full_text[max(0, offset - 5):offset]
        # 行首的 【】 可能是标题标记
        if ch in ("【", "】") and '\n' in before:
            return True

        return False

    def _make_error(self, text_doc: TextDoc, full_text: str,
                    offset: int, ch: str, is_nested: bool = False) -> ErrorRecord:
        """为单个非标准符号创建 ErrorRecord。"""
        line_num = text_doc.offset_to_line(offset)
        context_start = max(0, offset - 80)
        context_end = min(len(full_text), offset + 80)

        return ErrorRecord(
            error_type="wrong_symbol",
            line_number=line_num,
            offset=offset,
            context_before=full_text[offset - 80:offset],
            context_after=full_text[offset + 1:offset + 81],
            original_text=full_text[max(0, offset - 3):offset + 4],
            is_nested=is_nested,
        )

    def _make_ascii_dq_errors(self, text_doc: TextDoc, full_text: str,
                               open_offset: int, close_offset: int,
                               content: str, is_nested: bool = False) -> List[ErrorRecord]:
        """为一对 ASCII 引号创建 ErrorRecord。"""
        errors: List[ErrorRecord] = []

        for offset, ch in [(open_offset, '"'), (close_offset, '"')]:
            line_num = text_doc.offset_to_line(offset)
            errors.append(ErrorRecord(
                error_type="wrong_symbol",
                line_number=line_num,
                offset=offset,
                context_before=full_text[offset - 80:offset],
                context_after=full_text[offset + 1:offset + 81],
                original_text=full_text[max(0, offset - 3):offset + 4],
                is_nested=is_nested,
            ))

        return errors
