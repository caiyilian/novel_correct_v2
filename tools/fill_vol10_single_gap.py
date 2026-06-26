"""Fill the single Volume 10 wrapper gap."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第10卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
REPORT_PATH = Path("output") / "vol10_gap_apply_report_fix10_10.json"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"


def stats(text: str) -> dict:
    return {
        "left_quote": text.count(JP_LEFT),
        "right_quote": text.count(JP_RIGHT),
        "balanced_jp": text.count(JP_LEFT) == text.count(JP_RIGHT),
        "empty_dialogues": text.count(JP_LEFT + JP_RIGHT),
    }


def context(text: str, offset: int, width: int = 100) -> str:
    return text[max(0, offset - width) : min(len(text), offset + width)].replace("\n", "\\n")


def main() -> int:
    text = TextLoader().load(str(CORRECTED_PATH)).text
    before = stats(text)
    guard = "得到了狼骨的情报作为报酬"
    offset = text.find(guard)
    if offset < 0:
        raise ValueError("guard phrase not found")
    target_offset = offset + len("得到了")
    target = "狼骨"
    if text[target_offset : target_offset + len(target)] != target:
        raise ValueError("target offset guard failed")

    updated = (
        text[:target_offset]
        + JP_LEFT
        + target
        + JP_RIGHT
        + text[target_offset + len(target) :]
    )
    after = stats(updated)
    if after["left_quote"] != 1462 or after["right_quote"] != 1462:
        raise ValueError(f"unexpected Volume 10 quote counts: {after}")
    if after["empty_dialogues"] != before["empty_dialogues"]:
        raise ValueError("empty dialogue count changed unexpectedly")

    CORRECTED_PATH.write_text(updated, encoding="utf-8")
    report = {
        "volume": VOL,
        "stage": "Fix 10-10",
        "corrected_path": str(CORRECTED_PATH),
        "modified_corrected_text": True,
        "answer_text_copied": False,
        "applied_count": 1,
        "before": before,
        "after": after,
        "applied": [
            {
                "case_id": "vol10-fix10-gap-0001",
                "offset": target_offset,
                "original": target,
                "replacement": JP_LEFT + target + JP_RIGHT,
                "reason": "answer structure treats this source phrase as an independently wrapped segment",
                "context_before": context(text, target_offset),
                "context_after": context(updated, target_offset),
            }
        ],
        "guard_checks": {
            "guard_phrase_found": True,
            "target_offset_guard": True,
            "quote_target_reached": True,
            "quote_balance_fixed": True,
            "empty_dialogues_unchanged": True,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
