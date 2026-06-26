"""Fill the final Volume 4 dialogue wrapper pair after balance repair."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第4卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
REPORT_PATH = Path("output") / "vol4_gap_apply_report_fix8.json"
WHITELIST_PATH = Path("output") / "vol4_nonstandard_whitelist_fix8.json"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"
DIVISION = "\u00f7"
FULLWIDTH_COLON = "\uff1a"


def stats(text: str) -> dict:
    return {
        "left_quote": text.count(JP_LEFT),
        "right_quote": text.count(JP_RIGHT),
        "balanced_jp": text.count(JP_LEFT) == text.count(JP_RIGHT),
        "empty_dialogues": text.count(JP_LEFT + JP_RIGHT),
        "left_square": text.count("["),
        "right_square": text.count("]"),
        "book_left": text.count("\u300a"),
        "book_right": text.count("\u300b"),
    }


def context(text: str, offset: int, width: int = 90) -> str:
    return text[max(0, offset - width) : min(len(text), offset + width + 1)].replace("\n", "\\n")


def replace_at(chars: list[str], offset: int, original: str, replacement: str, case_id: str, reason: str) -> dict:
    current = "".join(chars)
    if chars[offset] != original:
        raise ValueError(f"{case_id}: offset guard failed at {offset}")
    before = context(current, offset)
    chars[offset] = replacement
    after = context("".join(chars), offset)
    return {
        "case_id": case_id,
        "offset": offset,
        "original": original,
        "replacement": replacement,
        "reason": reason,
        "context_before": before,
        "context_after": after,
    }


def unmatched_right_offsets(text: str) -> list[int]:
    stack: list[int] = []
    unmatched: list[int] = []
    for i, ch in enumerate(text):
        if ch == JP_LEFT:
            stack.append(i)
        elif ch == JP_RIGHT:
            if stack:
                stack.pop()
            else:
                unmatched.append(i)
    return unmatched


def main() -> int:
    text = TextLoader().load(str(CORRECTED_PATH)).text
    before = stats(text)
    chars = list(text)
    applied = []

    div_offset = text.find(DIVISION, 44000, 45500)
    if div_offset < 0:
        raise ValueError("target division marker not found")
    applied.append(
        replace_at(
            chars,
            div_offset,
            DIVISION,
            JP_RIGHT,
            "vol4-fix8-gap-0001",
            "OCR division sign used as right dialogue boundary",
        )
    )

    interim = "".join(chars)
    unmatched = unmatched_right_offsets(interim)
    if len(unmatched) != 1:
        raise ValueError(f"expected one unmatched right quote after division fix, got {unmatched}")
    right_offset = unmatched[0]
    colon_offset = right_offset - len("艾莉莎。") - 1
    applied.append(
        replace_at(
            chars,
            colon_offset,
            FULLWIDTH_COLON,
            JP_LEFT,
            "vol4-fix8-gap-0002",
            "fullwidth colon before a spoken name was an OCR left-boundary residue",
        )
    )

    updated = "".join(chars)
    after = stats(updated)
    if after["left_quote"] != 1561 or after["right_quote"] != 1561:
        raise ValueError(f"unexpected final Volume 4 quote counts: {after}")
    if not after["balanced_jp"]:
        raise ValueError("Volume 4 is not balanced")
    if unmatched_right_offsets(updated):
        raise ValueError("unmatched right quotes remain")
    if after["empty_dialogues"] != before["empty_dialogues"]:
        raise ValueError("empty dialogue count changed unexpectedly")
    if after["left_square"] or after["right_square"]:
        raise ValueError("square bracket residue regressed")

    whitelist = [
        {
            "symbol": "\u300a...\u300b",
            "decision": "whitelist",
            "reason": "book-title brackets, not dialogue wrappers",
            "context": context(updated, updated.find("\u300a")),
        },
        {
            "symbol": "\u300b",
            "decision": "whitelist",
            "reason": "annotation closing bracket residue, not dialogue wrapper",
            "context": context(updated, updated.rfind("\u300b")),
        },
    ]
    WHITELIST_PATH.write_text(json.dumps(whitelist, ensure_ascii=False, indent=2), encoding="utf-8")
    CORRECTED_PATH.write_text(updated, encoding="utf-8")

    report = {
        "volume": VOL,
        "stage": "Fix 8",
        "corrected_path": str(CORRECTED_PATH),
        "modified_corrected_text": True,
        "answer_text_copied": False,
        "applied_count": len(applied),
        "whitelist_count": len(whitelist),
        "before": before,
        "after": after,
        "applied": applied,
        "whitelist": str(WHITELIST_PATH),
        "guard_checks": {
            "offset_guard": "passed",
            "quote_target_reached": True,
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
