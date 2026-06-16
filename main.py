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
import sys
import time
from pathlib import Path
from typing import Optional

from src.core.text import TextDoc
from src.core.error_queue import ErrorQueue
from src.core.progress import ProgressTracker
from src.detector.pipeline import DetectorPipeline
from src.model.client import ChatMessage, ModelConfig, OpenAICompatibleClient
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
    return parser.parse_args()


# ── 管线核心 ──────────────────────────────────────────

def run_pipeline(
    novel_path: str,
    resume: bool = False,
    dry_run: bool = False,
    model_name: str = "",
    max_retries: int = 3,
    max_rounds: int = 5,
    max_decision_retries: int = 2,
    agent_tool_mode: bool = False,
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
    if not dry_run:
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

    # Phase 1: 全量检测
    print("\n[2/3] Detecting errors...")
    pipeline = DetectorPipeline()

    if resume and tracker.has_checkpoint():
        print("  Resuming from checkpoint...")
        processed_ids = tracker.get_processed_ids()
        print(f"  {len(processed_ids)} errors already processed")

    # 全量检测
    if resume and tracker.has_checkpoint():
        queue = pipeline.run_with_checkpoint(text, tracker)
    else:
        queue = pipeline.run(text)
        tracker.init_checkpoint(queue)

    stats = queue.type_summary()
    print(f"  Total: {queue.total} errors")
    for t, c in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    if queue.total == 0:
        print("\n[OK] No errors found. Text is already clean!")
        return

    if args.detect:
        print("\n[OK] Detection complete. Use without --detect to start correction.")
        return

    # Phase 2: Agent 修正
    mode_name = "agent-tool" if agent_tool_mode else "candidate-decision"
    print(f"\n[3/3] Correcting errors (model={model.config.model if model else 'dry-run'}, mode={mode_name})...")

    round_num = 0
    while queue.remaining() > 0:
        round_num += 1

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
            )
        else:
            agent = CandidateDecisionAgent(
                text_doc=text,
                error_queue=queue,
                model_client=model,
                tracker=tracker,
                verifier=CorrectionVerifier(),
                max_decision_retries=max_decision_retries,
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
        if new_queue.total == 0:
            print(f"\n[OK] All errors fixed after round {round_num}!")
            break

        # 过滤已处理的
        fresh_queue = ErrorQueue()
        for err in new_queue:
            if err.error_id not in tracker.get_processed_ids():
                fresh_queue.add(err)

        if fresh_queue.remaining() == 0:
            print(f"\n[OK] All errors fixed (no unprocessed remaining)!")
            break

        if fresh_queue.remaining() >= pending_before:
            print(f"\n  [!] No progress this round ({fresh_queue.remaining()} still pending)")
            print(f"  Stopping to avoid infinite loop.")
            break

        # 有新错误，继续下一轮
        queue = fresh_queue
        print(f"  {fresh_queue.remaining()} new errors found, continuing...")

    # 生成报告
    print(f"\n{'='*55}")
    print(f"  Generating report...")
    report = tracker.generate_report(error_queue=queue, output_dir="output")
    s = report["summary"]
    print(f"  Total: {s['total_errors']}, Fixed: {s['fixed']}, "
          f"Skipped: {s['skipped']}, Failed: {s['failed']}")
    print(f"  Report saved to output/correction_report.json")
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


def show_report(novel_path: str):
    """只查看上次纠错报告。"""
    tracker = ProgressTracker(novel_path)
    summary = tracker.get_progress_summary()
    if summary is None:
        print(f"No checkpoint found for {novel_path}")
        return
    print(f"\nReport for {Path(novel_path).name}:")
    print(f"  Progress: {summary.get('progress', {})}")
    print(f"  Type distribution: {summary.get('type_summary', {})}")
    indicators = tracker.get_indicators()
    if indicators:
        print(f"  Hard indicators: {indicators}")


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
            dry_run=args.dry_run,
            model_name=args.model,
            max_retries=args.max_retries,
            max_rounds=args.max_rounds,
            max_decision_retries=args.max_decision_retries,
            agent_tool_mode=args.agent_tool_mode,
        )
        sys.exit(0)

    if not args.novel:
        print("Error: Please specify a novel file or use --batch")
        print("Usage: python main.py data/ori_story/第1卷.txt")
        sys.exit(1)

    run_pipeline(
        args.novel,
        resume=args.resume,
        dry_run=args.dry_run,
        model_name=args.model,
        max_retries=args.max_retries,
        max_rounds=args.max_rounds,
        max_decision_retries=args.max_decision_retries,
        agent_tool_mode=args.agent_tool_mode,
    )
