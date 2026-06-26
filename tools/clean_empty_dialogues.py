"""
确定性清理修正后文件中的空 `「」` artifact。

这些空对话是 WrongSymbolDetector 在处理不成对 `[]` 时产生的残留。
本工具用确定性规则删除它们，不涉及 LLM。

用法:
    python tools/clean_empty_dialogues.py output/corrected_第1卷.txt
    python tools/clean_empty_dialogues.py output/corrected_第1卷.txt --output output/corrected_第1卷_clean.txt
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def save_text(path: str, text: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def find_empty_dialogues(text: str) -> List[Tuple[int, int, str]]:
    """
    定位所有空 `「」` (不含任何可见字符)。

    Returns:
        List of (start_offset, end_offset, context_before)
    """
    results: List[Tuple[int, int, str]] = []
    pattern = re.compile(r"\u300c[\s]*\u300d")

    for m in pattern.finditer(text):
        start = m.start()
        end = m.end()
        content = text[start + 1 : end - 1]  # between brackets
        if len(content.strip()) == 0:
            ctx_start = max(0, start - 15)
            ctx = text[ctx_start:start].replace("\n", "\\n")
            results.append((start, end, ctx))

    return results


def clean_text(text: str, verbose: bool = True) -> Tuple[str, List[dict]]:
    """
    删除所有空 `「」`。

    规则：
    1. 如果形态为 `。「」` → 只删除 `「」`，保留前导的句号
    2. 如果形态为 `。「 」` → 同上
    3. 如果形态为 `。「」\n` → 只删 `「」`
    4. 其他裸 `「」` → 只删括号本身

    删除后保持 quote balance。
    """
    ops: List[dict] = []
    pos = 0
    cleaned = []
    empty_spans = find_empty_dialogues(text)

    if verbose:
        print(f"发现 {len(empty_spans)} 个空 `「」`")
        print()

    # Sort by start position
    empty_spans.sort(key=lambda x: x[0])

    for start, end, ctx in empty_spans:
        # Append text before this empty dialogue
        cleaned.append(text[pos:start])

        # Record the deletion
        line_no = text[:start].count("\n") + 1
        ops.append({
            "offset": start,
            "length": end - start,
            "removed": text[start:end],
            "line": line_no,
            "context": ctx,
            "action": "deleted",
        })

        if verbose:
            print(f"  [行 {line_no}] 删除 {repr(text[start:end])}  上下文: ...{ctx}...")

        pos = end

    # Append remaining text
    cleaned.append(text[pos:])
    result = "".join(cleaned)

    # Verify
    left = result.count("\u300c")
    right = result.count("\u300d")
    balanced = left == right
    non_std = sum(1 for ch in result if ch in "[]\u3010\u3011{}\u300a\u300b\u201c\u201d")

    if verbose:
        print()
        print(f"清理完成: 删除了 {len(ops)} 个空 `「」`")
        print(f"Quote balance: {'[OK]' if balanced else '[NG]'}  ({left} vs {right})")
        print(f"Non-standard symbols: {non_std}")

    return result, ops


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="corrected novel file path")
    parser.add_argument("--output", default="", help="output file path (default: in-place)")
    parser.add_argument("--json", default="", help="save ops report as JSON")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 1

    text = load_text(args.input)
    cleaned, ops = clean_text(text)

    output_path = args.output or args.input
    save_text(output_path, cleaned)
    print(f"Saved: {output_path}")

    if args.json:
        report = {
            "input": args.input,
            "output": output_path,
            "removed_count": len(ops),
            "operations": ops,
            "quote_left": cleaned.count("\u300c"),
            "quote_right": cleaned.count("\u300d"),
            "balanced": cleaned.count("\u300c") == cleaned.count("\u300d"),
        }
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"Report JSON saved: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())