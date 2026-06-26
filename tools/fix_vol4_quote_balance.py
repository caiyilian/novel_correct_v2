"""Fix Volume 4 quote balance issues caused by OCR right-boundary markers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第4卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
REPORT_PATH = Path("output") / "vol4_quote_balance_fix8_report.json"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"
OCR_ONE = "\u4e00"


def stats(text: str) -> dict:
    return {
        "left_quote": text.count(JP_LEFT),
        "right_quote": text.count(JP_RIGHT),
        "balanced_jp": text.count(JP_LEFT) == text.count(JP_RIGHT),
        "empty_dialogues": text.count(JP_LEFT + JP_RIGHT),
        "left_square": text.count("["),
        "right_square": text.count("]"),
    }


def context(text: str, offset: int, width: int = 90) -> str:
    return text[max(0, offset - width) : min(len(text), offset + width + 1)].replace("\n", "\\n")


def unmatched_left_offsets(text: str) -> list[int]:
    stack: list[int] = []
    for i, ch in enumerate(text):
        if ch == JP_LEFT:
            stack.append(i)
        elif ch == JP_RIGHT and stack:
            stack.pop()
    return stack


def main() -> int:
    text = TextLoader().load(str(CORRECTED_PATH)).text
    before = stats(text)
    starts = unmatched_left_offsets(text)
    if len(starts) != 3:
        raise ValueError(f"expected 3 unmatched left quotes, got {starts}")

    chars = list(text)
    applied = []
    for n, start in enumerate(starts, start=1):
        # The corrupted right boundary is the last OCR '一' before the first
        # newline after the unmatched opening quote.
        window = "".join(chars[start : start + 180])
        para_end = window.find("\n")
        if para_end < 0:
            para_end = len(window)
        rel = window[:para_end].rfind(OCR_ONE)
        if rel < 0:
            raise ValueError(f"no OCR right-boundary marker near {start}")
        offset = start + rel
        if chars[offset] != OCR_ONE:
            raise ValueError(f"offset guard failed at {offset}")
        before_context = context("".join(chars), offset)
        chars[offset] = JP_RIGHT
        after_context = context("".join(chars), offset)
        applied.append(
            {
                "case_id": f"vol4-fix8-balance-{n:04d}",
                "offset": offset,
                "original": OCR_ONE,
                "replacement": JP_RIGHT,
                "reason": "unmatched opening Japanese quote closed by OCR one-character marker",
                "context_before": before_context,
                "context_after": after_context,
            }
        )

    updated = "".join(chars)
    after = stats(updated)
    remaining_unmatched = unmatched_left_offsets(updated)
    if not after["balanced_jp"]:
        raise ValueError(f"Volume 4 still unbalanced after fixes: {after}")
    if remaining_unmatched:
        raise ValueError(f"unmatched left quotes remain: {remaining_unmatched}")
    if after["empty_dialogues"] != before["empty_dialogues"]:
        raise ValueError("empty dialogue count changed unexpectedly")
    if after["left_square"] or after["right_square"]:
        raise ValueError("square bracket residue regressed")

    CORRECTED_PATH.write_text(updated, encoding="utf-8")
    report = {
        "volume": VOL,
        "stage": "Fix 8",
        "corrected_path": str(CORRECTED_PATH),
        "modified_corrected_text": True,
        "answer_text_copied": False,
        "applied_count": len(applied),
        "before": before,
        "after": after,
        "applied": applied,
        "remaining_unmatched_left": remaining_unmatched,
        "guard_checks": {
            "offset_guard": "passed",
            "quote_balance_fixed": True,
            "square_brackets_still_zero": True,
            "empty_dialogues_unchanged": True,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
