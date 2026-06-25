"""
main.py — novel_correct_v2 CLI 入口

完整纠错管线：检测 → Agent 修正 → 重新检测 → 终止判断。

用法：
    python main.py data/ori_story/第1卷.txt          # 完整纠错
    python main.py data/ori_story/第1卷.txt --detect  # 只检测
    python main.py data/ori_story/第1卷.txt --resume  # 从 checkpoint 恢复
    python main.py --batch data/ori_story/            # 批量处理
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from src.core.text import TextDoc
from src.core.error_queue import ErrorQueue
from src.core.progress import ProgressTracker
from src.detector.pipeline import DetectorPipeline
from src.model.client import ChatMessage, ModelConfig, OpenAICompatibleClient
from src.model.token_tracker import TokenTracker
from src.agent.loop import CorrectionAgent
from src.agent.decision import CandidateDecisionAgent
from src.verifier.agent import CorrectionVerifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="novel_correct_v2 — 小说自动纠错系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py data/ori_story/第1卷.txt           完整纠错
  python main.py data/ori_story/第1卷.txt --detect   只检测，不修正
  python main.py data/ori_story/第1卷.txt --resume   从 checkpoint 恢复
  python main.py --batch data/ori_story/             批量处理全部
        """,
    )
    parser.add_argument("novel", nargs="?", type=str,
                        help="小说文件路径")
    parser.add_argument("--batch", type=str, metavar="DIR",
                        help="批量处理目录下的所有 .txt 文件")
    parser.add_argument("--detect", action="store_true",
                        help="只检测错误，不进行修正")
    parser.add_argument("--resume", action="store_true",
                        help="从 checkpoint 恢复（跳过已处理的错误）")
    parser.add_argument("--dry-run", action="store_true",
                        help="干跑模式：检测 + 打印每个错误，不调 LLM")
    parser.add_argument("--report", action="store_true",
                        help="只查看上次纠错报告，不运行")
    parser.add_argument("--model", type=str, default="",
                        help="模型名（覆盖 ip_config 中的配置）")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="每个错误的最大重试次数（默认 3）")
    parser.add_argument("--max-rounds", type=int, default=5,
                        help="每次尝试的最大 Agent 对话轮数（默认 5）")
    parser.add_argument("--max-decision-retries", type=int, default=2,
                        help="候选决策模式下每个错误的最大 LLM 判断次数（默认 2）")
    parser.add_argument("--agent-tool-mode", action="store_true",
                        help="使用旧的 tool-calling Agent 模式（默认使用候选决策模式）")
    parser.add_argument("--llm-decision-fallback", action="store_true",
                        help="候选规则预检无法确定时继续调用 LLM 判断（默认直接跳过，避免长时间挂起）")
    parser.add_argument("--max-pipeline-rounds", type=int, default=3,
                        help="多轮纠错的最大轮数（默认 3）")
    return parser.parse_args()


# ── 管线核心 ──────────────────────────────────────────

