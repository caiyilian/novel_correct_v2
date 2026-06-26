from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "output" / "corrected_第7卷.txt"
REPORT = ROOT / "output" / "vol7_gap_apply_report_fix10_7.json"
QUEUE_JSON = ROOT / "output" / "vol7_manual_review_queue_fix10_7.json"
QUEUE_MD = ROOT / "output" / "vol7_manual_review_queue_fix10_7.md"
WHITELIST = ROOT / "output" / "vol7_nonstandard_whitelist_fix10_7.json"


SAFE_SPLIT = {
    "case_id": "vol7_gap_safe_split_001",
    "before": "「您的预算是？两枚崔尼银币。」",
    "after": "「您的预算是？」「两枚崔尼银币。」",
    "reason": "Two adjacent speaker turns were wrapped as one dialogue pair; split without changing text.",
}


MANUAL_CASES = [
    {
        "case_id": "vol7_gap_manual_001",
        "answer_alignment": "？ + 啊，艾里亚丝！",
        "corrected_alignment": "艾里亚丝！",
        "anchor": "「艾里亚丝！」",
        "reason": "Answer has extra punctuation/text not present in OCR corrected dialogue; auto-fix would add answer-side text.",
    },
    {
        "case_id": "vol7_gap_manual_002",
        "answer_alignment": "啊，好的。 + 你在这里休息。",
        "corrected_alignment": "在这里休息！",
        "anchor": "「在这里休息！」",
        "reason": "Answer split uses substantially different text; no existing OCR fragment can be wrapped safely.",
    },
    {
        "case_id": "vol7_gap_manual_003",
        "answer_alignment": "咦？ + 抱歉。",
        "corrected_alignment": "抱、抱歉什么？",
        "anchor": "「抱、抱歉什么？」",
        "reason": "Answer split uses different wording; auto-fix would replace or add OCR text.",
    },
    {
        "case_id": "vol7_gap_manual_004",
        "answer_alignment": "抱、抱歉什么？ + 咱可能没办法救汝等。",
        "corrected_alignment": "咱可能没办法救汝等。",
        "anchor": "「咱可能没办法救汝等。」",
        "reason": "This is downstream alignment after the previous source/text mismatch, not a safe standalone wrapper fix.",
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
        "book_title_left": text.count("《"),
        "book_title_right": text.count("》"),
    }


def context_for(text: str, anchor: str, radius: int = 120) -> tuple[int, str]:
    offset = text.find(anchor)
    if offset < 0:
        raise RuntimeError(f"anchor not found: {anchor}")
    start = max(0, offset - radius)
    end = min(len(text), offset + len(anchor) + radius)
    return offset, text[start:end]


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    before = quote_stats(text)

    if text.count(SAFE_SPLIT["before"]) != 1:
        raise RuntimeError("safe split guard failed")
    offset = text.find(SAFE_SPLIT["before"])
    text = text.replace(SAFE_SPLIT["before"], SAFE_SPLIT["after"], 1)
    after = quote_stats(text)

    if after["left"] - before["left"] != 1 or after["right"] - before["right"] != 1:
        raise RuntimeError("expected exactly one added quote pair")
    if not after["balanced"] or after["empty"]:
        raise RuntimeError(f"invalid quote stats after split: {after}")

    TARGET.write_text(text, encoding="utf-8", newline="")

    manual = []
    for case in MANUAL_CASES:
        anchor_offset, context = context_for(text, case["anchor"])
        manual.append({**case, "anchor_offset": anchor_offset, "ocr_context": context, "status": "needs_manual_source_review"})

    report = {
        "target": str(TARGET.relative_to(ROOT)),
        "before": before,
        "after": after,
        "applied": [{**SAFE_SPLIT, "offset": offset}],
        "manual_review_count": len(manual),
        "remaining_gap_after_safe_apply": {"left": 4, "right": 4},
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    QUEUE_JSON.write_text(json.dumps({"cases": manual}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 第7卷 Fix 10-7 人工审核队列",
        "",
        "- 已安全拆分 1 处连包对话：`您的预算是？` / `两枚崔尼银币。`。",
        "- 剩余 4 处涉及答案侧额外文本或 OCR 文本差异，不能自动插入或替换。",
        "",
    ]
    for case in manual:
        lines.extend(
            [
                f"## {case['case_id']}",
                "",
                f"- 答案对齐：`{case['answer_alignment']}`",
                f"- 当前对齐：`{case['corrected_alignment']}`",
                f"- OCR anchor offset：{case['anchor_offset']}",
                f"- 原因：{case['reason']}",
                "",
                "```text",
                case["ocr_context"],
                "```",
                "",
            ]
        )
    QUEUE_MD.write_text("\n".join(lines), encoding="utf-8")

    WHITELIST.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "symbol": "《》",
                        "fragment": "刊载于《电击ｈｐ》的短篇及中篇故事",
                        "reason": "book/magazine title marker in afterword, not dialogue wrapper",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"before": before, "after": after, "manual_review_count": len(manual)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
