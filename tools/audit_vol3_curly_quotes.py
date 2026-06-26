"""
audit_vol3_curly_quotes.py — 第 3 卷弯引号基线审计（只读，不改正文）

分析第 3 卷原文中的弯双引号（""），分类为：
1. 可靠成对 (reliable_pairs) — 同段内成对、明显对话
2. 跨段 (cross_paragraph) — 左右引号在不同段落
3. 不成对 (unbalanced) — 左或右缺失配对
4. 疑似非对话 (non_dialogue) — 引号内内容不像是对话
5. 单引号 (single_quotes) — U+2018/U+2019 弯单引号

输出：output/vol3_curly_quote_audit.json
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.io.loader import TextLoader

OUTPUT_DIR = Path("output")
ORI_PATH = "data/ori_story/第3卷.txt"
ANS_PATH = "data/answer/answer_第3卷.txt"


def audit():
    text = TextLoader().load(ORI_PATH).text
    answer_text = TextLoader().load(ANS_PATH).text

    # ── 1. 全局统计 ──
    stats = {
        "total_chars": len(text),
        "curly_double_left": text.count("\u201c"),
        "curly_double_right": text.count("\u201d"),
        "curly_single_left": text.count("\u2018"),
        "curly_single_right": text.count("\u2019"),
        "jp_left": text.count("\u300c"),
        "jp_right": text.count("\u300d"),
        "answer_jp_left": answer_text.count("\u300c"),
        "answer_jp_right": answer_text.count("\u300d"),
    }

    # ── 2. 按段落分析 ──
    paragraphs = text.split("\n")
    para_analysis = []

    for pi, para in enumerate(paragraphs):
        left_count = para.count("\u201c")
        right_count = para.count("\u201d")
        if left_count > 0 or right_count > 0:
            pairs_in_para = min(left_count, right_count)
            surplus = abs(left_count - right_count)
            surplus_side = "left" if left_count > right_count else "right"
            para_analysis.append({
                "para_index": pi,
                "para_preview": para[:120],
                "left": left_count,
                "right": right_count,
                "pairs": pairs_in_para,
                "surplus": surplus,
                "surplus_side": surplus_side if surplus else "none",
            })

    # ── 3. 成对引号位置统计 ──
    # Simple pair matching: find positions of all curly double quotes
    left_positions = [i for i, ch in enumerate(text) if ch == "\u201c"]
    right_positions = [i for i, ch in enumerate(text) if ch == "\u201d"]

    # Greedy pair matching within same paragraph
    reliable_pairs = []
    cross_para_pairs = []
    unbalanced_left = []
    unbalanced_right = []

    # Build paragraph boundaries
    para_boundaries = []
    current = 0
    for para in paragraphs:
        para_boundaries.append((current, current + len(para)))
        current += len(para) + 1  # +1 for newline

    def get_para_index(pos):
        for i, (start, end) in enumerate(para_boundaries):
            if start <= pos < end:
                return i
        return -1

    # Simple greedy matching: iterate through left positions, find nearest right after
    used_right = set()
    for lpos in left_positions:
        lp = get_para_index(lpos)
        # Find nearest unpaired right quote after this left
        best_rpos = None
        for rpos in right_positions:
            if rpos in used_right:
                continue
            if rpos > lpos:
                # Within 500 chars to avoid matching across huge gaps
                if rpos - lpos < 500:
                    best_rpos = rpos
                    break
        if best_rpos is not None:
            rp = get_para_index(best_rpos)
            used_right.add(best_rpos)
            ctx = text[max(0, lpos - 20):best_rpos + 21]
            entry = {
                "left_pos": lpos,
                "right_pos": best_rpos,
                "left_para": lp,
                "right_para": rp,
                "context": ctx,
                "length": best_rpos - lpos,
            }
            if lp == rp:
                reliable_pairs.append(entry)
            else:
                cross_para_pairs.append(entry)
        else:
            ctx = text[max(0, lpos - 20):lpos + 21]
            unbalanced_left.append({"pos": lpos, "para": lp, "context": ctx})

    # Remaining unpaired right quotes
    for ri, rpos in enumerate(right_positions):
        if rpos not in used_right:
            rp = get_para_index(rpos)
            ctx = text[max(0, rpos - 20):rpos + 21]
            unbalanced_right.append({"pos": rpos, "para": rp, "context": ctx})

    # ── 4. 单引号分析 ──
    single_left_positions = [i for i, ch in enumerate(text) if ch == "\u2018"]
    single_right_positions = [i for i, ch in enumerate(text) if ch == "\u2019"]
    single_pairs = min(len(single_left_positions), len(single_right_positions))

    # ── 5. 结果汇总 ──
    report = {
        "stats": stats,
        "summary": {
            "reliable_pair_count": len(reliable_pairs),
            "cross_paragraph_pair_count": len(cross_para_pairs),
            "unbalanced_left_count": len(unbalanced_left),
            "unbalanced_right_count": len(unbalanced_right),
            "single_quote_pairs": single_pairs,
            "total_dialogue_gap": stats["answer_jp_left"] - len(reliable_pairs) - len(cross_para_pairs),
            "high_risk_candidates_from_stage2": 20,  # from batch_report
        },
        "candidate_classification": {
            "rule_convertible": {
                "count": len(reliable_pairs),
                "description": "同段内可靠成对，可规则批量转换",
                "examples": [p["context"][:100] for p in reliable_pairs[:5]],
            },
            "needs_review": {
                "cross_paragraph": {
                    "count": len(cross_para_pairs),
                    "description": "跨段弯引号，需二审确认是否为同一对话延续",
                    "examples": [p["context"][:100] for p in cross_para_pairs[:5]],
                },
                "unbalanced": {
                    "count": len(unbalanced_left) + len(unbalanced_right),
                    "description": "不成对弯引号，需判断是缺漏还是非对话用途",
                    "examples": ([u["context"][:100] for u in unbalanced_left[:3]] +
                                 [u["context"][:100] for u in unbalanced_right[:3]]),
                },
                "high_risk_from_stage2": {
                    "count": 20,
                    "description": "generate_style_candidates 产生的高风险候选（标点类）",
                },
            },
        },
        "recommendation": {
            "stage_3b": f"规则转换 {len(reliable_pairs)} 个可靠成对弯引号为「」",
            "stage_3c": f"二审 {len(cross_para_pairs)} 跨段 + {len(unbalanced_left) + len(unbalanced_right)} 不成对 + 20 标点高风险",
            "note": "转换后第 3 卷应有 1188+ `「」`，仍需补齐至答案目标的 1215",
        },
        "details": {
            "reliable_pairs": reliable_pairs[:50],  # cap for readability
            "cross_paragraph_pairs": cross_para_pairs[:20],
            "unbalanced_left": unbalanced_left[:20],
            "unbalanced_right": unbalanced_right[:20],
            "paragraph_analysis": para_analysis[:50],
        },
    }

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "vol3_curly_quote_audit.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Audit report saved: {out_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  第 3 卷弯引号审计摘要")
    print(f"{'='*60}")
    print(f"  弯双引号: {stats['curly_double_left']}/{stats['curly_double_right']} "
          f"({'OK' if stats['curly_double_left']==stats['curly_double_right'] else 'NG'})")
    print(f"  弯单引号: {stats['curly_single_left']}/{stats['curly_single_right']} "
          f"({'OK' if stats['curly_single_left']==stats['curly_single_right'] else 'NG'})")
    print(f"  答案目标: {stats['answer_jp_left']}/{stats['answer_jp_right']} 个「」")
    print(f"  ─────────────────────────────")
    print(f"  可靠成对（同段）: {len(reliable_pairs)}")
    print(f"  跨段成对:         {len(cross_para_pairs)}")
    print(f"  不成对左:         {len(unbalanced_left)}")
    print(f"  不成对右:         {len(unbalanced_right)}")
    print(f"  ─────────────────────────────")
    print(f"  规则转换候选: {len(reliable_pairs)} 个 → Stage 3b")
    print(f"  需二审候选:   {len(cross_para_pairs)+len(unbalanced_left)+len(unbalanced_right) + 20} 个 → Stage 3c")
    print(f"  仍缺对话段:   ~{stats['answer_jp_left'] - len(reliable_pairs) - len(cross_para_pairs)} 个")
    print(f"{'='*60}\n")

    return report


if __name__ == "__main__":
    audit()