def run_pipeline(
    novel_path: str,
    resume: bool = False,
    detect: bool = False,
    dry_run: bool = False,
    model_name: str = "",
    max_retries: int = 3,
    max_rounds: int = 5,
    max_decision_retries: int = 2,
    agent_tool_mode: bool = False,
    llm_decision_fallback: bool = False,
    max_pipeline_rounds: int = 3,
) -> None:
    """
    完整纠错管线。

    流程：
    Phase 0: 加载文本
    Phase 1: 全量检测 → ErrorQueue
    Phase 2: Agent 逐条修正（逐个调 LLM）
    Phase 3: 重新检测 → 如果有新错误 → 回到 Phase 2
             连续 2 轮零错误 → 终止
    """
    print(f"\n{'='*55}")
    print(f"  novel_correct_v2 — {Path(novel_path).name}")
    print(f"{'='*55}\n")

    # Phase 0: 加载
    print("[1/3] Loading text...")
    from src.io.loader import TextLoader
    text = TextLoader().load(novel_path)
    print(f"  {text.line_count()} lines, {len(text.text)} chars, encoding={text.encoding}")

    # 初始化模型和 Verifier
    model = None
    needs_model = not dry_run and not detect and (
        agent_tool_mode or llm_decision_fallback
    )
    if needs_model:
        config = ModelConfig()
        if model_name:
            config = ModelConfig(model=model_name)
        model = OpenAICompatibleClient(config)
        # Warmup：先发一条简单请求，确保模型已加载并保持常驻
        print("  Warming up model...", end=" ", flush=True)
        try:
            model.chat(
                messages=[ChatMessage(role="user", content="hello")],
                temperature=0.0,
                max_tokens=10,
            )
            print("OK")
        except Exception as e:
            print(f"failed ({e})")
            print("  Continuing anyway...")

    # 初始化 tracker
    tracker = ProgressTracker(novel_path)
    token_tracker = TokenTracker()

    # Phase 1: 全量检测
    print("\n[2/3] Detecting errors...")
    ErrorQueue.reset_counter()  # 重置错误 ID 计数器，防止跨运行重复
    pipeline = DetectorPipeline()

    if resume and tracker.has_checkpoint():
        print("  Resuming from checkpoint...")
        processed_ids = tracker.get_processed_ids()
        print(f"  {len(processed_ids)} errors already processed")

    # 全量检测（始终全量检测，不按 error_id 过滤，因为修正后偏移量会变）
    queue = pipeline.run(text)
    if not resume or not tracker.has_checkpoint():
        tracker.init_checkpoint(queue)

    stats = queue.type_summary()
    print(f"  Total: {queue.total} errors")
    for t, c in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    if queue.total == 0:
        print("\n[OK] No errors found. Text is already clean!")
        return

    if detect:
        print("\n[OK] Detection complete. Use without --detect to start correction.")
        return

    # Phase 2: Agent 修正
    mode_name = "agent-tool" if agent_tool_mode else "candidate-decision"
    model_label = model.config.model if model else "rule-precheck"
    print(f"\n[3/3] Correcting errors (model={model_label}, mode={mode_name})...")

    round_num = 0
    original_total = queue.total  # 记录原始总数用于进度判断
    prev_remaining = queue.total  # 上一轮剩余错误数，用于判断收敛
    no_progress_rounds = 0  # 连续无进步轮数
    while queue.remaining() > 0:
        round_num += 1
        if round_num > max_pipeline_rounds:
            print(f"\n  [!] Reached max pipeline rounds ({max_pipeline_rounds}), stopping.")
            break

        pending_before = queue.remaining()
        print(f"\n  --- Round {round_num}: {pending_before} errors remaining ---")

        if dry_run:
            # 干跑模式：打印每个错误，不调 LLM，一轮就结束
            for err in queue.all():
                if err.status == "pending":
                    print(f"    [{err.error_id}] L{err.line_number:5d} "
                          f"{err.error_type:18s} {err.original_text[:60]}")
            print(f"\n  Dry-run complete. {queue.remaining()} errors would need fixing.")
            print(f"  Run without --dry-run to start actual correction.")
            break

        # 创建 Agent 并运行
        if agent_tool_mode:
            agent = CorrectionAgent(
                text_doc=text,
                error_queue=queue,
                model_client=model,
                tracker=tracker,
                verifier=CorrectionVerifier(model_client=model),
                max_retries=max_retries,
                max_rounds=max_rounds,
                token_tracker=token_tracker,
            )
        else:
            agent = CandidateDecisionAgent(
                text_doc=text,
                error_queue=queue,
                model_client=model,
                tracker=tracker,
                verifier=CorrectionVerifier(),
                max_decision_retries=max_decision_retries,
                rule_precheck=True,
                llm_fallback=llm_decision_fallback,
                token_tracker=token_tracker,
            )

        def show_progress(processed, total, result):
            print(f"    [{processed}/{total}] {result.error_id}: {result.verdict}"
                  f"{' -> ' + result.reason[:40] if result.reason else ''}")

        results = agent.run_all(progress_callback=show_progress)

        # 统计本轮结果
        passes = sum(1 for r in results if r.verdict == "pass")
        skips = sum(1 for r in results if r.verdict == "uncertain")
        fails = sum(1 for r in results if r.verdict == "fail")
        print(f"    Round {round_num}: {passes} fixed, {skips} skipped, {fails} failed")

        tracker.update_progress(queue)

        # Phase 3: 重新检测（检查是否有新错误引入）
        print("    Re-detecting for new errors...")
        new_queue = pipeline.run(text)
        print(f"    Before: {pending_before} errors, After re-detect: {new_queue.total} errors")
        if new_queue.total == 0:
            print(f"\n[OK] All errors fixed after round {round_num}!")
            break

        # 按 offset 过滤已跳过的错误（error_id 每轮会变，不能用 ID 过滤）
        skipped_keys = set()
        for err in queue.all():
            if err.status == "skipped" or err.status == "failed":
                skipped_keys.add((err.offset, err.error_type))

        fresh_queue = ErrorQueue()
        filtered = 0
        for err in new_queue:
            if (err.offset, err.error_type) in skipped_keys:
                filtered += 1
            else:
                fresh_queue.add(err)

        if filtered > 0:
            print(f"    Filtered out {filtered} previously skipped errors")
        if fresh_queue.remaining() == 0:
            print(f"\n[OK] All errors fixed (no unprocessed remaining)!")
            break

        # 收敛性检查：连续 2 轮错误数不再减少才停止（参考开发方案设计）
        if fresh_queue.remaining() >= prev_remaining:
            no_progress_rounds += 1
            print(f"  [!] No progress this round: {fresh_queue.remaining()} >= {prev_remaining} "
                  f"(no-progress rounds: {no_progress_rounds}/2)")
            if no_progress_rounds >= 2:
                print(f"  Stopping: 2 consecutive rounds without error reduction.")
                break
        else:
            no_progress_rounds = 0  # 有进步，重置计数器

        prev_remaining = fresh_queue.remaining()
        queue = fresh_queue
        print(f"  {fresh_queue.remaining()} errors after re-detect, continuing to round {round_num + 1}...")

    # 生成报告
    print(f"\n{'='*55}")
    print(f"  Generating report...")
    report = tracker.generate_report(error_queue=queue, output_dir="output")
    token_report_path = Path("output") / "token_usage.json"
    token_tracker.save(token_report_path)
    s = report["summary"]
    print(f"  Total: {s['total_errors']}, Fixed: {s['fixed']}, "
          f"Skipped: {s['skipped']}, Failed: {s['failed']}")
    print(f"  Report saved to output/correction_report.json")
    print(
        f"  Token usage: {token_tracker.total_tokens} tokens "
        f"across {len(token_tracker.records)} calls"
    )

    # 保存纠错后的小说全文
    novel_name = Path(novel_path).stem
    corrected_path = Path("output") / f"corrected_{novel_name}.txt"
    text.save(corrected_path)
    print(f"  Corrected novel saved to {corrected_path}")

    print(f"{'='*55}\n")


