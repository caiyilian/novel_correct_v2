"""Locate remaining Volume 3 dialogue wrapping gaps after Fix 1.

This tool is read-only. It does not modify corrected text and does not copy
answer text into the corrected product. The answer file is used only as a
structural reference for dialogue counts and gap candidates.
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第3卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
ANSWER_PATH = Path("data/answer") / f"answer_{VOL}.txt"
OUT_CANDIDATES = Path("output") / "vol3_remaining_gap_candidates.jsonl"
OUT_SUMMARY = Path("output") / "vol3_remaining_gap_summary.json"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"
CURLY_LEFT = "\u201c"
CURLY_RIGHT = "\u201d"


def extract_dialogues(text: str) -> List[Tuple[int, int, str]]:
    stack: List[int] = []
    result: List[Tuple[int, int, str]] = []
    for i, ch in enumerate(text):
        if ch == JP_LEFT:
            stack.append(i)
        elif ch == JP_RIGHT and stack:
            start = stack.pop()
            result.append((start, i + 1, text[start : i + 1]))
    return result


def context(text: str, offset: int, width: int = 80) -> str:
    start = max(0, offset - width)
    end = min(len(text), offset + width)
    return text[start:end].replace("\n", "\\n")


def preview_dialogue(dialogue: str, limit: int = 120) -> str:
    inner = dialogue[1:-1] if dialogue.startswith(JP_LEFT) and dialogue.endswith(JP_RIGHT) else dialogue
    inner = re.sub(r"\s+", "", inner)
    if len(inner) <= limit:
        return inner
    return inner[:limit] + "..."


def main() -> int:
    corrected = TextLoader().load(str(CORRECTED_PATH)).text
    answer = TextLoader().load(str(ANSWER_PATH)).text

    corrected_dialogues = extract_dialogues(corrected)
    answer_dialogues = extract_dialogues(answer)

    candidates = []

    current_count = len(corrected_dialogues)
    target_count = len(answer_dialogues)
    gap = target_count - current_count

    tail_context = [
        {
            "corrected_dialogue_index": i + 1,
            "preview": preview_dialogue(d),
        }
        for i, (_, _, d) in enumerate(corrected_dialogues[-5:], start=max(0, current_count - 5))
    ]

    if gap > 0:
        for idx, (_, _, ans_dialogue) in enumerate(answer_dialogues[current_count:], start=current_count + 1):
            candidates.append({
                "case_id": f"vol3-gap-answer-extra-{idx:04d}",
                "volume": VOL,
                "candidate_type": "answer_extra_tail",
                "risk_level": "high",
                "answer_dialogue_index": idx,
                "answer_dialogue_preview": preview_dialogue(ans_dialogue),
                "corrected_tail_context": tail_context,
                "suggested_action": "locate_matching_source_text_and_add_dialogue_wrappers",
                "notes": (
                    "Answer has a dialogue segment after the current corrected dialogue list ends. "
                    "Use as structural reference only; do not copy answer text into corrected output."
                ),
            })

    curly_positions = [
        (i, ch)
        for i, ch in enumerate(corrected)
        if ch in (CURLY_LEFT, CURLY_RIGHT)
    ]
    for n, (offset, ch) in enumerate(curly_positions, start=1):
        candidates.append({
            "case_id": f"vol3-gap-curly-{n:04d}",
            "volume": VOL,
            "candidate_type": "remaining_curly_quote",
            "risk_level": "high",
            "offset": offset,
            "symbol": ch,
            "context": context(corrected, offset),
            "suggested_action": "review_curly_quote_boundary",
            "notes": "Remaining curly quote in corrected output may indicate a missed or abnormal dialogue boundary.",
        })

    brace_positions = [
        (i, ch)
        for i, ch in enumerate(corrected)
        if ch in ("{", "}")
    ]
    for n, (offset, ch) in enumerate(brace_positions, start=1):
        candidates.append({
            "case_id": f"vol3-gap-brace-{n:04d}",
            "volume": VOL,
            "candidate_type": "remaining_brace_symbol",
            "risk_level": "uncertain",
            "offset": offset,
            "symbol": ch,
            "context": context(corrected, offset),
            "suggested_action": "manual_review_nonstandard_symbol",
            "notes": "Brace symbol is non-standard for dialogue wrapping; classify before modifying.",
        })

    type_counts = {}
    risk_counts = {}
    for c in candidates:
        type_counts[c["candidate_type"]] = type_counts.get(c["candidate_type"], 0) + 1
        risk_counts[c["risk_level"]] = risk_counts.get(c["risk_level"], 0) + 1

    summary = {
        "volume": VOL,
        "corrected_path": str(CORRECTED_PATH),
        "answer_path": str(ANSWER_PATH),
        "current_dialogues": current_count,
        "target_dialogues": target_count,
        "dialogue_gap": gap,
        "current_quote_left": corrected.count(JP_LEFT),
        "current_quote_right": corrected.count(JP_RIGHT),
        "remaining_curly_left": corrected.count(CURLY_LEFT),
        "remaining_curly_right": corrected.count(CURLY_RIGHT),
        "remaining_brace_left": corrected.count("{"),
        "remaining_brace_right": corrected.count("}"),
        "candidate_count": len(candidates),
        "candidate_type_counts": type_counts,
        "risk_counts": risk_counts,
        "modified_corrected_text": False,
        "next_stage": (
            "Fix 3 should inspect these candidates, apply low-risk source-text wrappers, "
            "and send high-risk cases to constrained Ollama/人工裁决."
        ),
    }

    OUT_CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CANDIDATES.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
