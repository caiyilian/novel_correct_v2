"""
TextLoader — 文本加载器

自动检测文件编码（UTF-8 → UTF-16 LE/BE → GBK），
去除 BOM，统一换行符，返回 TextDoc 实例。
"""

from __future__ import annotations

import codecs
import os
from pathlib import Path
from typing import List, Optional, Tuple

from src.core.text import TextDoc


# ─── 编码检测优先级 ────────────────────────────────────

# 每种编码的检测方式：(名称, 是否需 BOM)
# UTF-16 有 BOM，优先检测
_PRIORITY_WITH_BOM: List[Tuple[str, str]] = [
    ("utf-8-sig", "\ufeff"),       # UTF-8 with BOM
    ("utf-16-le", "\ufffe"),        # UTF-16 LE BOM (little-endian)
    ("utf-16-be", "\ufeff"),        # UTF-16 BE BOM (big-endian)
]

# 无 BOM 时的备选编码（按优先级）
_FALLBACK_ENCODINGS = [
    "utf-8",
    "gbk",
    "gb2312",
    "gb18030",
    "utf-16-le",
    "utf-16-be",
    "shift-jis",
    "euc-jp",
]


# ─── 错误类型 ────────────────────────────────────────────


class LoaderError(IOError):
    """文本加载失败时抛出。"""


# ─── TextLoader ─────────────────────────────────────────


class TextLoader:
    """文本加载器，自动检测编码并返回 TextDoc。"""

    def __init__(self, fallback_encodings: Optional[List[str]] = None):
        self._fallback_encodings = fallback_encodings or _FALLBACK_ENCODINGS

    def load(self, path: str | Path) -> TextDoc:
        """
        加载文本文件。

        流程：
        1. 检查文件是否存在
        2. 通过 BOM 或逐编码尝试检测编码
        3. 去除 BOM
        4. 统一换行符 \r\n → \n
        5. 返回 TextDoc
        """
        path = Path(path).expanduser().resolve()

        if not path.exists():
            raise LoaderError(f"file not found: {path}")
        if not path.is_file():
            raise LoaderError(f"path is not a file: {path}")

        # 读取原始字节
        raw_bytes = self._read_raw_bytes(path)

        # 检测编码
        encoding, text = self._detect_and_decode(raw_bytes)

        # 去除 BOM
        text = self._strip_bom(text, encoding)

        # 统一换行符
        text = self._normalize_newlines(text)

        return TextDoc(text=text, encoding=encoding, path=str(path))

    # ─── 内部方法 ─────────────────────────────────────────

    def _read_raw_bytes(self, path: Path) -> bytes:
        """以二进制模式读取文件。"""
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError as e:
            raise LoaderError(f"cannot read file: {e}") from e

    def _detect_and_decode(self, raw: bytes) -> Tuple[str, str]:
        """
        检测编码并解码。

        先检查 BOM，再尝试 fallback 编码列表。
        """
        # 1. 先尝试有 BOM 的编码
        for enc_name, bom in _PRIORITY_WITH_BOM:
            bom_bytes = bom.encode("utf-16-le") if "utf-16" in enc_name else bom.encode("utf-8")
            if raw[:len(bom_bytes)] == bom_bytes:
                try:
                    text = raw.decode(enc_name, errors="strict")
                    # 统一编码名称
                    normalized = self._normalize_encoding_name(enc_name)
                    return normalized, text
                except (UnicodeDecodeError, LookupError):
                    continue

        # 2. 尝试 UTF-16 无 BOM 检测（通过空字节比例）
        if self._looks_like_utf16(raw):
            for enc in ["utf-16-le", "utf-16-be"]:
                try:
                    text = raw.decode(enc, errors="strict")
                    return enc, text
                except UnicodeDecodeError:
                    continue

        # 3. 尝试 fallback 编码列表
        for enc in self._fallback_encodings:
            try:
                text = raw.decode(enc, errors="strict")
                return enc, text
            except (UnicodeDecodeError, LookupError):
                continue

        # 4. 最后手段：用 UTF-8 带替换
        try:
            text = raw.decode("utf-8", errors="replace")
            print(f"[warning] fallback to utf-8 with replacement")
            return "utf-8", text
        except Exception as e:
            raise LoaderError(
                f"cannot decode file with any known encoding: {e}"
            ) from e

    def _looks_like_utf16(self, raw: bytes) -> bool:
        """通过空字节比例判断是否可能是 UTF-16。"""
        if len(raw) < 4:
            return False
        # 如果是 UTF-16 LE，偶数索引（0, 2, 4...）应该是空字节
        # 但这只适用于纯 ASCII 范围的内容
        null_count = sum(1 for b in raw if b == 0)
        return null_count > len(raw) * 0.2

    @staticmethod
    def _strip_bom(text: str, encoding: str) -> str:
        """去除 BOM 字符。"""
        if text and text[0] == "\ufeff":
            return text[1:]
        return text

    @staticmethod
    def _normalize_newlines(text: str) -> str:
        """统一换行符：\r\n → \n，单独的 \r → \n。"""
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        return text

    @staticmethod
    def _normalize_encoding_name(enc: str) -> str:
        """将编码名称归一化为小写。"""
        name = enc.lower().replace("-", "")
        # 别名映射
        aliases = {
            "utf8sig": "utf-8",
            "utf8": "utf-8",
            "utf16le": "utf-16-le",
            "utf16be": "utf-16-be",
        }
        return aliases.get(name, enc)


# ─── 便利函数 ────────────────────────────────────────────


def load_text(path: str | Path) -> TextDoc:
    """便利函数：一行代码加载文本。"""
    return TextLoader().load(path)
