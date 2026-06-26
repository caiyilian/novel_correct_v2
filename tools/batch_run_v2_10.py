"""
batch_run_v2_10.py — 对第2~10卷跑一遍当前工具链，输出基准报告。

流程（每卷）：
1. 复制原始文本到 output/corrected_第X卷.txt
2. clean_empty_dialogues → 清理空「」
3. generate_style_candidates + --apply-low-risk → 应用低风险标点修正
4. generate_style_candidates 高风险 → style_candidates_high.jsonl
5. compare_dialogues → 与答案对比
6. verify_against_answer → 白空格忽略匹配率

Stage 1 产物规范（每卷）：
- corrected_第X卷.txt        — 修正后最终文本
- verify_第X卷.json          — verify_against_answer 报告
- compare_第X卷.json         — compare_dialogues 对齐报告
- decisions_第X卷.jsonl      — 修正决策日志（Ollama/人工裁决时生成）

跨卷汇总：
- final_report_10_volumes.json  — 统一最终汇总
- batch_report_v2_10.json       — 基准报告（同内容，别名）

decisions_第X卷.jsonl 记录格式：
  {
    "candidate_id": "c1",
    "volume": "第X卷",
    "offset": 1234,
    "original": ".",
    "candidate": "。",
    "source": "style_candidates",
    "decision": "apply|keep|uncertain",
    "decision_method": "ollama|rule|manual",
    "verification": "passed|failed|skipped",
    "reason": "reason for skip/keep/uncertain"
  }
"""

import json
import re
import sys
import time
from pathlib import Path

# Add project root and tools dir
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tools"))

import clean_empty_dialogues as clean_mod
import generate_style_candidates as cand_mod
from compare_dialogues import report as compare_report
from verify_against_answer import generate_report as verify_report, save_json

ORI_DIR = Path("data/ori_story")
ANSWER_DIR = Path("data/answer")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VOLUMES = list(range(2, 11))  # 2-10


from src.io.loader import TextLoader


def load_text(path):
    """Load text with encoding auto-detection."""
    return TextLoader().load(str(path)).text


