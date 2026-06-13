"""
ErrorRecord — 纠错任务的核心数据单元

每个 ErrorRecord 代表一个由规则检测器定位到的潜在错误，
包含错误位置、类型、上下文、状态和修正记录等信息。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── 错误类型 ───────────────────────────────────────────


class ErrorType(str, Enum):
    """错误类型枚举，按检测器优先级排列。"""
    CONSECUTIVE = "consecutive"           # 「「 或 」」连续出现
    UNPAIRED = "unpaired"                 # 「 和 」不成对
    WRONG_SYMBOL = "wrong_symbol"         # [] 【】 “” 等非标准符号
    LONG_DIALOGUE = "long_dialogue"       # 超长对话（可能漏符号合并了旁白）
    MISSING_BRACKET = "missing_bracket"   # 对话疑似缺失包裹符号


# ─── 错误状态 ───────────────────────────────────────────


class ErrorStatus(str, Enum):
    """错误处理状态。"""
    PENDING = "pending"       # 待处理
    FIXED = "fixed"           # 已修正（Verifier 确认通过）
    SKIPPED = "skipped"       # 已跳过（LLM 判断不是错误或不确定）
    FAILED = "failed"         # 修正失败（Verifier 不通过或 Agent 多次重试失败）


# ─── Verifier 判定 ──────────────────────────────────────


class VerifierVerdict(str, Enum):
    """Verifier 对修正的判定结果。"""
    PENDING = "pending"       # 尚未验证
    PASS = "pass"             # 修正合理
    FAIL = "fail"             # 修正不合理
    UNCERTAIN = "uncertain"   # 不确定


# ─── ErrorRecord ────────────────────────────────────────


@dataclass
class ErrorRecord:
    """
    一个潜在错误的完整记录。

    由规则检测器创建，经过 Agent 修正和 Verifier 验证后更新状态。
    """

    # ── 标识 ──
    error_id: str = ""
    """全局唯一错误 ID，格式 'e-0001'。留空则自动生成。"""

    error_type: str = ""
    """错误类型，对应 ErrorType 的 value。"""

    # ── 位置 ──
    line_number: int = 0
    """错误所在行号（1-based）。"""

    offset: int = 0
    """错误在全文中的字符偏移量。"""

    # ── 上下文 ──
    context_before: str = ""
    """错误前的上下文文本（约 100 字符）。"""

    context_after: str = ""
    """错误后的上下文文本（约 100 字符）。"""

    original_text: str = ""
    """包含错误的内容片段。"""

    # ── 状态 ──
    status: str = ErrorStatus.PENDING.value
    """当前处理状态。"""

    fix_applied: str = ""
    """实际应用的修正内容（仅当 status=fixed 时有效）。"""

    verifier_verdict: str = VerifierVerdict.PENDING.value
    """Verifier 的判定结果。"""

    verifier_reason: str = ""
    """Verifier 判定的理由。"""

    skip_reason: str = ""
    """跳过的原因（仅当 status=skipped 时有效）。"""

    fail_reason: str = ""
    """失败的原因（仅当 status=failed 时有效）。"""

    # ── 元信息 ──
    created_at: float = 0.0
    """记录创建时间（time.time()）。"""

    retry_count: int = 0
    """已重试次数。"""

    # ── ID 生成 ──
    _id_counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._id_counter += 1
        return f"e-{cls._id_counter:04d}"

    def __post_init__(self) -> None:
        if not self.error_id:
            self.error_id = self._next_id()
        if not self.created_at:
            import time
            self.created_at = time.time()

    # ── 便利方法 ──

    def mark_fixed(self, fix: str, verdict: str = VerifierVerdict.PASS.value,
                   reason: str = "") -> None:
        """标记为已修正。"""
        self.status = ErrorStatus.FIXED.value
        self.fix_applied = fix
        self.verifier_verdict = verdict
        self.verifier_reason = reason

    def mark_skipped(self, reason: str) -> None:
        """标记为跳过。"""
        self.status = ErrorStatus.SKIPPED.value
        self.skip_reason = reason

    def mark_failed(self, reason: str) -> None:
        """标记为失败。"""
        self.status = ErrorStatus.FAILED.value
        self.fail_reason = reason

    @property
    def is_resolved(self) -> bool:
        """是否已处理完毕（不论成功还是跳过/失败）。"""
        return self.status != ErrorStatus.PENDING.value

    @property
    def summary(self) -> str:
        """一行摘要。"""
        return (
            f"[{self.error_id}] L{self.line_number} "
            f"type={self.error_type} status={self.status} "
            f"text={self.original_text[:40]!r}"
        )

    def to_dict(self) -> dict:
        """序列化为字典（用于 JSON 报告和 checkpoint）。"""
        return {
            "error_id": self.error_id,
            "error_type": self.error_type,
            "line_number": self.line_number,
            "offset": self.offset,
            "context_before": self.context_before[-100:],
            "context_after": self.context_after[:100],
            "original_text": self.original_text,
            "status": self.status,
            "fix_applied": self.fix_applied,
            "verifier_verdict": self.verifier_verdict,
            "verifier_reason": self.verifier_reason,
            "skip_reason": self.skip_reason,
            "fail_reason": self.fail_reason,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ErrorRecord:
        """从字典反序列化。"""
        return cls(**{k: v for k, v in data.items()
                      if k in cls.__dataclass_fields__})
