#!/usr/bin/env python3
"""
tools/audit_detector_gap.py — 漏检审计工具

对修正后文件中残留的非标准符号逐个分析漏检原因。
读取修正后文件 → 扫描非标准符号 → 运行 DetectorPipeline
→ 对每个未被 Pipeline 命中的符号分类 → 输出分析表。

用法:
    python tools/audit_detector_gap.py output/corrected_第1卷.txt
    python tools/audit_detector_gap.py output/corrected_第1卷.txt --json output/audit.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.text import TextDoc
from src.detector.pipeline import DetectorPipeline
from src.io.loader import TextLoader


# ── 非标准符号定义（与 src/detector/wrong_symbol.py 保持一致） ──────────

NON_STANDARD_SYMBOLS: Dict[str, Optional[str]] = {
    "[": "「",
    "]": "」",
    "【": "「",
    "】": "」",
    "［": "「",
    "］": "」",
    "{": "「",
    "}": "」",
    "《": "「",
    "》": "」",
    "\u201c": "「",  # 弯引号开（左双引号）
    "\u201d": "」",  # 弯引号闭（右双引号）
}

OPENERS = {"[", "【", "［", "{", "《", "\u201c"}
CLOSERS = {"]", "】", "］", "}", "》", "\u201d"}

# 已知注释模式（SmartSkip 应该跳过的）
COMMENT_PATTERNS: List[str] = [
    "[1]", "[2]", "[3]", "[4]", "[5]", "[6]", "[7]", "[8]", "[9]", "[0]",
    "[注]", "[插图]", "[图]", "[表]", "[序号]",
]


# ── 数据结构 ──────────────────────────────────────────────────────


class LeakRecord:
    """单条漏检记录"""

    __slots__ = (
        "symbol", "offset", "line_number",
        "context_before", "context_after",
        "leak_reason", "surrounded_by",
        "is_digit", "is_short_text", "is_comment_pattern", "note",
    )

    def __init__(
        self,
        symbol: str, offset: int, line_number: int,
        context_before: str, context_after: str,
        leak_reason: str = "unknown",
        surrounded_by: str = "",
        is_digit: bool = False,
        is_short_text: bool = False,
        is_comment_pattern: bool = False,
        note: str = "",
    ):
        self.symbol = symbol
        self.offset = offset
        self.line_number = line_number
        self.context_before = context_before
        self.context_after = context_after
        self.leak_reason = leak_reason
        self.surrounded_by = surrounded_by
        self.is_digit = is_digit
        self.is_short_text = is_short_text
        self.is_comment_pattern = is_comment_pattern
        self.note = note

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "offset": self.offset,
            "line_number": self.line_number,
            "context_before": self.context_before[-80:],
            "context_after": self.context_after[:80],
            "leak_reason": self.leak_reason,
            "surrounded_by": self.surrounded_by,
            "is_digit": self.is_digit,
            "is_short_text": self.is_short_text,
            "is_comment_pattern": self.is_comment_pattern,
            "note": self.note,
        }


# ── 核心分析函数 ──────────────────────────────────────────────────


def find_non_standard_symbols(text_doc: TextDoc) -> List[dict]:
    """扫描文本中所有非标准符号，返回位置详情列表。"""
    results: List[dict] = []
    full_text = text_doc.text
    for offset, ch in enumerate(full_text):
        if ch in NON_STANDARD_SYMBOLS:
            line_num = text_doc.offset_to_line(offset)
            ctx_start = max(0, offset - 80)
            ctx_end = min(len(full_text), offset + 81)
            results.append({
                "symbol": ch,
                "offset": offset,
                "line_number": line_num,
                "context_before": full_text[ctx_start:offset],
                "context_after": full_text[offset + 1:ctx_end],
            })
    return results


def compute_bracket_depth_up_to(text: str, pos: int) -> int:
    """计算 text[:pos] 范围内「」嵌套深度（走到 pos 时的深度）。"""
    depth = 0
    for i, ch in enumerate(text[:pos]):
        if ch == "\u300c":
            depth += 1
        elif ch == "\u300d":
            depth = max(0, depth - 1)
    return depth


def check_is_digit_bracket(full_text: str, offset: int, symbol: str) -> bool:
    """检查 `[数字]` 模式。"""
    if symbol == "[":
        rest = full_text[offset + 1:offset + 15]
        close_pos = rest.find("]")
        if close_pos != -1 and close_pos < 8 and rest[:close_pos].strip().isdigit():
            return True
    if symbol == "]":
        before = full_text[max(0, offset - 15):offset]
        open_pos = before.rfind("[")
        if open_pos != -1:
            inner = before[open_pos + 1:offset].strip()
            if inner.isdigit():
                return True
    return False


def check_is_short_text_bracket(full_text: str, offset: int, symbol: str) -> bool:
    """检查 `[短文本]` 模式（6 个以内中文字符）。"""
    closer_map = {"[": "]", "【": "】", "［": "］", "{": "}", "《": "》"}
    closer = closer_map.get(symbol)
    if not closer:
        return False
    rest = full_text[offset + 1:offset + 25]
    close_pos = rest.find(closer)
    if close_pos == -1 or close_pos > 15:
        return False
    inner = rest[:close_pos]
    cjk_count = sum(1 for c in inner if "\u4e00" <= c <= "\u9fff")
    return cjk_count <= 6 and len(inner) <= 15


def check_comment_pattern(full_text: str, offset: int) -> bool:
    """检查是否匹配已知注释模式如 [注] [插图] [1] 等。"""
    for pattern in COMMENT_PATTERNS:
        if full_text[offset:offset + len(pattern)] == pattern:
            return True
    return False


def classify_leak(full_text: str, symbol: str, offset: int, line_number: int) -> LeakRecord:
    """对漏检符号分类。"""
    ctx_start = max(0, offset - 80)
    ctx_end = min(len(full_text), offset + 81)

    record = LeakRecord(
        symbol=symbol,
        offset=offset,
        line_number=line_number,
        context_before=full_text[ctx_start:offset],
        context_after=full_text[offset + 1:ctx_end],
    )

    depth = compute_bracket_depth_up_to(full_text, offset)
    nested = depth > 0
    record.surrounded_by = "\u300c\u300d" if nested else ""

    record.is_digit = check_is_digit_bracket(full_text, offset, symbol)
    record.is_short_text = check_is_short_text_bracket(full_text, offset, symbol)
    record.is_comment_pattern = check_comment_pattern(full_text, offset)

    # 分类优先级：nested > smart_skip > type_not_covered > unknown
    if nested:
        record.leak_reason = "nested"
        record.note = f"符号在\u300c\u300d内部(深度{depth})，WrongSymbolDetector 嵌套保护跳过"
    elif record.is_comment_pattern:
        record.leak_reason = "smart_skip"
        record.note = "匹配已知注释模式（如[注][插图]），_should_skip/_is_likely_comment 返回 True"
    elif record.is_short_text:
        record.leak_reason = "smart_skip"
        record.note = "匹配短括号模式（6个中文字以内），_looks_like_paired_bracket 返回 True"
    elif symbol in ("\u201c", "\u201d"):
        record.leak_reason = "type_not_covered"
        record.note = "弯引号检测覆盖不全，部分出现在\u300c\u300d外部但仍未被捕获"
    elif record.is_digit:
        # [数字] 在 \u300c\u300d 外部的情况 → 也是 SmartSkip
        record.leak_reason = "smart_skip"
        record.note = "匹配 [数字] 模式，_looks_like_paired_bracket 返回 True"
    else:
        record.leak_reason = "unknown"
        record.note = "不在\u300c\u300d内部且不匹配已知跳过模式，但仍未被 Pipeline 捕获"

    return record


# ── 主审计函数 ────────────────────────────────────────────────────


def run_audit(corrected_path: str) -> List[LeakRecord]:
    """执行审计，返回漏检分析结果。"""
    # 1. 加载文本
    text_doc = TextLoader().load(corrected_path)
    full_text = text_doc.text
    print(f"  Text: {len(full_text)} chars, {text_doc.line_count()} lines")

    # 2. 扫描非标准符号
    symbols = find_non_standard_symbols(text_doc)
    print(f"  Total non-standard symbols in file: {len(symbols)}")
    by_sym: Dict[str, int] = {}
    for s in symbols:
        by_sym[s["symbol"]] = by_sym.get(s["symbol"], 0) + 1
    for sym, cnt in sorted(by_sym.items(), key=lambda x: -x[1]):
        print(f"    {repr(sym)}: {cnt}")

    # 3. 运行 DetectorPipeline
    print("  Running DetectorPipeline...")
    pipeline = DetectorPipeline()
    queue = pipeline.run(text_doc)
    summary = queue.type_summary()
    print(f"  Pipeline detected: {queue.total} errors")
    for t, c in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    # 建立检测到的偏移索引
    detected_offsets = [err.offset for err in queue.all()]
    MERGE_RADIUS = 50  # 与 ErrorQueue.MERGE_RADIUS 一致

    # 4. 逐一检查
    results: List[LeakRecord] = []
    detected_count = 0

    for sym in symbols:
        offset = sym["offset"]
        symbol = sym["symbol"]
        line_num = sym["line_number"]

        # 检查 Pipeline 是否覆盖了这个符号
        is_detected = any(abs(offset - do) <= MERGE_RADIUS for do in detected_offsets)

        if is_detected:
            detected_count += 1
            continue

        # 漏检 → 分类
        record = classify_leak(full_text, symbol, offset, line_num)
        results.append(record)

    print(f"\n  ---")
    print(f"  Detected by pipeline: {detected_count}")
    print(f"  Missed (leaks):       {len(results)}")
    print(f"  Total non-standard:   {detected_count + len(results)}")

    return results


# ── 输出函数 ──────────────────────────────────────────────────────


def print_summary(results: List[LeakRecord]):
    """打印分类汇总。"""
    reasons: Dict[str, int] = {}
    symbols: Dict[str, int] = {}
    for r in results:
        reasons[r.leak_reason] = reasons.get(r.leak_reason, 0) + 1
        symbols[r.symbol] = symbols.get(r.symbol, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"  漏检分析汇总")
    print(f"{'=' * 60}")
    print(f"  总计漏检: {len(results)}")

    print(f"\n  ── 按原因分类 ──")
    print(f"  {'原因':<20} {'数量':<8} {'占比':<8}")
    print(f"  {'-' * 36}")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        pct = count / len(results) * 100
        print(f"  {reason:<20} {count:<8} {pct:>6.1f}%")

    print(f"\n  ── 按符号分类 ──")
    print(f"  {'符号':<8} {'数量':<8} {'占比':<8}")
    print(f"  {'-' * 28}")
    for sym, count in sorted(symbols.items(), key=lambda x: -x[1]):
        pct = count / len(results) * 100
        print(f"  {repr(sym):<8} {count:<8} {pct:>6.1f}%")


def print_table(results: List[LeakRecord]):
    """打印详细表格。"""
    print(f"\n{'=' * 130}")
    print(f"  漏检明细表")
    print(f"{'=' * 130}")
    hdr = (
        f"  {'#':<4} {'符号':<8} {'行号':<6} {'偏移':<8} "
        f"{'漏检原因':<18} {'内部':<5} {'数字':<5} {'短文':<5} "
        f" 上下文"
    )
    print(hdr)
    print(f"  {'-' * 128}")

    for i, r in enumerate(results[:200], 1):  # 最多 200 行
        ctx_before = r.context_before[-25:].replace("\n", "\\n")
        ctx_after = r.context_after[:25].replace("\n", "\\n")
        ctx = f"{ctx_before}\u2192{ctx_after}"
        n = "\u2611" if r.surrounded_by else "\u2610"
        d = "\u2611" if r.is_digit else "\u2610"
        s = "\u2611" if r.is_short_text else "\u2610"
        print(
            f"  {i:<4} {repr(r.symbol):<8} {r.line_number:<6} {r.offset:<8} "
            f"{r.leak_reason:<18} {n:<5} {d:<5} {s:<5} {ctx}"
        )

    print(f"  {'-' * 128}")
    print(f"  Total: {len(results)} records (showing first 200)")


def save_json(results: List[LeakRecord], output_path: str):
    """保存为 JSON。"""
    reasons: Dict[str, int] = {}
    symbols: Dict[str, int] = {}
    for r in results:
        reasons[r.leak_reason] = reasons.get(r.leak_reason, 0) + 1
        symbols[r.symbol] = symbols.get(r.symbol, 0) + 1

    data = {
        "total": len(results),
        "summary": {
            "by_reason": dict(sorted(reasons.items(), key=lambda x: -x[1])),
            "by_symbol": dict(sorted(symbols.items(), key=lambda x: -x[1])),
        },
        "records": [r.to_dict() for r in results],
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  JSON saved: {output_path}")


# ── 入口 ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="漏检审计工具 — 对修正后文件中的非标准符号逐个分析漏检原因"
    )
    parser.add_argument("corrected_file", help="修正后文件路径")
    parser.add_argument(
        "--json", default="output/audit_detector_gap.json",
        help="JSON 输出路径 (默认: output/audit_detector_gap.json)",
    )
    parser.add_argument(
        "--no-table", action="store_true",
        help="不打印详细表格",
    )
    args = parser.parse_args()

    if not Path(args.corrected_file).exists():
        print(f"Error: file not found: {args.corrected_file}")
        sys.exit(1)

    print(f"Audit: {args.corrected_file}")
    results = run_audit(args.corrected_file)

    print_summary(results)

    if not args.no_table:
        print_table(results)

    save_json(results, args.json)

    print(f"\nDone. {len(results)} leak records.")


if __name__ == "__main__":
    main()