def save_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def run_for_volume(vol):
    """Run the full pipeline for a single volume. Returns result dict."""
    novel_name = f"第{vol}卷"
    results = {"volume": novel_name, "vol_num": vol}

    ori_path = ORI_DIR / f"{novel_name}.txt"
    ans_path = ANSWER_DIR / f"answer_{novel_name}.txt"
    corr_path = OUTPUT_DIR / f"corrected_{novel_name}.txt"
    clean_path = OUTPUT_DIR / f"corrected_{novel_name}_clean.txt"
    candidates_path = OUTPUT_DIR / f"style_candidates_{novel_name}.jsonl"
    high_risk_path = OUTPUT_DIR / f"style_candidates_{novel_name}_high.jsonl"

    if not ori_path.exists():
        return {"volume": novel_name, "error": f"原文件不存在: {ori_path}"}
    if not ans_path.exists():
        return {"volume": novel_name, "error": f"答案文件不存在: {ans_path}"}

    # ── Step 0: 复制原始文本 ──
    save_text(str(corr_path), load_text(str(ori_path)))
    results["original_chars"] = len(load_text(str(ori_path)))

    # ── Step 1: clean_empty_dialogues ──
    print(f"  [1] clean_empty_dialogues...", end=" ", flush=True)
    text = load_text(str(corr_path))
    cleaned, ops = clean_mod.clean_text(text, verbose=False)
    save_text(str(clean_path), cleaned)
    results["empty_removed"] = len(ops)
    left = cleaned.count("\u300c")
    right = cleaned.count("\u300d")
    results["clean_balance"] = {"left": left, "right": right,
                                "balanced": left == right}
    print(f"{len(ops)} empty removed, balance {left}/{right} {'OK' if left==right else 'NG'}")

    # ── Step 2: 检测原始文本　quote 统计 ──
    original_text = load_text(str(ori_path))
    o_left = original_text.count("\u300c")
    o_right = original_text.count("\u300d")
    results["original_quotes"] = {"left": o_left, "right": o_right,
                                   "balanced": o_left == o_right}

    # ── Step 3: generate_style_candidates (on cleaned text) ──
    print(f"  [2] generate_style_candidates...", end=" ", flush=True)
    candidates = cand_mod.generate_candidates(cleaned)
    low_risk = [c for c in candidates if c.get("auto_applicable")]
    high_risk = [c for c in candidates if not c.get("auto_applicable")]
    results["candidates"] = {
        "total": len(candidates),
        "low_risk": len(low_risk),
        "high_risk": len(high_risk),
    }

    # Save all candidates
    with open(candidates_path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Save high-risk only
    if high_risk:
        with open(high_risk_path, "w", encoding="utf-8") as f:
            for c in high_risk:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Apply low-risk automatically
    punct_fixed = cand_mod.apply_low_risk(text=cleaned, candidates=candidates)
    save_text(str(corr_path), punct_fixed)
    results["low_risk_applied"] = len(low_risk)
    print(f"total={len(candidates)}, low={len(low_risk)}, high={len(high_risk)}")

    # ── Step 4: compare_dialogues (corrected vs answer) ──
    print(f"  [3] compare_dialogues...", end=" ", flush=True)
    try:
        cmp = compare_report(
            corrected_path=str(corr_path),
            answer_path=str(ans_path),
            json_path=str(OUTPUT_DIR / f"compare_{novel_name}.json"),
            align=False,
        )
        results["comparison"] = {
            "corrected_total": cmp["corrected_total"],
            "corrected_empty": cmp["corrected_empty"],
            "answer_total": cmp["answer_total"],
            "answer_empty": cmp["answer_empty"],
            "exact_matches": cmp["exact_matches"],
            "punct_differences": cmp["punct_differences"],
            "content_differences": cmp["content_differences"],
            "total_compared": cmp["total_compared"],
        }
        if cmp["corrected_total"] > 0:
            results["comparison"]["exact_pct"] = round(
                cmp["exact_matches"] / cmp["corrected_total"] * 100, 1)
        print(f"{cmp['corrected_total']} dialogues, {cmp['exact_matches']} exact matches")
    except Exception as e:
        print(f"ERROR: {e}")
        results["comparison_error"] = str(e)

    # ── Step 5: verify_against_answer (whitespace-ignored match rate) ──
    print(f"  [4] verify_against_answer...", end=" ", flush=True)
    verify_path = str(OUTPUT_DIR / f"verify_{novel_name}.json")
    try:
        vrf = verify_report(
            corrected_path=str(corr_path),
            answer_path=str(ans_path),
        )
        # Save verify JSON per volume
        save_json(vrf, verify_path)
        results["verification"] = {
            "match_rate": vrf["matching"]["match_rate"],
            "matching_chars": vrf["matching"]["matching_chars_no_whitespace"],
            "total_chars": vrf["matching"]["total_answer_chars_no_whitespace"],
            "diff_snippets": vrf["diff_snippets_count"],
        }
        results["symbols"] = {
            "corrected": vrf["symbol_stats"]["corrected"],
            "answer": vrf["symbol_stats"]["answer"],
        }
        results["verify_saved"] = verify_path
        print(f"match rate: {vrf['matching']['match_rate']:.4f}")
    except Exception as e:
        print(f"ERROR: {e}")
        results["verification_error"] = str(e)

    # ── Step 6: 答案本身的 quote 统计 ──
    ans_text = load_text(str(ans_path))
    a_left = ans_text.count("\u300c")
    a_right = ans_text.count("\u300d")
    results["answer_quotes"] = {"left": a_left, "right": a_right,
                                 "balanced": a_left == a_right}

    # ── Step 7: main.py --detect ──
    print(f"  [5] main.py --detect...", end=" ", flush=True)
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, "main.py", str(ori_path), "--detect"],
            capture_output=True, text=True, timeout=120
        )
        # Parse total errors
        for line in r.stdout.split("\n"):
            if "Total:" in line and "errors" in line:
                m = re.search(r"Total:\s*(\d+)", line)
                if m:
                    results["detected_errors"] = int(m.group(1))
                    break
        print(f"{results.get('detected_errors', '?')} errors detected")
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        results["detection_timeout"] = True
    except Exception as e:
        print(f"ERROR: {e}")
        results["detection_error"] = str(e)

    return results


