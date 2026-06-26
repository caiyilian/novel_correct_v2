"""
通过 PolishJudge 运行候选人并输出裁决结果。

用法:
    python tools/run_polish_judge.py --candidates output/style_candidates.jsonl --output output/polish_decisions.jsonl
    python tools/run_polish_judge.py --candidates output/style_candidates.jsonl --mock  # 测试模式
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.polish_judge import PolishJudge


def load_candidates(path: str) -> List[dict]:
    """Load JSONL candidates file."""
    candidates = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(json.loads(line))
    return candidates


def candidate_to_case(c: dict, index: int) -> dict:
    """将一条候选记录转换为 PolishJudge 的 case 格式。"""
    case_type = c.get("type", "unknown")
    if case_type == "question_mark":
        case_type_label = "punctuation"
    elif case_type == "exclamation_mark":
        case_type_label = "punctuation"
    elif case_type == "period":
        case_type_label = "punctuation"
    elif case_type == "tilde":
        case_type_label = "punctuation"
    else:
        case_type_label = case_type

    target = c.get("original", "")
    candidate_val = c.get("candidate", target)
    risk = c.get("risk_level", "unknown")

    candidates = [
        {"id": "keep", "replacement": f"keep: {target}"},
        {"id": "c1", "replacement": f"apply: {target} -> {candidate_val}"},
    ]

    return {
        "case_id": f"{case_type}-{index:06d}",
        "case_type": case_type_label,
        "context_before": c.get("context_before", ""),
        "target": target,
        "context_after": c.get("context_after", ""),
        "candidates": candidates,
        "constraints": [
            "只能选择候选之一",
            "不得自由改写",
            "不得改变非目标文本",
            "不确定则选择 keep",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, help="input candidates JSONL path")
    parser.add_argument("--output", default="", help="output decisions JSONL path (default: stdout)")
    parser.add_argument("--mock", action="store_true", help="use mock judge (no LLM)")
    parser.add_argument("--limit", type=int, default=0, help="limit number of cases to process")
    args = parser.parse_args()

    if not Path(args.candidates).exists():
        print(f"Error: candidates file not found: {args.candidates}", file=sys.stderr)
        return 1

    candidates = load_candidates(args.candidates)
    if args.limit > 0:
        candidates = candidates[:args.limit]

    if args.mock:
        print(f"  Mock mode: {len(candidates)} candidates")
    else:
        print(f"  LLM mode: {len(candidates)} candidates")

    judge = PolishJudge(mock=args.mock)
    decisions = []

    start_time = time.time()
    for i, c in enumerate(candidates):
        case = candidate_to_case(c, i)
        result = judge.judge(case)
        decisions.append(result)

        if (i + 1) % 50 == 0 or i == 0 or i == len(candidates) - 1:
            elapsed = time.time() - start_time
            print(f"  [{i+1}/{len(candidates)}] {result['case_id']}: {result['decision']} "
                  f"({elapsed:.1f}s)", file=sys.stderr)

    total_elapsed = time.time() - start_time
    apply_count = sum(1 for d in decisions if d["decision"] == "apply")
    keep_count = sum(1 for d in decisions if d["decision"] == "keep")
    uncertain_count = sum(1 for d in decisions if d["decision"] == "uncertain")

    print(f"\n  完成: {len(decisions)} cases in {total_elapsed:.1f}s", file=sys.stderr)
    print(f"  apply={apply_count}, keep={keep_count}, uncertain={uncertain_count}", file=sys.stderr)
    if not args.mock:
        print(f"  Total tokens: {judge.total_tokens()}", file=sys.stderr)

    # 输出 decisions
    output_str = "\n".join(json.dumps(d, ensure_ascii=False) for d in decisions)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str + "\n")
        print(f"  Decisions saved: {args.output}", file=sys.stderr)
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())