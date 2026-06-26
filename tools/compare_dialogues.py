"""
对话提取与对比工具

提取修正后文件和答案文件中的全部「」对话，按顺序逐组对比。
输出统计：总对话数、空对话数、内容匹配率、差异样本。

用法:
    python tools/compare_dialogues.py output/corrected_第1卷.txt data/answer/answer_第1卷.txt
    python tools/compare_dialogues.py output/corrected_第1卷.txt data/answer/answer_第1卷.txt --json output/compare_第1卷.json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def extract_dialogues(text: str) -> List[str]:
    """基于栈的「」提取器，支持嵌套"""
    stack: List[int] = []
    result: List[str] = []
    for i, ch in enumerate(text):
        if ch == "\u300c":
            stack.append(i)
        elif ch == "\u300d":
            if stack:
                start = stack.pop()
                result.append(text[start : i + 1])
    return result


def strip_punct(s: str) -> str:
    """去标点，仅保留中文字符和字母数字"""
    return re.sub(r"[？?!！·.。：:、，,～~…—‥\s\"\'\\n\\r]", "", s)


def text_similarity(a: str, b: str) -> float:
    """字符集重叠率: overlap / max(len(a), len(b))"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    overlap = len(sa & sb)
    larger = max(len(sa), len(sb))
    return overlap / larger


def find_align_diffs(corr: List[str], ans: List[str],
                     match_threshold: float = 0.50) -> List[dict]:
    """
    双指针对话分段差异分析。

    对两段对话列表做结构对齐：
    - 内容相似 → 指针同步推进（i++, j++）
    - corr[i]+corr[i+1] ≈ ans[j] → corrected_split
    - corr[i] ≈ ans[j]+ans[j+1] → answer_split
    - 尾部多出 → extra
    """
    diffs: List[dict] = []
    i = j = 0

    while i < len(corr) and j < len(ans):
        c_norm = strip_punct(corr[i][1:-1])
        a_norm = strip_punct(ans[j][1:-1])
        sim = text_similarity(c_norm, a_norm)

        if sim >= match_threshold:
            i += 1
            j += 1
            continue

        # Try corrected_split: corr[i] + corr[i+1] ≈ ans[j]
        if i + 1 < len(corr):
            merged_norm = strip_punct(corr[i][1:-1] + corr[i + 1][1:-1])
            sim_m = text_similarity(merged_norm, a_norm)
            if sim_m >= match_threshold:
                diffs.append({
                    "type": "corrected_split",
                    "corrected_idx": i,
                    "answer_idx": j,
                    "corrected": [corr[i][1:-1], corr[i + 1][1:-1]],
                    "answer": ans[j][1:-1],
                    "similarity": round(sim_m, 3),
                })
                i += 2
                j += 1
                continue

        # Try answer_split: corr[i] ≈ ans[j] + ans[j+1]
        if j + 1 < len(ans):
            merged_norm = strip_punct(ans[j][1:-1] + ans[j + 1][1:-1])
            sim_m = text_similarity(merged_norm, c_norm)
            if sim_m >= match_threshold:
                diffs.append({
                    "type": "answer_split",
                    "corrected_idx": i,
                    "answer_idx": j,
                    "corrected": corr[i][1:-1],
                    "answer": [ans[j][1:-1], ans[j + 1][1:-1]],
                    "similarity": round(sim_m, 3),
                })
                i += 1
                j += 2
                continue

        # No match — content differs but structurally parallel, advance both
        i += 1
        j += 1

    # Tail extras
    while i < len(corr):
        diffs.append({
            "type": "corrected_extra",
            "corrected_idx": i,
            "corrected": corr[i][1:-1],
        })
        i += 1
    while j < len(ans):
        diffs.append({
            "type": "answer_extra",
            "answer_idx": j,
            "answer": ans[j][1:-1],
        })
        j += 1

    return diffs


