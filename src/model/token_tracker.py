"""Token usage tracking for model calls."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.model.client import TokenUsage


@dataclass(frozen=True)
class TokenRecord:
    timestamp: float
    source: str
    error_id: str
    error_type: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    context_window_pct: float


class TokenTracker:
    """Collect and persist token usage from LLM calls."""

    def __init__(self, context_limit: int = 40960):
        self._context_limit = max(1, context_limit)
        self._records: list[TokenRecord] = []

    @property
    def records(self) -> list[TokenRecord]:
        return list(self._records)

    @property
    def total_tokens(self) -> int:
        return sum(record.total_tokens for record in self._records)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(record.prompt_tokens for record in self._records)

    @property
    def total_completion_tokens(self) -> int:
        return sum(record.completion_tokens for record in self._records)

    def record(
        self,
        source: str,
        error_id: str,
        error_type: str,
        usage: TokenUsage,
    ) -> TokenRecord:
        record = TokenRecord(
            timestamp=time.time(),
            source=source,
            error_id=error_id,
            error_type=error_type,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            context_window_pct=round(
                usage.prompt_tokens / self._context_limit * 100,
                2,
            ),
        )
        self._records.append(record)
        return record

    def to_json(self) -> dict:
        return {
            "context_limit": self._context_limit,
            "total_records": len(self._records),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "records": [asdict(record) for record in self._records],
        }

    def save(self, path: str | Path = "output/token_usage.json") -> None:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, ensure_ascii=False, indent=2)