def batch_process(batch_dir: str, **kwargs):
    """批量处理目录下的所有 .txt 文件。"""
    path = Path(batch_dir)
    novels = sorted(path.glob("*.txt"))
    if not novels:
        print(f"No .txt files found in {batch_dir}")
        return
    print(f"Batch processing {len(novels)} novels from {batch_dir}")
    for novel in novels:
        run_pipeline(str(novel), **kwargs)
        print("\n" + "-" * 55 + "\n")


def _icon(ok: bool) -> str:
    """Status icon safe for GBK terminals."""
    return "[OK]" if ok else "[NG]"


def _load_json_safe(path: Path) -> Optional[dict]:
    """Load JSON file, return None if not found."""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def show_report(novel_path: str):
    """
    查看增强版纠错质量报告。

    读取 checkpoint + output 目录中的报告文件，综合展示：
    - 修正进度摘要
    - 硬性指标达标情况（实时检测修正后文本）
    - Token 消耗统计
    - 符号平衡状态
    """
    from src.detector.pipeline import DetectorPipeline
    from src.io.loader import TextLoader

    novel_name = Path(novel_path).stem
    tracker = ProgressTracker(novel_path)
    summary = tracker.get_progress_summary()
    indicators = tracker.get_indicators() or {}

    print(f"\n{'=' * 60}")
    print(f"  Quality Report -- {novel_name}")
    print(f"{'=' * 60}")

    # --- Section 1: Correction Summary (from checkpoint) ---
    print(f"\n  I. Correction Summary")
    print(f"  {'-' * 56}")
    if summary:
        prog = summary.get("progress", {})
        type_sum = summary.get("type_summary", {})
        print(f"  Total errors: {prog.get('total', '?'):>6}")
        print(f"  Fixed:        {prog.get('fixed', '?'):>6}")
        print(f"  Skipped:      {prog.get('skipped', '?'):>6}")
        print(f"  Failed:       {prog.get('failed', '?'):>6}")
        print(f"  Remaining:    {prog.get('remaining', '?'):>6}")
        if type_sum:
            print(f"  By type: {', '.join(f'{k}={v}' for k, v in type_sum.items())}")
    else:
        print(f"  (no checkpoint data)")

    # --- Section 2: Hard Indicators (realtime from corrected text) ---
    print(f"\n  II. Hard Indicators (realtime)")
    print(f"  {'-' * 56}")
    corrected_path = Path("output") / f"corrected_{novel_name}.txt"
    if corrected_path.exists():
        corrected_doc = TextLoader().load(str(corrected_path))
        text = corrected_doc.text
        LQ = "\u300c"
        RQ = "\u300d"
        left_count = text.count(LQ)
        right_count = text.count(RQ)
        balanced = left_count == right_count

        # Non-standard symbols
        non_std_set = set("[]\u3010\u3011\uff3b\uff3d{}\u300a\u300b\u201c\u201d")
        non_std_count = sum(1 for ch in text if ch in non_std_set)

        # Consecutive symbols check
        consecutive_found = False
        for i in range(1, len(text)):
            if text[i] == text[i - 1] and text[i] in (LQ, RQ):
                consecutive_found = True
                break

        print(f"  Quote balance: {_icon(balanced)}  "
              f"( {left_count} vs {right_count})")
        print(f"  Consecutive symbols: {_icon(not consecutive_found)}")
        print(f"  Non-standard symbols: {_icon(non_std_count == 0)}  "
              f"( {non_std_count} remaining)")
        print(f"  Text: {len(text)} chars, {corrected_doc.line_count()} lines")

        # Compare with checkpoint indicators
        if indicators:
            from_stored = indicators.get("quote_balanced",
                                         indicators.get("balanced", None))
            if from_stored is not None:
                diff = "match" if from_stored == balanced else "MISMATCH"
                print(f"  (checkpoint agrees: {diff})")
    else:
        print(f"  (corrected file not found: {corrected_path})")
        print(f"  Run the pipeline first to generate corrected output.")

    # --- Section 3: Token Usage (from output/token_usage.json) ---
    print(f"\n  III. Token Usage")
    print(f"  {'-' * 56}")
    token_report = _load_json_safe(Path("output") / "token_usage.json")
    if token_report:
        total_tokens = token_report.get("total_tokens", 0)
        n_records = token_report.get("total_records", 0)
        cost = token_report.get("estimated_cost_cny", 0)
        context_limit = token_report.get("context_limit", "?")

        records = token_report.get("records", [])
        if records:
            usage_pcts = [r.get("context_window_pct", 0) for r in records]
            avg_pct = sum(usage_pcts) / len(usage_pcts) if usage_pcts else 0
            max_pct = max(usage_pcts) if usage_pcts else 0
        else:
            avg_pct = max_pct = 0

        print(f"  Total tokens:  {total_tokens:>10,}")
        print(f"  LLM calls:     {n_records:>10}")
        print(f"  Avg ctx util:  {avg_pct:>9.1f}%")
        print(f"  Max ctx util:  {max_pct:>9.1f}%")
        print(f"  Context limit: {context_limit:>10,}")
        print(f"  Est. cost:     CNY {cost:>8.2f}")
    else:
        print(f"  (no token usage data in output/token_usage.json)")

    # --- Section 4: Correction Report Summary (from output/) ---
    print(f"\n  IV. Correction Report")
    print(f"  {'-' * 56}")
    corr_report = _load_json_safe(Path("output") / "correction_report.json")
    if corr_report:
        s = corr_report.get("summary", {})
        print(f"  Final: {s.get('fixed',0)} fixed, {s.get('skipped',0)} skipped, "
              f"{s.get('failed',0)} failed, {s.get('remaining',0)} remaining")
        # Print first few corrections as samples
        corrections = corr_report.get("corrections", [])
        skipped = corr_report.get("skipped", [])
        if corrections:
            print(f"  Sample corrections (last {len(corrections)}):")
            for c in corrections[-5:]:
                orig = c.get("original_text", "")[:40]
                fix = c.get("fix_applied", "")[:40]
                print(f"    {c.get('error_id','')}: {orig} -> {fix}")
        if skipped:
            print(f"  Skipped ({len(skipped)}):")
            for s_item in skipped[:3]:
                print(f"    {s_item.get('error_id','')} type={s_item.get('error_type','')}: "
                      f"{s_item.get('skip_reason','')[:60]}")
    else:
        print(f"  (no correction report in output/)")

    print(f"\n{'=' * 60}\n")


