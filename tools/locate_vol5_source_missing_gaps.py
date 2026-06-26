from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "output" / "corrected_第5卷.txt"
REPORT_JSON = ROOT / "output" / "vol5_source_missing_gap_queue_fix10_5.json"
REPORT_MD = ROOT / "output" / "vol5_source_missing_gap_queue_fix10_5.md"


CASES = [
    {
        "case_id": "vol5_gap_001",
        "answer_dialogue": "……",
        "anchor": "赫萝发出「嘻嘻嘻」的笑声说",
        "expected_near": "answer has standalone silence before the laugh",
    },
    {
        "case_id": "vol5_gap_002",
        "answer_dialogue": "……",
        "anchor": "可能是睡了一觉后觉得舒爽许多，赫萝正在床上梳理尾巴",
        "expected_near": "answer has standalone silence before 「……怎么了？」",
    },
    {
        "case_id": "vol5_gap_003",
        "answer_dialogue": "……",
        "anchor": "抱有占有欲的罪恶之深，与只想独自一人赚钱的欲望根本不成正比",
        "expected_near": "answer has standalone silence before 「那，汝反省好了没？」",
    },
    {
        "case_id": "vol5_gap_004",
        "answer_dialogue": "……",
        "anchor": "当然了，因为怕走丢，所以她紧紧握住罗伦斯的手",
        "expected_near": "answer has standalone silence before 「咦？」",
    },
]


def quote_stats(text: str) -> dict[str, int | bool]:
    return {
        "left": text.count("「"),
        "right": text.count("」"),
        "balanced": text.count("「") == text.count("」"),
        "empty": text.count("「」"),
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
    cases = []
    for case in CASES:
        offset, context = context_for(text, case["anchor"])
        local_has_bare_silence = "「……」" not in context and "……" in context
        cases.append(
            {
                **case,
                "anchor_offset": offset,
                "ocr_context": context,
                "auto_action": "needs_manual_source_review",
                "reason": (
                    "The answer-side missing dialogue is a standalone 「……」, but the OCR corrected "
                    "context does not contain a corresponding unwrapped standalone ellipsis. "
                    "Auto-inserting it would add answer-only text instead of wrapping existing OCR text."
                ),
                "local_has_bare_ellipsis": local_has_bare_silence,
            }
        )

    payload = {
        "target": str(TARGET.relative_to(ROOT)),
        "stats": quote_stats(text),
        "target_answer_counts": {"left": 1459, "right": 1459},
        "remaining_gap": {"left": 4, "right": 4},
        "auto_applied": 0,
        "manual_review_count": len(cases),
        "cases": cases,
    }
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 第5卷 Fix 10-5 人工/来源缺失队列",
        "",
        "- 当前第5卷：1455/1455，答案目标：1459/1459。",
        "- 4 个缺口均为答案侧独立 `「……」`。",
        "- OCR 主产物对应上下文没有可直接包裹的独立省略号；自动插入会新增答案侧文本，因此本阶段未自动应用。",
        "",
    ]
    for case in cases:
        lines.extend(
            [
                f"## {case['case_id']}",
                "",
                f"- 答案缺口：`「{case['answer_dialogue']}」`",
                f"- OCR anchor offset：{case['anchor_offset']}",
                f"- 说明：{case['reason']}",
                "",
                "```text",
                case["ocr_context"],
                "```",
                "",
            ]
        )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"manual_review_count": len(cases), "auto_applied": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
