"""
对话提取与对比工具

提取修正后文件和答案文件中的全部「」对话，按顺序逐组对比。
输出统计：总对话数、空对话数、内容匹配率、差异样本。

用法:
    python tools/compare_dialogues.py output/corrected_第1卷.txt data/answer_第1卷.txt
"""

import sys
import re
from typing import List


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


def report(corrected_path: str, answer_path: str):
    corr = extract_dialogues(load_text(corrected_path))
    ans = extract_dialogues(load_text(answer_path))

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
    samples: list[tuple[int, str, str]] = []

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

    return {
        "corrected_total": len(corr),
        "corrected_empty": empty_c,
        "corrected_nonempty": nonempty_c,
        "answer_total": len(ans),
        "answer_empty": empty_a,
        "answer_nonempty": nonempty_a,
        "exact_matches": exact,
        "punct_differences": content_ok,
        "content_differences": diff,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    report(sys.argv[1], sys.argv[2])