# ── 入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()

    if args.report:
        if args.novel:
            show_report(args.novel)
        else:
            print("Please specify a novel file with --report")
        sys.exit(0)

    if args.batch:
        batch_process(
            args.batch,
            resume=args.resume,
            detect=args.detect,
            dry_run=args.dry_run,
            model_name=args.model,
            max_retries=args.max_retries,
            max_rounds=args.max_rounds,
            max_decision_retries=args.max_decision_retries,
            agent_tool_mode=args.agent_tool_mode,
            llm_decision_fallback=args.llm_decision_fallback,
            max_pipeline_rounds=args.max_pipeline_rounds,
        )
        sys.exit(0)

    if not args.novel:
        print("Error: Please specify a novel file or use --batch")
        print("Usage: python main.py data/ori_story/第1卷.txt")
        sys.exit(1)

    run_pipeline(
        args.novel,
        resume=args.resume,
        detect=args.detect,
        dry_run=args.dry_run,
        model_name=args.model,
        max_retries=args.max_retries,
        max_rounds=args.max_rounds,
        max_decision_retries=args.max_decision_retries,
        agent_tool_mode=args.agent_tool_mode,
        llm_decision_fallback=args.llm_decision_fallback,
        max_pipeline_rounds=args.max_pipeline_rounds,
    )
