"""
ProgressTracker — 进度持久化与断点续跑

每次修正后自动保存 checkpoint，支持中断恢复。
Checkpoint 存储在项目根目录的 .checkpoint/ 文件夹下。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .error_record import ErrorRecord
from .error_queue import ErrorQueue


# ─── 文件结构 ──────────────────────────────────────────

# .checkpoint/
# ├── corrections.jsonl      # 每行一条修正记录（JSON）
# ├── progress.json          # 进度快照
# └── hard_indicators.json   # 硬性指标达标情况


@dataclass
class Checkpoint:
    """一次 checkpoint 快照。"""
    novel_path: str
    error_queue: ErrorQueue
    hard_indicators: dict
    timestamp: float

    def to_progress_dict(self) -> dict:
        return {
            "novel_path": self.novel_path,
            "progress": self.error_queue.progress(),
            "type_summary": self.error_queue.type_summary(),
            "hard_indicators": self.hard_indicators,
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
        }


class ProgressTracker:
    """
    进度追踪器。

    使用方式：
        tracker = ProgressTracker("data/ori_story/第1卷.txt")
        tracker.init_checkpoint(error_queue)  # 首次初始化
        ...
        tracker.save_correction(err, fix_result)  # 每修一条就保存
        tracker.update_progress(error_queue)       # 更新进度

    断点恢复：
        tracker = ProgressTracker("data/ori_story/第1卷.txt")
        if tracker.has_checkpoint():
            error_queue = tracker.load_checkpoint()
    """

    CHECKPOINT_DIR = ".checkpoint"

    def __init__(self, novel_path: str | Path, checkpoint_dir: str | Path | None = None):
        self.novel_path = str(Path(novel_path).resolve())
        self._checkpoint_dir = Path(checkpoint_dir or self.CHECKPOINT_DIR)

        # 为每本小说建立独立的子目录（用文件名做子目录名）
        novel_name = Path(self.novel_path).stem
        self._novel_dir = self._checkpoint_dir / novel_name

    # ── 路径 ────────────────────────────────────────────

    @property
    def corrections_path(self) -> Path:
        """修正记录文件路径。"""
        return self._novel_dir / "corrections.jsonl"

    @property
    def progress_path(self) -> Path:
        """进度快照路径。"""
        return self._novel_dir / "progress.json"

    @property
    def indicators_path(self) -> Path:
        """硬性指标路径。"""
        return self._novel_dir / "hard_indicators.json"

    # ── 初始化 ──────────────────────────────────────────

    def init_checkpoint(self, error_queue: ErrorQueue,
                        hard_indicators: Optional[dict] = None) -> None:
        """首次初始化 checkpoint 目录。"""
        self._novel_dir.mkdir(parents=True, exist_ok=True)

        # 写入初始进度
        cp = Checkpoint(
            novel_path=self.novel_path,
            error_queue=error_queue,
            hard_indicators=hard_indicators or {},
            timestamp=time.time(),
        )
        self._write_progress(cp)

        # 写入硬性指标
        if hard_indicators:
            self._write_indicators(hard_indicators)

        print(f"[checkpoint] initialized: {self._novel_dir}")

    # ── 保存 ────────────────────────────────────────────

    def save_correction(self, record: ErrorRecord,
                        fix_result: Optional[dict] = None) -> None:
        """保存一条修正记录到 corrections.jsonl。"""
        entry = {
            "error_id": record.error_id,
            "error_type": record.error_type,
            "line_number": record.line_number,
            "offset": record.offset,
            "original_text": record.original_text,
            "status": record.status,
            "fix_applied": record.fix_applied,
            "verifier_verdict": record.verifier_verdict,
            "verifier_reason": record.verifier_reason,
            "skip_reason": record.skip_reason,
            "fail_reason": record.fail_reason,
            "retry_count": record.retry_count,
            "timestamp": time.time(),
        }
        if fix_result:
            entry["fix_detail"] = fix_result

        self._novel_dir.mkdir(parents=True, exist_ok=True)
        with open(self.corrections_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def update_progress(self, error_queue: ErrorQueue,
                        hard_indicators: Optional[dict] = None) -> None:
        """更新进度快照。"""
        cp = Checkpoint(
            novel_path=self.novel_path,
            error_queue=error_queue,
            hard_indicators=hard_indicators or {},
            timestamp=time.time(),
        )
        self._write_progress(cp)
        if hard_indicators:
            self._write_indicators(hard_indicators)

    def _write_progress(self, cp: Checkpoint) -> None:
        self._novel_dir.mkdir(parents=True, exist_ok=True)
        data = cp.to_progress_dict()
        with open(self.progress_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _write_indicators(self, indicators: dict) -> None:
        with open(self.indicators_path, "w", encoding="utf-8") as f:
            json.dump(indicators, f, ensure_ascii=False, indent=2)

    # ── 加载 ────────────────────────────────────────────

    def has_checkpoint(self) -> bool:
        """检查是否存在 checkpoint。"""
        return self.progress_path.exists()

    def load_checkpoint(self) -> Optional[ErrorQueue]:
        """从 checkpoint 加载错误队列（过滤已处理的错误）。"""
        if not self.has_checkpoint():
            return None

        # 加载 progress.json 获取进度信息
        with open(self.progress_path, encoding="utf-8") as f:
            progress_data = json.load(f)

        # 加载 corrections.jsonl 重建已处理的错误
        fixed_ids: set[str] = set()
        corrections: list[dict] = []
        if self.corrections_path.exists():
            with open(self.corrections_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        corrections.append(entry)
                        fixed_ids.add(entry["error_id"])

        # 如果 corrections.jsonl 为空但有 progress 信息，说明是首次初始化
        if not corrections:
            return None

        # 根据 progress 中的进度信息重建 ErrorQueue
        # 注意：corrections.jsonl 只记录了已处理的错误，
        # 未处理的错误需要从检测器重新生成。
        # 这里我们返回一个带有进度信息的标记，让调用方知道
        # 哪些错误已经处理过了。
        result_queue = ErrorQueue()
        for entry in corrections:
            record = ErrorRecord.from_dict(entry)
            result_queue.add(record)

        return result_queue

    def load_corrections(self) -> List[dict]:
        """加载所有修正记录。"""
        if not self.corrections_path.exists():
            return []
        entries: list[dict] = []
        with open(self.corrections_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    # ── 进度查询 ────────────────────────────────────────

    def get_processed_ids(self) -> set[str]:
        """获取已经处理过的 error_id 集合（用于断点续跑时去重）。"""
        ids: set[str] = set()
        if self.corrections_path.exists():
            with open(self.corrections_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        ids.add(entry["error_id"])
        return ids

    def get_progress_summary(self) -> Optional[dict]:
        """获取进度摘要。"""
        if self.progress_path.exists():
            with open(self.progress_path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def get_indicators(self) -> Optional[dict]:
        """获取硬性指标达标情况。"""
        if self.indicators_path.exists():
            with open(self.indicators_path, encoding="utf-8") as f:
                return json.load(f)
        return None

    # ── 报告 ────────────────────────────────────────────

    def generate_report(self, error_queue: Optional[ErrorQueue] = None,
                        output_dir: str | Path | None = None) -> dict:
        """
        生成纠错报告。

        Args:
            error_queue: 完整的错误队列（包含未处理的错误）
            output_dir: 报告输出目录

        Returns:
            报告字典
        """
        corrections = self.load_corrections()
        progress = self.get_progress_summary() or {}
        indicators = self.get_indicators() or {}

        # 统计
        fixed = [c for c in corrections if c["status"] == "fixed"]
        skipped = [c for c in corrections if c["status"] == "skipped"]
        failed = [c for c in corrections if c["status"] == "failed"]

        report = {
            "novel": self.novel_path,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_errors": progress.get("progress", {}).get("total", 0),
                "fixed": len(fixed),
                "skipped": len(skipped),
                "failed": len(failed),
                "remaining": progress.get("progress", {}).get("remaining", 0),
            },
            "hard_indicators": indicators,
            "type_summary": progress.get("type_summary", {}),
            "corrections": fixed[-20:],   # 最近 20 条修正
            "skipped": skipped[-10:],     # 最近 10 条跳过
            "failed": failed[:10],        # 最近 10 条失败
        }

        # 写入文件
        if output_dir:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            report_path = out_path / "correction_report.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            report_path = out_path / "correction_report.txt"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(self._format_text_report(report))

        return report

    @staticmethod
    def _format_text_report(report: dict) -> str:
        """生成可读的文本报告。"""
        s = report["summary"]
        lines = [
            "=" * 50,
            f"  纠错报告 — {Path(report['novel']).name}",
            "=" * 50,
            "",
            f"  总错误数: {s['total_errors']}",
            f"  已修正:   {s['fixed']}",
            f"  已跳过:   {s['skipped']}",
            f"  失败:     {s['failed']}",
            f"  剩余:     {s['remaining']}",
            "",
            "  硬性指标:",
        ]
        for key, val in report.get("hard_indicators", {}).items():
            lines.append(f"    {key}: {'[OK]' if val else '[FAIL]'}")
        lines.append("")
        lines.append(f"  类型分布: {report.get('type_summary', {})}")
        lines.append("")
        lines.append(f"  生成时间: {report['generated_at']}")
        lines.append("=" * 50)
        return "\n".join(lines)

    # ── 清理 ────────────────────────────────────────────

    def clear(self) -> None:
        """清除 checkpoint（用于测试和重新开始）。"""
        if self._novel_dir.exists():
            import shutil
            shutil.rmtree(self._novel_dir)
            print(f"[checkpoint] cleared: {self._novel_dir}")
