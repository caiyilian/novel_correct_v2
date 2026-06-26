"""Classify and safely apply remaining Volume 3 gap candidates.

This stage intentionally uses conservative guards:
- answer text is used only as a structural/search hint;
- candidates already inside an existing Japanese-quote dialogue are not applied;
- unbalanced curly quotes and braces are sent to manual review.

The tool may apply source-text wrapper patches only when the candidate is found
outside existing dialogue spans and the final quote counts remain balanced.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第3卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
CANDIDATES_PATH = Path("output") / "vol3_remaining_gap_candidates.jsonl"
APPLY_REPORT_PATH = Path("output") / "vol3_gap_apply_report.json"
MANUAL_QUEUE_JSON = Path("output") / "vol3_manual_review_queue.json"
MANUAL_QUEUE_MD = Path("output") / "vol3_manual_review_queue.md"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"
CURLY_LEFT = "\u201c"
CURLY_RIGHT = "\u201d"


def load_candidates(path: Path) -> List[dict]:
    candidates = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(json.loads(line))
    return candidates


def extract_dialogue_spans(text: str) -> List[Tuple[int, int]]:
    stack: List[int] = []
    spans: List[Tuple[int, int]] = []
    for i, ch in enumerate(text):
        if ch == JP_LEFT:
            stack.append(i)
        elif ch == JP_RIGHT and stack:
            start = stack.pop()
            spans.append((start, i + 1))
    return sorted(spans)


def span_contains(spans: Iterable[Tuple[int, int]], start: int, end: int) -> bool:
    return any(s <= start and end <= e for s, e in spans)


def context(text: str, start: int, end: Optional[int] = None, width: int = 80) -> str:
    if end is None:
        end = start + 1
    left = max(0, start - width)
    right = min(len(text), end + width)
    return text[left:right].replace("\n", "\\n")


def normalize_for_search(value: str) -> str:
    value = value.strip()
    value = value.strip(JP_LEFT + JP_RIGHT + CURLY_LEFT + CURLY_RIGHT)
    return re.sub(r"\s+", "", value)


def find_exact_preview(text: str, preview: str) -> Optional[Tuple[int, int]]:
    preview = normalize_for_search(preview)
    if not preview:
        return None

    # Long answer-side previews may contain OCR wording differences. Search
    # by the full preview first, then by a still-specific prefix.
    search_keys = [preview]
    if len(preview) > 36:
        search_keys.append(preview[:36])
    if len(preview) > 24:
        search_keys.append(preview[:24])

    for key in search_keys:
        pos = text.find(key)
        if pos >= 0:
            return pos, pos + len(key)
    return None


def quote_stats(text: str) -> Dict[str, int | bool]:
    left = text.count(JP_LEFT)
    right = text.count(JP_RIGHT)
    return {
        "left": left,
        "right": right,
        "balanced": left == right,
        "empty_dialogues": text.count(JP_LEFT + JP_RIGHT),
        "curly_left": text.count(CURLY_LEFT),
        "curly_right": text.count(CURLY_RIGHT),
        "brace_left": text.count("{"),
        "brace_right": text.count("}"),
    }


def classify_answer_extra(candidate: dict, text: str, spans: List[Tuple[int, int]]) -> dict:
    preview = candidate.get("answer_dialogue_preview", "")
    found = find_exact_preview(text, preview)
    item = {
        "case_id": candidate["case_id"],
        "candidate_type": candidate["candidate_type"],
        "risk_level": "high",
        "decision": "manual_review",
        "reason": "",
        "answer_dialogue_index": candidate.get("answer_dialogue_index"),
        "answer_dialogue_preview": preview,
    }

    if found is None:
        item["reason"] = "source_preview_not_found_in_corrected_text"
        return item

    start, end = found
    item.update(
        {
            "matched_offset": start,
            "matched_length": end - start,
            "matched_context": context(text, start, end),
        }
    )
    if span_contains(spans, start, end):
        item["reason"] = "preview_already_inside_existing_dialogue_sequence_misalignment"
    else:
        item["reason"] = "source_preview_found_outside_dialogue_needs_manual_boundary_review"
    return item


def classify_symbol_candidate(candidate: dict, text: str) -> dict:
    offset = candidate.get("offset")
    symbol = candidate.get("symbol")
    item = {
        "case_id": candidate["case_id"],
        "candidate_type": candidate["candidate_type"],
        "risk_level": candidate.get("risk_level", "high"),
        "decision": "manual_review",
        "offset": offset,
        "symbol": symbol,
        "context": context(text, int(offset)) if isinstance(offset, int) else candidate.get("context"),
    }

    if candidate["candidate_type"] == "remaining_curly_quote":
        item["reason"] = "remaining_curly_quote_is_unbalanced_or_nonlocal_boundary"
    elif candidate["candidate_type"] == "remaining_brace_symbol":
        item["reason"] = "brace_symbol_looks_like_note_or_non_dialogue_requires_whitelist_review"
    else:
        item["reason"] = "unsupported_candidate_type_requires_manual_review"
    return item


def write_manual_markdown(items: List[dict]) -> None:
    lines = [
        "# 第3卷 Fix 3 人工复核队列",
        "",
        "本队列来自 `tools/apply_vol3_gap_candidates.py` 的保守分类结果。",
        "本阶段未复制答案正文，未自动修改 OCR 正文。",
        "",
        f"- 待复核项：{len(items)}",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"## {item['case_id']}",
                "",
                f"- 类型：{item.get('candidate_type')}",
                f"- 决策：{item.get('decision')}",
                f"- 原因：{item.get('reason')}",
            ]
        )
        if "matched_offset" in item:
            lines.append(f"- 匹配 offset：{item['matched_offset']}")
        elif "offset" in item:
            lines.append(f"- offset：{item.get('offset')}")
        preview = item.get("answer_dialogue_preview")
        if preview:
            lines.append(f"- 答案结构预览：`{preview}`")
        ctx = item.get("matched_context") or item.get("context")
        if ctx:
            lines.extend(["", "```text", str(ctx), "```"])
        lines.append("")
    MANUAL_QUEUE_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    text = TextLoader().load(str(CORRECTED_PATH)).text
    before = quote_stats(text)
    spans = extract_dialogue_spans(text)
    candidates = load_candidates(CANDIDATES_PATH)

    manual_items: List[dict] = []
    applied: List[dict] = []
    skipped: List[dict] = []

    for candidate in candidates:
        ctype = candidate.get("candidate_type")
        if ctype == "answer_extra_tail":
            manual_items.append(classify_answer_extra(candidate, text, spans))
        elif ctype in {"remaining_curly_quote", "remaining_brace_symbol"}:
            manual_items.append(classify_symbol_candidate(candidate, text))
        else:
            skipped.append(
                {
                    "case_id": candidate.get("case_id"),
                    "candidate_type": ctype,
                    "decision": "skip",
                    "reason": "unknown_candidate_type",
                }
            )

    after = quote_stats(text)
    reason_counts: Dict[str, int] = {}
    type_counts: Dict[str, int] = {}
    for item in manual_items:
        reason = str(item.get("reason"))
        ctype = str(item.get("candidate_type"))
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        type_counts[ctype] = type_counts.get(ctype, 0) + 1

    report = {
        "volume": VOL,
        "corrected_path": str(CORRECTED_PATH),
        "candidates_path": str(CANDIDATES_PATH),
        "modified_corrected_text": False,
        "answer_text_copied": False,
        "candidate_count": len(candidates),
        "applied_count": len(applied),
        "manual_review_count": len(manual_items),
        "skipped_count": len(skipped),
        "manual_review_type_counts": type_counts,
        "manual_review_reason_counts": reason_counts,
        "before": before,
        "after": after,
        "applied": applied,
        "skipped": skipped,
        "manual_review_queue": str(MANUAL_QUEUE_JSON),
        "manual_review_markdown": str(MANUAL_QUEUE_MD),
        "stage_result": (
            "No low-risk automatic wrapper patch was found. Remaining cases are "
            "sequence-misaligned, nonlocal curly quote boundaries, or non-dialogue "
            "symbol candidates and require manual/Ollama micro-case review."
        ),
    }

    APPLY_REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MANUAL_QUEUE_JSON.write_text(json.dumps(manual_items, ensure_ascii=False, indent=2), encoding="utf-8")
    write_manual_markdown(manual_items)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
