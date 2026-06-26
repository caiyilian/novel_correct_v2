"""Fill the final three Volume 2 dialogue wrapper gaps."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第2卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
REPORT_PATH = Path("output") / "vol2_gap_apply_report_fix7.json"
WHITELIST_PATH = Path("output") / "vol2_nonstandard_whitelist_fix7.json"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"


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


def apply_exact_once(text: str, case_id: str, original: str, replacement: str, reason: str) -> tuple[str, dict]:
    offset = text.find(original)
    if offset < 0:
        raise ValueError(f"{case_id}: source snippet not found")
    if text.find(original, offset + 1) >= 0:
        raise ValueError(f"{case_id}: source snippet is not unique")
    updated = text[:offset] + replacement + text[offset + len(original) :]
    return updated, {
        "case_id": case_id,
        "offset": offset,
        "original": original,
        "replacement": replacement,
        "reason": reason,
        "context_before": context(text, offset),
        "context_after": context(updated, offset),
    }


def main() -> int:
    text = TextLoader().load(str(CORRECTED_PATH)).text
    before = stats(text)

    replacements = [
        (
            "vol2-fix7-gap-0001",
            "\n \n    我明白。 \n \n    此刻，第二故乡断然地排拒罗伦斯在门外。",
            "\n \n    「我明白。」 \n \n    此刻，第二故乡断然地排拒罗伦斯在门外。",
            "bare dialogue line between spoken turns",
        ),
        (
            "vol2-fix7-gap-0002",
            "说了句“怎么可能”结果被赫萝斜眼一瞪",
            "说了句「怎么可能」结果被赫萝斜眼一瞪",
            "curly inline dialogue quote normalized to project wrapper",
        ),
        (
            "vol2-fix7-gap-0003",
            "一呵呵呵呵呵。汝这家伙也真是奇怪，把咱的衣服当成宝一样。一",
            "「呵呵呵呵呵。汝这家伙也真是奇怪，把咱的衣服当成宝一样。」",
            "OCR dash-like wrappers around a spoken line normalized to Japanese quotes",
        ),
    ]

    applied = []
    updated = text
    for case_id, original, replacement, reason in replacements:
        updated, item = apply_exact_once(updated, case_id, original, replacement, reason)
        applied.append(item)

    after = stats(updated)
    if after["left_quote"] != 1425 or after["right_quote"] != 1425:
        raise ValueError(f"unexpected final quote counts: {after}")
    if not after["balanced_jp"]:
        raise ValueError("Volume 2 is not balanced after Fix 7")
    if after["empty_dialogues"] != before["empty_dialogues"]:
        raise ValueError("empty dialogue count changed unexpectedly")
    if after["left_square"] or after["right_square"]:
        raise ValueError("square bracket residue regressed")
    if after["curly_left"] or after["curly_right"]:
        raise ValueError("curly quote residue still exists")

    CORRECTED_PATH.write_text(updated, encoding="utf-8")
    WHITELIST_PATH.write_text("[]\n", encoding="utf-8")
    report = {
        "volume": VOL,
        "stage": "Fix 7",
        "corrected_path": str(CORRECTED_PATH),
        "modified_corrected_text": True,
        "answer_text_copied": False,
        "applied_count": len(applied),
        "manual_review_count": 0,
        "whitelist_count": 0,
        "before": before,
        "after": after,
        "applied": applied,
        "guard_checks": {
            "exact_source_snippets_unique": True,
            "quote_target_reached": True,
            "quote_balance_fixed": True,
            "square_brackets_still_zero": True,
            "curly_quotes_zero": True,
            "empty_dialogues_unchanged": True,
        },
        "known_residual_structure_note": (
            "Alignment still contains historical OCR boundary artifacts such as "
            "dash-like closers. This stage is limited to reaching the Volume 2 "
            "1425/1425 wrapper target without OCR text rewriting."
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