def report(corrected_path: str, answer_path: str, json_path: Optional[str] = None,
           align: bool = False) -> dict:
    corr_text = load_text(corrected_path)
    ans_text = load_text(answer_path)
    corr = extract_dialogues(corr_text)
    ans = extract_dialogues(ans_text)

    empty_c = sum(1 for d in corr if len(d[1:-1]) == 0)
    empty_a = sum(1 for d in ans if len(d[1:-1]) == 0)
    nonempty_c = len(corr) - empty_c
    nonempty_a = len(ans) - empty_a

    print(f"{'='*60}")
    print(f"  修正文件: {corrected_path}")
    print(f"  答案文件: {answer_path}")
    print(f"{'='*60}")
    print()
    print(f"{'':20s} {'总对话':>8s} {'空对话':>8s} {'非空':>8s}")
    print(f"{'修正后':20s} {len(corr):>8d} {empty_c:>8d} {nonempty_c:>8d}")
    print(f"{'答案':20s} {len(ans):>8d} {empty_a:>8d} {nonempty_a:>8d}")
    print(f"{'差异':20s} {len(corr)-len(ans):>+8d} {empty_c-empty_a:>+8d} {nonempty_c-nonempty_a:>+8d}")
    print()

    # 逐组对比前 min(len(corr), len(ans)) 段
    n = min(len(corr), len(ans))
    exact = content_ok = diff = 0
    samples: List[tuple[int, str, str]] = []

    for i in range(n):
        c_text = corr[i][1:-1]
        a_text = ans[i][1:-1]
        if c_text == a_text:
            exact += 1
        elif strip_punct(c_text) == strip_punct(a_text):
            content_ok += 1
        else:
            diff += 1
            if len(samples) < 15:
                samples.append((i + 1, corr[i], ans[i]))

    print(f"前 {n} 段逐组对比:")
    print(f"  完全一致:        {exact:>5d} ({exact/n*100:.1f}%)")
    print(f"  仅标点不同:      {content_ok:>5d} ({content_ok/n*100:.1f}%)")
    print(f"  内容有差异:      {diff:>5d} ({diff/n*100:.1f}%)")
    print()

    if samples:
        print(f"内容差异样本（前 {len(samples)} 组）:")
        for idx, c, a in samples:
            print(f"  [{idx}]")
            print(f"    修正: {c}")
            print(f"    答案: {a}")
            print()

    # 多出的对话
    if len(corr) > len(ans):
        print(f"\n修正文件比答案多 {len(corr)-len(ans)} 段:")
        for i in range(len(ans), len(corr)):
            print(f"  [{i+1}] {corr[i]}")

    if len(ans) > len(corr):
        print(f"\n答案文件比修正多 {len(ans)-len(corr)} 段:")
        for i in range(len(corr), len(ans)):
            print(f"  [{i+1}] {ans[i]}")

    # 构建 JSON 数据
    # 空对话位置
    empty_positions: List[dict] = []
    for d in corr:
        if len(d[1:-1]) == 0:
            # 查找在文本中的位置
            idx_in_text = corr_text.find(d)
            line_no = corr_text[:idx_in_text].count("\n") + 1 if idx_in_text >= 0 else 0
            ctx_start = max(0, idx_in_text - 20)
            ctx_end = min(len(corr_text), idx_in_text + len(d) + 20)
            context = corr_text[ctx_start:ctx_end].replace("\n", "\\n")
            empty_positions.append({
                "dialogue": d,
                "line": line_no,
                "offset": idx_in_text,
                "context": context,
            })

    # 多出的对话
    extra_dialogues: List[str] = []
    if len(corr) > len(ans):
        for i in range(len(ans), len(corr)):
            extra_dialogues.append(corr[i])

    # 分段差异分析（仅 --align）
    alignment_diffs: List[dict] = []
    if align:
        alignment_diffs = find_align_diffs(corr, ans)

        print(f"\n  -- Alignment Analysis --")
        print(f"  Total alignment diffs: {len(alignment_diffs)}")
        print()

        # 按类型统计
        type_counts: dict = {}
        for d in alignment_diffs:
            type_counts[d["type"]] = type_counts.get(d["type"], 0) + 1
        for t, c in sorted(type_counts.items()):
            print(f"    {t}: {c}")
        print()

        # 输出前 15 条
        print(f"  Alignment diffs (first 15):")
        for idx, d in enumerate(alignment_diffs[:15]):
            t = d["type"]
            if t == "corrected_split":
                print(f"  [{idx+1}] 修正分离(2段=答案1段) 修正#{d['corrected_idx']+1}")
                print(f"        修正: {'  +  '.join(d['corrected'])}")
                print(f"        答案: {d['answer']}")
            elif t == "answer_split":
                print(f"  [{idx+1}] 答案分离(答案2段=修正1段) 答案#{d['answer_idx']+1}")
                print(f"        修正: {d['corrected']}")
                print(f"        答案: {'  +  '.join(d['answer'])}")
            elif t == "corrected_extra":
                print(f"  [{idx+1}] 修正多一段 #{d['corrected_idx']+1}: {d['corrected'][:60]}")
            elif t == "answer_extra":
                print(f"  [{idx+1}] 答案多一段 #{d['answer_idx']+1}: {d['answer'][:60]}")
            print()

    data = {
        "corrected_total": len(corr),
        "corrected_empty": empty_c,
        "corrected_nonempty": nonempty_c,
        "answer_total": len(ans),
        "answer_empty": empty_a,
        "answer_nonempty": nonempty_a,
        "exact_matches": exact,
        "punct_differences": content_ok,
        "content_differences": diff,
        "total_compared": n,
        "empty_dialogues": empty_positions,
        "extra_dialogues": extra_dialogues,
        "alignment_diffs": alignment_diffs if align else [],
    }

    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\nJSON saved: {json_path}")

    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corrected", help="corrected file path")
    parser.add_argument("answer", help="answer file path")
    parser.add_argument("--json", default="", help="output JSON path")
    parser.add_argument("--align", action="store_true", help="run alignment analysis")
    args = parser.parse_args()

    report(args.corrected, args.answer, json_path=args.json or None, align=args.align)