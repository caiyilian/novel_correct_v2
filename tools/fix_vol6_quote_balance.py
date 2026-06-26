"""Fix Volume 6 quote balance and final wrapper gap."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第6卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
REPORT_PATH = Path("output") / "vol6_quote_balance_fix9_report.json"
WHITELIST_PATH = Path("output") / "vol6_nonstandard_whitelist_fix9.json"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"


def stats(text: str) -> dict:
    return {
        "left_quote": text.count(JP_LEFT),
        "right_quote": text.count(JP_RIGHT),
        "balanced_jp": text.count(JP_LEFT) == text.count(JP_RIGHT),
        "empty_dialogues": text.count(JP_LEFT + JP_RIGHT),
        "book_left": text.count("\u300a"),
        "book_right": text.count("\u300b"),
    }


def context(text: str, offset: int, width: int = 90) -> str:
    return text[max(0, offset - width) : min(len(text), offset + width + 1)].replace("\n", "\\n")


def apply_once(text: str, original: str, replacement: str, case_id: str, reason: str) -> tuple[str, dict]:
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
    applied = []

    text, item = apply_once(
        text,
        "木箱还是只能保持这样吧。 \n \n    「那么，赶紧动手吧。」",
        "木箱还是只能保持这样吧。」 \n \n    「那么，赶紧动手吧。」",
        "vol6-fix9-balance-0001",
        "missing right Japanese quote before next dialogue",
    )
    applied.append(item)

    after_balance = stats(text)
    # The remaining target gap is a safe book-title non-dialogue residue only;
    # keep book-title brackets as whitelist rather than converting them.
    whitelist = [
        {
            "symbol": "\u300a...\u300b",
            "decision": "whitelist",
            "reason": "book-title brackets, not dialogue wrappers",
            "context": context(text, text.find("\u300a")),
        }
    ]

    if not after_balance["balanced_jp"]:
        raise ValueError(f"Volume 6 is still unbalanced: {after_balance}")
    if after_balance["empty_dialogues"] != before["empty_dialogues"]:
        raise ValueError("empty dialogue count changed unexpectedly")

    CORRECTED_PATH.write_text(text, encoding="utf-8")
    WHITELIST_PATH.write_text(json.dumps(whitelist, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "volume": VOL,
        "stage": "Fix 9",
        "corrected_path": str(CORRECTED_PATH),
        "modified_corrected_text": True,
        "answer_text_copied": False,
        "applied_count": len(applied),
        "whitelist_count": len(whitelist),
        "before": before,
        "after": after_balance,
        "applied": applied,
        "whitelist": str(WHITELIST_PATH),
        "guard_checks": {
            "exact_source_snippet_unique": True,
            "quote_balance_fixed": True,
            "empty_dialogues_unchanged": True,
        },
        "remaining_note": "Volume 6 is balanced after this fix; remaining count target should be checked by compare/verify.",
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
