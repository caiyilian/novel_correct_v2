"""Document the remaining Volume 6 target gap after balance repair."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


VOL = "第6卷"
CORRECTED_PATH = Path("output") / f"corrected_{VOL}.txt"
ANSWER_PATH = Path("data/answer") / f"answer_{VOL}.txt"
QUEUE_PATH = Path("output") / "vol6_gap_manual_queue_fix9.json"
SUMMARY_PATH = Path("output") / "vol6_gap_manual_queue_fix9.md"

JP_LEFT = "\u300c"
JP_RIGHT = "\u300d"


def extract_dialogues(text: str) -> list[str]:
    stack: list[int] = []
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch == JP_LEFT:
            stack.append(i)
        elif ch == JP_RIGHT and stack:
            start = stack.pop()
            out.append(text[start : i + 1])
    return out


def context(text: str, offset: int, width: int = 120) -> str:
    return text[max(0, offset - width) : min(len(text), offset + width)].replace("\n", "\\n")


def main() -> int:
    corrected = TextLoader().load(str(CORRECTED_PATH)).text
    answer = TextLoader().load(str(ANSWER_PATH)).text
    corr_dialogues = extract_dialogues(corrected)
    ans_dialogues = extract_dialogues(answer)

    missing = "什么事啊？如果是要跟我借盘缠，我可帮不上忙。"
    search_terms = ["什么事啊", "借盘缠", "帮不上忙"]
    found_terms = [
        {
            "term": term,
            "offset": corrected.find(term),
            "context": context(corrected, corrected.find(term)) if corrected.find(term) >= 0 else "",
        }
        for term in search_terms
    ]
    nearby_anchor = "我、我有事想请求您。"
    anchor_offset = corrected.find(nearby_anchor)
    queue = [
        {
            "case_id": "vol6-fix9-gap-0001",
            "volume": VOL,
            "decision": "manual_review",
            "risk_level": "blocked_by_missing_source_text",
            "answer_dialogue_index": 1147,
            "answer_dialogue_preview": missing,
            "source_search": found_terms,
            "nearby_source_anchor": nearby_anchor,
            "nearby_source_anchor_offset": anchor_offset,
            "nearby_source_context": context(corrected, anchor_offset) if anchor_offset >= 0 else "",
            "reason": (
                "The answer-side dialogue is not present in the corrected OCR text. "
                "Adding it would copy answer正文, which is outside this project's scope."
            ),
        }
    ]

    report = {
        "volume": VOL,
        "corrected_path": str(CORRECTED_PATH),
        "answer_path": str(ANSWER_PATH),
        "corrected_dialogues": len(corr_dialogues),
        "answer_dialogues": len(ans_dialogues),
        "dialogue_gap": len(ans_dialogues) - len(corr_dialogues),
        "manual_review_count": len(queue),
        "queue": queue,
    }
    QUEUE_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY_PATH.write_text(
        "\n".join(
            [
                "# 第6卷 Fix 9 剩余缺口人工队列",
                "",
                f"- 当前段数：{len(corr_dialogues)}",
                f"- 答案段数：{len(ans_dialogues)}",
                f"- 剩余缺口：{len(ans_dialogues) - len(corr_dialogues)}",
                "",
                "## vol6-fix9-gap-0001",
                "",
                f"- 答案结构预览：`{missing}`",
                "- 判定：当前 OCR 文本中未找到该句或关键片段。",
                "- 处理：不得从答案复制正文，进入人工复核。",
                "",
                "```text",
                queue[0]["nearby_source_context"],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
