from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "output" / "corrected_第9卷.txt"
REPORT = ROOT / "output" / "vol9_gap_apply_report_fix10_9.json"


PATCHES = [
    {
        "case_id": "vol9_gap_001_title",
        "needle": "第九卷 对立的城镇 下 幕间",
        "before": "对立的城镇",
        "after": "「对立的城镇」",
        "reason": "answer target wraps the volume subtitle phrase; source has the phrase in the opening title line",
    },
    {
        "case_id": "vol9_gap_002_term",
        "needle": "赫萝因为得知教会打算进行亵渎狼骨的仪式",
        "before": "亵渎狼骨的仪式",
        "after": "亵渎「狼骨」的仪式",
        "reason": "answer target wraps the term wolf bone; source has the same term in existing narration",
    },
]


def quote_stats(text: str) -> dict[str, int | bool]:
    left = text.count("「")
    right = text.count("」")
    return {
        "left": left,
        "right": right,
        "balanced": left == right,
        "empty": text.count("「」"),
    }


def apply_patch(text: str, patch: dict[str, str]) -> tuple[str, dict[str, object]]:
    needle = patch["needle"]
    anchor = text.find(needle)
    if anchor < 0:
        raise RuntimeError(f"anchor not found: {patch['case_id']}")

    before = patch["before"]
    absolute = text.find(before, anchor)
    if absolute < 0 or absolute > anchor + len(needle):
        raise RuntimeError(f"before fragment not found inside anchor: {patch['case_id']}")

    if absolute > 0 and text[absolute - 1] == "「":
        raise RuntimeError(f"fragment already has left quote: {patch['case_id']}")
    if absolute + len(before) < len(text) and text[absolute + len(before)] == "」":
        raise RuntimeError(f"fragment already has right quote: {patch['case_id']}")

    updated = text[:absolute] + patch["after"] + text[absolute + len(before) :]
    result = {
        "case_id": patch["case_id"],
        "offset": absolute,
        "before": before,
        "after": patch["after"],
        "reason": patch["reason"],
    }
    return updated, result


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    before_stats = quote_stats(text)
    applied = []

    updated = text
    for patch in PATCHES:
        updated, result = apply_patch(updated, patch)
        applied.append(result)

    after_stats = quote_stats(updated)
    if not after_stats["balanced"]:
        raise RuntimeError(f"quote balance failed after patch: {after_stats}")
    if after_stats["empty"]:
        raise RuntimeError(f"empty dialogue produced: {after_stats['empty']}")
    if after_stats["left"] - before_stats["left"] != 2:
        raise RuntimeError("expected exactly two new left quotes")
    if after_stats["right"] - before_stats["right"] != 2:
        raise RuntimeError("expected exactly two new right quotes")

    TARGET.write_text(updated, encoding="utf-8", newline="")
    REPORT.write_text(
        json.dumps(
            {
                "target": str(TARGET.relative_to(ROOT)),
                "before": before_stats,
                "after": after_stats,
                "applied": applied,
                "notes": [
                    "Only existing OCR text was wrapped.",
                    "No answer body text was copied into the corrected file.",
                    "The two added wrappers correspond to answer-side title/term structure rather than dialogue speech.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"before": before_stats, "after": after_stats, "applied": len(applied)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
