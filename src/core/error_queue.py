"""
ErrorQueue — 错误队列

管理所有检测到的 ErrorRecord，按位置排序，支持去重、跳过、标记处理状态。
"""

from __future__ import annotations

import json
from typing import Dict, Iterator, List, Optional

from .error_record import ErrorRecord, ErrorStatus


class ErrorQueue:
    """
    错误队列。

    按 offset 升序排列，同一个位置附近的错误（50 字符内）自动合并。
    支持迭代、进度查询、断点续跑。
    """

    # 合并半径：两个错误 offset 差小于此值视为同一位置
    MERGE_RADIUS = 50

    def __init__(self, errors: Optional[List[ErrorRecord]] = None):
        self._errors: Dict[str, ErrorRecord] = {}  # error_id -> record
        self._sorted_ids: List[str] = []            # 按 offset 排序的 ID 列表

        if errors:
            for err in errors:
                self.add(err)

    # ── 添加 ────────────────────────────────────────────

    def add(self, record: ErrorRecord) -> None:
        """添加一个错误记录。如果在合并半径内有已有的记录，则合并。"""
        if record.error_id in self._errors:
            return  # 已存在

        # 检查合并半径
        merge_target = self._find_merge_target(record.offset)
        if merge_target is not None:
            # 合并到已有记录：保留更严重的问题
            existing = self._errors[merge_target]
            # 优先级：wrong_symbol > unpaired > consecutive > long_dialogue > missing_bracket
            priority = {
                "wrong_symbol": 0, "unpaired": 1, "consecutive": 2,
                "long_dialogue": 3, "missing_bracket": 4,
            }
            if priority.get(record.error_type, 99) < priority.get(existing.error_type, 99):
                # 新错误类型更严重，替换
                self._errors[merge_target] = record
            return

        self._errors[record.error_id] = record
        self._sorted_ids.append(record.error_id)
        self._sort()

    def extend(self, records: List[ErrorRecord]) -> None:
        """批量添加。"""
        for r in records:
            self.add(r)

    def _find_merge_target(self, offset: int) -> Optional[str]:
        """在合并半径内查找已有的错误 ID。"""
        for eid in self._sorted_ids:
            existing = self._errors[eid]
            if existing.status == ErrorStatus.PENDING.value:
                if abs(existing.offset - offset) <= self.MERGE_RADIUS:
                    return eid
        return None

    def _sort(self) -> None:
        """按 offset 升序排序。"""
        self._sorted_ids.sort(key=lambda eid: self._errors[eid].offset)

    # ── 获取 ────────────────────────────────────────────

    def next_pending(self) -> Optional[ErrorRecord]:
        """获取下一个待处理的错误（status=pending）。"""
        for eid in self._sorted_ids:
            err = self._errors[eid]
            if err.status == ErrorStatus.PENDING.value:
                return err
        return None

    def get(self, error_id: str) -> Optional[ErrorRecord]:
        """通过 error_id 获取错误记录（遍历查找，兼容 merge 后 key 不一致）。"""
        for eid, err in self._errors.items():
            if err.error_id == error_id:
                return err
        return None

    def all(self) -> List[ErrorRecord]:
        """获取所有错误记录（按 offset 排序）。"""
        return [self._errors[eid] for eid in self._sorted_ids]

    def pending(self) -> List[ErrorRecord]:
        """获取所有待处理的错误。"""
        return [err for err in self.all()
                if err.status == ErrorStatus.PENDING.value]

    def __iter__(self) -> Iterator[ErrorRecord]:
        return iter(self.all())

    def __len__(self) -> int:
        return len(self._errors)

    def __bool__(self) -> bool:
        return len(self._errors) > 0

    # ── 状态更新 ────────────────────────────────────────

    def mark_fixed(self, error_id: str, fix: str = "",
                   verdict: str = "pass", reason: str = "") -> None:
        """标记一条错误为已修复（按 error_id 遍历查找，兼容 merge 后 key 不一致）。"""
        for eid, err in self._errors.items():
            if err.error_id == error_id:
                err.mark_fixed(fix, verdict, reason)
                return

    def mark_skipped(self, error_id: str, reason: str = "") -> None:
        """标记一条错误为跳过（按 error_id 遍历查找）。"""
        for eid, err in self._errors.items():
            if err.error_id == error_id:
                err.mark_skipped(reason)
                return

    def mark_failed(self, error_id: str, reason: str = "") -> None:
        """标记一条错误为失败（按 error_id 遍历查找）。"""
        for eid, err in self._errors.items():
            if err.error_id == error_id:
                err.mark_failed(reason)
                return

    # ── 进度查询 ────────────────────────────────────────

    def progress(self) -> dict:
        """返回进度统计。"""
        counts = {"total": 0, "pending": 0, "fixed": 0,
                  "skipped": 0, "failed": 0}
        counts["total"] = len(self._errors)
        for err in self._errors.values():
            if err.status in counts:
                counts[err.status] += 1
        counts["remaining"] = counts["pending"]
        counts["done"] = counts["total"] - counts["remaining"]
        counts["percent"] = (
            (counts["done"] / counts["total"] * 100)
            if counts["total"] > 0 else 100.0
        )
        return counts

    def remaining(self) -> int:
        """剩余待处理数。"""
        return self.progress()["remaining"]

    @property
    def total(self) -> int:
        """错误总数。"""
        return len(self._errors)

    # ── 持久化 ──────────────────────────────────────────

    def to_dict_list(self) -> list:
        """序列化为字典列表（用于 checkpoint）。"""
        return [err.to_dict() for err in self.all()]

    @classmethod
    def from_dict_list(cls, data: list) -> ErrorQueue:
        """从字典列表反序列化。"""
        records = [ErrorRecord.from_dict(d) for d in data]
        return cls(records)

    def to_json(self, indent: int = 2) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict_list(), ensure_ascii=False, indent=indent)

    # ── 过滤 ────────────────────────────────────────────

    def by_type(self, error_type: str) -> List[ErrorRecord]:
        """按错误类型过滤。"""
        return [err for err in self.all() if err.error_type == error_type]

    def by_status(self, status: str) -> List[ErrorRecord]:
        """按状态过滤。"""
        return [err for err in self.all() if err.status == status]

    # ── 统计 ────────────────────────────────────────────

    def type_summary(self) -> dict:
        """按类型统计错误分布。"""
        summary: dict = {}
        for err in self.all():
            t = err.error_type
            summary[t] = summary.get(t, 0) + 1
        return summary

    @classmethod
    def reset_counter(cls) -> None:
        """重置自动 ID 计数器。"""
        ErrorRecord._id_counter = 0
