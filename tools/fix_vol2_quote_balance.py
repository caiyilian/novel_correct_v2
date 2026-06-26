"""Fix the remaining Volume 2 quote imbalance after bracket normalization."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第2卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
REPORT_PATH = Path("output") / "vol2_quote_balance_fix6_report.json"
WHITELIST_PATH = Path("output") / "vol2_nonstandard_whitelist_fix6.json"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"
INNER_RIGHT = "\u300f"


def stats(text: str) -> dict:
    return {
        "left_quote": text.count(JP_LEFT),
        "right_quote": text.count(JP_RIGHT),
        "balanced_jp": text.count(JP_LEFT) == text.count(JP_RIGHT),
        "empty_dialogues": text.count(JP_LEFT + JP_RIGHT),
        "left_square": text.count("["),
        "right_square": text.count("]"),
        "curly_left": text.count("\u201c"),
        "curly_right": text.count("\u201d"),
    }


def context(text: str, offset: int, width: int = 90) -> str:
    return text[max(0, offset - width) : min(len(text), offset + width + 1)].replace("\n", "\\n")


def unmatched_quote_offsets(text: str) -> dict:
    stack = []
    unmatched_right = []
    for i, ch in enumerate(text):
        if ch == JP_LEFT:
            stack.append(i)
        elif ch == JP_RIGHT:
            if stack:
                stack.pop()
            else:
                unmatched_right.append(i)
    return {
        "unmatched_left": stack,
        "unmatched_right": unmatched_right,
    }


def main() -> int:
    text = TextLoader().load(str(CORRECTED_PATH)).text
    before = stats(text)
    before_unmatched = unmatched_quote_offsets(text)

    target = "「不然要顺便听听布道吗?』"
    offset = text.find(target)
    if offset < 0:
        raise ValueError("target imbalance pattern not found")
    replace_offset = offset + len(target) - 1
    if text[replace_offset] != INNER_RIGHT:
        raise ValueError("offset guard failed for inner quote replacement")

    chars = list(text)
    chars[replace_offset] = JP_RIGHT
    updated = "".join(chars)
    after = stats(updated)
    after_unmatched = unmatched_quote_offsets(updated)

    if not after["balanced_jp"]:
        raise ValueError("Volume 2 still has unbalanced Japanese quotes")
    if after["empty_dialogues"] != before["empty_dialogues"]:
        raise ValueError("empty dialogue count changed unexpectedly")
    if after["left_square"] or after["right_square"]:
        raise ValueError("square bracket residue regressed")

    curly_items = [
        {
            "offset": i,
            "symbol": ch,
            "decision": "whitelist",
            "reason": "ordinary inline narration quote, not a dialogue wrapper",
            "context": context(updated, i),
        }
        for i, ch in enumerate(updated)
        if ch in "\u201c\u201d"
    ]
    WHITELIST_PATH.write_text(json.dumps(curly_items, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "volume": VOL,
        "stage": "Fix 6",
        "corrected_path": str(CORRECTED_PATH),
        "modified_corrected_text": True,
        "answer_text_copied": False,
        "applied": [
            {
                "case_id": "vol2-fix6-balance-0001",
                "offset": replace_offset,
                "original": INNER_RIGHT,
                "replacement": JP_RIGHT,
                "reason": "mixed opening 「 with closing 』 caused one unmatched left Japanese quote",
                "context_before": context(text, replace_offset),
                "context_after": context(updated, replace_offset),
            }
        ],
        "whitelist": str(WHITELIST_PATH),
        "whitelist_count": len(curly_items),
        "before": before,
        "after": after,
        "before_unmatched": before_unmatched,
        "after_unmatched": after_unmatched,
        "guard_checks": {
            "offset_guard": "passed",
            "quote_balance_fixed": after["balanced_jp"],
            "square_brackets_still_zero": after["left_square"] == 0 and after["right_square"] == 0,
            "empty_dialogues_unchanged": after["empty_dialogues"] == before["empty_dialogues"],
        },
    }
    CORRECTED_PATH.write_text(updated, encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