def main():
    print("=" * 65)
    print("  Batch Run: 第2卷 ~ 第10卷 — 当前工具链基准测试")
    print("=" * 65)
    print()

    all_results = []

    for vol in VOLUMES:
        novel_name = f"第{vol}卷"
        print(f"\n{'─' * 55}")
        print(f"  [{novel_name}]")
        print(f"{'─' * 55}")

        t0 = time.time()
        result = run_for_volume(vol)
        elapsed = time.time() - t0
        result["elapsed_seconds"] = round(elapsed, 1)
        all_results.append(result)

        print(f"  [{novel_name}] done in {elapsed:.0f}s")

    # ── 汇总 ──
    print("\n\n" + "=" * 65)
    print("  汇总")
    print("=" * 65)
    print()
    header = f"{'卷':>6s} {'原文本':>7s} {'空删除':>6s} {'候选总数':>8s} {'低风险':>6s} {'高风险':>6s} | {'对话比':>8s} {'精确':>7s} {'仅标点':>7s} {'内容差':>7s} | {'匹配率':>8s} {'检测':>6s}"
    sep = "─" * 95
    print(sep)
    print(header)
    print(sep)

    summary = {
        "total_volumes": len(all_results),
        "volumes": [],
        "totals": {
            "original_quotes": {"left": 0, "right": 0},
            "answer_quotes": {"left": 0, "right": 0},
            "exact_matches": 0,
            "punct_differences": 0,
            "content_differences": 0,
            "total_compared": 0,
            "detected_errors": 0,
            "empty_removed": 0,
            "low_risk_applied": 0,
            "high_risk_candidates": 0,
        },
    }

    for r in all_results:
        vol = r["vol_num"]
        vol_label = f"第{vol}卷"
        cmp = r.get("comparison", {}) or {}
        vrf = r.get("verification", {}) or {}
        det = r.get("detected_errors", 0) or 0

        dlg_ratio = f"{cmp.get('corrected_total',0)}/{cmp.get('answer_total',0)}"
        line = (
            f"{vol_label:>6s} "
            f"{r.get('original_chars', 0):>7,d} "
            f"{r.get('empty_removed', 0):>6d} "
            f"{r.get('candidates', {}).get('total', 0):>8d} "
            f"{r.get('candidates', {}).get('low_risk', 0):>6d} "
            f"{r.get('candidates', {}).get('high_risk', 0):>6d} | "
            f"{dlg_ratio:>8s} "
            f"{cmp.get('exact_matches', 0):>7d} "
            f"{cmp.get('punct_differences', 0):>7d} "
            f"{cmp.get('content_differences', 0):>7d} | "
            f"{vrf.get('match_rate', 0):>8.2%} "
            f"{det if det else '?' :>6}"
        )
        print(line)

        oq = r.get("original_quotes", {})
        aq = r.get("answer_quotes", {})
        summary["totals"]["original_quotes"]["left"] += oq.get("left", 0)
        summary["totals"]["original_quotes"]["right"] += oq.get("right", 0)
        summary["totals"]["answer_quotes"]["left"] += aq.get("left", 0)
        summary["totals"]["answer_quotes"]["right"] += aq.get("right", 0)
        summary["totals"]["exact_matches"] += cmp.get("exact_matches", 0)
        summary["totals"]["punct_differences"] += cmp.get("punct_differences", 0)
        summary["totals"]["content_differences"] += cmp.get("content_differences", 0)
        summary["totals"]["total_compared"] += cmp.get("total_compared", 0)
        summary["totals"]["detected_errors"] += det
        summary["totals"]["empty_removed"] += r.get("empty_removed", 0)
        summary["totals"]["low_risk_applied"] += r.get("low_risk_applied", 0)
        summary["totals"]["high_risk_candidates"] += r.get("candidates", {}).get("high_risk", 0)

    print(sep)
    t = summary["totals"]
    total_exact = t["exact_matches"]
    total_compared = t["total_compared"]
    exact_pct = total_exact / total_compared * 100 if total_compared else 0
    print(
        f"{'合计':>6s} "
        f"{'':>7s} "
        f"{t['empty_removed']:>6d} "
        f"{'':>8s} "
        f"{t['low_risk_applied']:>6d} "
        f"{t['high_risk_candidates']:>6d} | "
        f"{f'{total_compared}':>8s} "
        f"{t['exact_matches']:>7d} "
        f"{t['punct_differences']:>7d} "
        f"{t['content_differences']:>7d} | "
        f"{'':>8s} "
        f"{t['detected_errors']:>6d}"
    )
    print()

    print(f"  Quote Balance（原始 vs 答案）:")
    oq = t["original_quotes"]
    aq = t["answer_quotes"]
    print(f"    原始「: {oq['left']:,} 原始」: {oq['right']:,}  {'OK' if oq['left']==oq['right'] else 'NG'}")
    print(f"    答案「: {aq['left']:,} 答案」: {aq['right']:,}  {'OK' if aq['left']==aq['right'] else 'NG'}")
    print(f"    精确匹配率: {exact_pct:.1f}%")
    print(f"    检测错误总数: {t['detected_errors']:,}")
    print(f"    空「」删除: {t['empty_removed']}")
    print(f"    低风险标点自动修正: {t['low_risk_applied']}")
    print(f"    高风险标点（需 Ollama 裁决）: {t['high_risk_candidates']}")

    summary["exact_match_pct"] = round(exact_pct, 1)
    summary["volumes"] = all_results

    # Save reports
    report_path = OUTPUT_DIR / "batch_report_v2_10.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  JSON report saved: {report_path}")

    # Also save as final_report_10_volumes.json (Stage 1 convention)
    final_path = OUTPUT_DIR / "final_report_10_volumes.json"
    save_json(summary, str(final_path))

    # Save text report
    txt_path = OUTPUT_DIR / "batch_report_v2_10.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"Batch Report: 第2卷~第10卷 — 当前工具链基准测试\n")
        f.write(f"={'-'*60}=\n\n")
        f.write(header + "\n")
        f.write(sep + "\n")
        for r in all_results:
            vol = r["vol_num"]
            cmp = r.get("comparison", {}) or {}
            vrf = r.get("verification", {}) or {}
            det = r.get("detected_errors", 0) or 0
        vol_label = f"第{vol}卷"
        dlg_ratio = f"{cmp.get('corrected_total',0)}/{cmp.get('answer_total',0)}"
        f.write(
            f"{vol_label:>6s} "
            f"{r.get('original_chars', 0):>7,d} "
            f"{r.get('empty_removed', 0):>6d} "
            f"{r.get('candidates', {}).get('total', 0):>8d} "
            f"{r.get('candidates', {}).get('low_risk', 0):>6d} "
            f"{r.get('candidates', {}).get('high_risk', 0):>6d} | "
            f"{dlg_ratio:>8s} "
            f"{cmp.get('exact_matches', 0):>7d} "
            f"{cmp.get('punct_differences', 0):>7d} "
            f"{cmp.get('content_differences', 0):>7d} | "
            f"{vrf.get('match_rate', 0):>8.2%} "
            f"{det if det else '?' :>6}\n"
        )
        f.write(sep + "\n")
        f.write(f"合计: 空删除={t['empty_removed']}, 低风险={t['low_risk_applied']}, 高风险={t['high_risk_candidates']}\n")
        f.write(f"精确匹配率: {exact_pct:.1f}% ({t['exact_matches']}/{t['total_compared']})\n")
        f.write(f"检测错误总数: {t['detected_errors']:,}\n")
    print(f"  Text report saved: {txt_path}")

    print(f"\n{'=' * 65}")
    print(f"  Done. All results in output/")
    print(f"{'=' * 65}\n")

    return summary


if __name__ == "__main__":
    summary = main()
