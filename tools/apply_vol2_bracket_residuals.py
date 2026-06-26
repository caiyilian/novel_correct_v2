"""Normalize remaining square bracket wrappers in Volume 2.

The script is intentionally narrow: it only replaces '[' with '「' and ']'
with '」' in the current Volume 2 corrected product. It records every offset
and verifies that no non-wrapper text changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第2卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
CANDIDATES_PATH = Path("output") / "vol2_bracket_candidates_fix5.jsonl"
REPORT_PATH = Path("output") / "vol2_bracket_apply_report_fix5.json"
MANUAL_QUEUE_PATH = Path("output") / "vol2_bracket_manual_queue_fix5.json"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"


def context(text: str, offset: int, width: int = 70) -> str:
    start = max(0, offset - width)
    end = min(len(text), offset + width + 1)
    return text[start:end].replace("\n", "\\n")


def stats(text: str) -> Dict[str, int | bool]:
    return {
        "left_quote": text.count(JP_LEFT),
        "right_quote": text.count(JP_RIGHT),
        "balanced_jp": text.count(JP_LEFT) == text.count(JP_RIGHT),
        "left_square": text.count("["),
        "right_square": text.count("]"),
        "curly_left": text.count("\u201c"),
        "curly_right": text.count("\u201d"),
        "empty_dialogues": text.count(JP_LEFT + JP_RIGHT),
    }


def without_wrapper_symbols(text: str) -> str:
    return (
        text.replace("[", "")
        .replace("]", "")
        .replace(JP_LEFT, "")
        .replace(JP_RIGHT, "")
    )


def build_candidates(text: str) -> List[dict]:
    candidates: List[dict] = []
    for index, (offset, ch) in enumerate(
        ((i, ch) for i, ch in enumerate(text) if ch in "[]"),
        start=1,
    ):
        replacement = JP_LEFT if ch == "[" else JP_RIGHT
        candidates.append(
            {
                "case_id": f"vol2-fix5-bracket-{index:04d}",
                "volume": VOL,
                "offset": offset,
                "original": ch,
                "replacement": replacement,
                "candidate_type": (
                    "left_square_as_dialogue_or_inline_quote_boundary"
                    if ch == "["
                    else "right_square_as_dialogue_or_inline_quote_boundary"
                ),
                "risk_level": "low",
                "decision": "apply",
                "reason": (
                    "remaining square bracket is a wrapper-side OCR residue; "
                    "normalize only the wrapper symbol and keep inner text unchanged"
                ),
                "context": context(text, offset),
            }
        )
    return candidates


def apply_candidates(text: str, candidates: List[dict]) -> str:
    chars = list(text)
    for candidate in candidates:
        offset = candidate["offset"]
        original = candidate["original"]
        replacement = candidate["replacement"]
        if chars[offset] != original:
            raise ValueError(
                f"offset guard failed for {candidate['case_id']}: "
                f"expected {original!r}, got {chars[offset]!r}"
            )
        chars[offset] = replacement
    return "".join(chars)


def main() -> int:
    text = TextLoader().load(str(CORRECTED_PATH)).text
    before = stats(text)
    candidates = build_candidates(text)
    updated = apply_candidates(text, candidates)
    after = stats(updated)

    if without_wrapper_symbols(text) != without_wrapper_symbols(updated):
        raise ValueError("non-wrapper text changed; aborting")
    if abs(after["left_quote"] - after["right_quote"]) > abs(
        before["left_quote"] - before["right_quote"]
    ):
        raise ValueError("quote balance gap became worse; aborting")
    if after["empty_dialogues"] != before["empty_dialogues"]:
        raise ValueError("empty dialogue count changed unexpectedly; aborting")

    CORRECTED_PATH.write_text(updated, encoding="utf-8")
    with CANDIDATES_PATH.open("w", encoding="utf-8") as f:
        for candidate in candidates:
            f.write(json.dumps(candidate, ensure_ascii=False) + "\n")

    report = {
        "volume": VOL,
        "stage": "Fix 5",
        "corrected_path": str(CORRECTED_PATH),
        "modified_corrected_text": bool(candidates),
        "answer_text_copied": False,
        "candidate_count": len(candidates),
        "applied_count": len(candidates),
        "manual_review_count": 0,
        "whitelist_count": 0,
        "before": before,
        "after": after,
        "quote_balance_gap_before": before["left_quote"] - before["right_quote"],
        "quote_balance_gap_after": after["left_quote"] - after["right_quote"],
        "guard_checks": {
            "offset_guard": "passed",
            "only_wrapper_symbols_changed": True,
            "quote_balance_not_worse": True,
            "empty_dialogues_unchanged": True,
        },
        "outputs": {
            "candidates": str(CANDIDATES_PATH),
            "manual_queue": str(MANUAL_QUEUE_PATH),
        },
        "remaining_notes": (
            "Square brackets are fully normalized. Remaining Volume 2 structure "
            "work should address quote balance and any curly quote residues."
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MANUAL_QUEUE_PATH.write_text("[]\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
