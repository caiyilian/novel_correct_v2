"""
DetectorPipeline — 检测器编排流水线

按优先级顺序运行所有规则检测器，合并结果到 ErrorQueue。
支持通过 ProgressTracker 过滤已处理的错误（断点续跑）。
"""

from __future__ import annotations

from typing import List, Optional, Type

from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.core.progress import ProgressTracker
from src.core.text import TextDoc
from src.detector.base import BaseDetector
from src.detector.consecutive import ConsecutiveDetector
from src.detector.unpaired import UnpairedDetector
from src.detector.wrong_symbol import WrongSymbolDetector
from src.detector.long_dialogue import LongDialogueDetector
from src.detector.missing_bracket import MissingBracketDetector


class DetectorPipeline:
    """
    检测器编排流水线。

    自动注册所有检测器，按优先级顺序运行（P0 → P1 → P2 → P3），
    合并结果到 ErrorQueue。
    """

    # 默认注册的检测器（按优先级顺序）
    DEFAULT_DETECTORS = [
        ConsecutiveDetector,   # P0: 连续符号
        UnpairedDetector,      # P0: 不成对
        WrongSymbolDetector,   # P1: 非标准符号
        LongDialogueDetector,  # P2: 超长对话
        MissingBracketDetector, # P3: 缺失符号
    ]

    def __init__(self, detectors: Optional[List[BaseDetector]] = None):
        """
        Args:
            detectors: 检测器实例列表。为 None 则使用默认列表。
        """
        self.detectors = detectors or [
            cls() for cls in self.DEFAULT_DETECTORS
        ]
        # 按优先级排序
        self.detectors.sort(key=lambda d: d.priority)

    # ── 核心接口 ───────────────────────────────────────

    def run(self, text: TextDoc) -> ErrorQueue:
        """
        运行所有检测器，返回合并后的 ErrorQueue。

        Args:
            text: 已加载的文本文档。

        Returns:
            包含所有检测到的错误的 ErrorQueue。
        """
        queue = ErrorQueue()

        for detector in self.detectors:
            errors = detector.detect(text)
            queue.extend(errors)

        return queue

    def run_with_checkpoint(
        self,
        text: TextDoc,
        tracker: ProgressTracker,
    ) -> ErrorQueue:
        """
        运行检测器并过滤已处理的错误（支持 checkpoint 恢复）。

        1. 运行所有检测器
        2. 从 checkpoint 获取已处理的 error_id
        3. 过滤掉已处理的错误
        4. 如果 checkpoint 不存在，初始化一个新 checkpoint

        Args:
            text: 已加载的文本文档。
            tracker: ProgressTracker 实例。

        Returns:
            过滤后的 ErrorQueue（只包含尚未处理的错误）。
        """
        # 全量检测
        queue = self.run(text)

        if tracker.has_checkpoint():
            # 加载已处理的 ID，过滤
            processed_ids = tracker.get_processed_ids()
            if processed_ids:
                filtered = ErrorQueue()
                for err in queue:
                    if err.error_id not in processed_ids:
                        filtered.add(err)
                return filtered
            return queue
        else:
            # 首次运行，初始化 checkpoint
            tracker.init_checkpoint(queue)
            return queue

    # ── 统计 ────────────────────────────────────────────

    def run_with_stats(self, text: TextDoc) -> dict:
        """
        运行检测器并返回详细统计。

        Returns:
            {
                "total": int,
                "by_type": {"consecutive": int, ...},
                "by_detector": [
                    {"name": str, "count": int, "priority": int},
                ]
            }
        """
        queue = self.run(text)
        by_detector = []
        for detector in self.detectors:
            name = detector.name
            priority = detector.priority
            count = sum(1 for e in queue if e.error_type == self._error_type_for(detector))
            by_detector.append({
                "name": name,
                "priority": priority,
                "count": count,
            })

        return {
            "total": queue.total,
            "by_type": queue.type_summary(),
            "by_detector": by_detector,
            "queue": queue,
        }

    @staticmethod
    def _error_type_for(detector: BaseDetector) -> str:
        """根据检测器推断对应的 error_type。"""
        name = detector.name
        mapping = {
            "consecutive_detector": "consecutive",
            "unpaired_detector": "unpaired",
            "wrong_symbol_detector": "wrong_symbol",
            "long_dialogue_detector": "long_dialogue",
            "missing_bracket_detector": "missing_bracket",
        }
        return mapping.get(name, name)

    def __repr__(self) -> str:
        detectors_str = ", ".join(d.name for d in self.detectors)
        return f"<DetectorPipeline: [{detectors_str}]>"
