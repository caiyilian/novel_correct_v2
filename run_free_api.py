"""
run_free_api.py — 使用 FreeTheAI 免费 API 运行纠错管线

限制：每分钟最多 10 次请求，串行执行，自动限流。
"""

import io
import sys
import time
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, List, Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.core.progress import ProgressTracker
from src.core.text import TextDoc
from src.detector.pipeline import DetectorPipeline
from src.model.client import (
    ChatMessage,
    ChatResult,
    ModelConnectionStatus,
    OpenAICompatibleClient,
    ToolCall,
    ModelConfig,
)
from src.model.protocol import ToolSpec
from src.io.loader import TextLoader
from src.agent.decision import CandidateDecisionAgent
from src.verifier.agent import CorrectionVerifier


# ─── 限流客户端 ──────────────────────────────────────────


class RateLimitedClient(OpenAICompatibleClient):
    """
    基于 OpenAICompatibleClient 的限流包装器。
    每次调用前自动等待，确保不超过每分钟 10 次请求。
    """

    def __init__(self, config, min_interval: float = 7.0):
        super().__init__(config)
        self._min_interval = min_interval
        self._last_call_time = 0.0

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        now = time.time()
        elapsed = now - self._last_call_time
        if elapsed < self._min_interval:
            wait = self._min_interval - elapsed
            print(f"      [RateLimit] waiting {wait:.1f}s...")
            time.sleep(wait)

        self._last_call_time = time.time()
        return super().chat(messages, tools, temperature, max_tokens)


# ─── 加载免费 API 配置 ───────────────────────────────────


def load_free_api_config():
    config = {
        "base_url": "https://api.freetheai.xyz/v1",
        "api_key": "",
        "model": "bbl/gemini-2.5-flash",
    }
    config_path = Path("free_api_config")
    if config_path.exists():
        for line in config_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key == "FREE_API_BASE_URL":
                    config["base_url"] = value
                elif key == "FREE_API_KEY":
                    config["api_key"] = value
                elif key == "FREE_API_MODEL":
                    config["model"] = value
    return config


# ─── 优化的 Agent（跳过 Verifier LLM 调用） ──────────────


class FastCorrectionAgent:
    """
    优化的纠错 Agent，跳过 Verifier 的 LLM 调用以加速。
    Verifier 只做规则校验，不调用 LLM。
    """

    def __init__(
        self,
        text_doc: TextDoc,
        error_queue: ErrorQueue,
        model_client,
        tracker: ProgressTracker,
        max_retries: int = 2,
        max_rounds: int = 5,
    ):
        self._text = text_doc
        self._queue = error_queue
        self._model = model_client
        self._tracker = tracker
        self._max_retries = max_retries
        self._max_rounds = max_rounds
        self._tools = None

    def run_all(self, progress_callback=None):
        from src.agent.loop import AgentResult
        from src.agent.tools import CorrectionToolset
        from src.agent.prompts import build_system_prompt, build_user_prompt

        results = []
        total = self._queue.remaining()
        processed = 0

        while self._queue.remaining() > 0:
            error = self._queue.next_pending()
            if error is None:
                break

            processed += 1
            result = self._process_one(error)

            if progress_callback:
                progress_callback(processed, total, result)

            results.append(result)

        return results

    def _process_one(self, error):
        from src.agent.loop import AgentResult
        from src.agent.tools import CorrectionToolset
        from src.agent.prompts import build_system_prompt, build_user_prompt

        start_time = time.time()
        self._tools = CorrectionToolset(self._text, self._queue)

        for attempt in range(1, self._max_retries + 1):
            result = AgentResult(
                error_id=error.error_id,
                verdict="fail",
                duration=0.0,
                retry_count=attempt,
            )

            messages = [
                ChatMessage(role="system", content=build_system_prompt(error.error_type)),
                ChatMessage(role="user", content=build_user_prompt(error)),
            ]

            tool_specs = CorrectionToolset.tool_specs()

            round_count = 0

            while round_count < self._max_rounds:
                round_count += 1

                try:
                    response = self._model.chat(
                        messages=messages,
                        tools=tool_specs,
                        temperature=0.0,
                        max_tokens=2000,
                    )
                except Exception as e:
                    result.reason = f"Model call failed: {e}"
                    result.duration = time.time() - start_time
                    return result

                result.llm_response += response.content

                if response.tool_calls:
                    for tc in response.tool_calls:
                        tool_entry = {"name": tc.name, "arguments": tc.arguments}
                        result.tool_calls.append(tool_entry)

                        tool_result = self._tools.execute(tc.name, tc.arguments)

                        messages.append(
                            ChatMessage(
                                role="assistant",
                                content="",
                                tool_calls=[tc.to_openai_tool_call()],
                            )
                        )
                        messages.append(
                            ChatMessage(
                                role="tool",
                                content=str(tool_result),
                                tool_call_id=tc.id,
                            )
                        )

                        if tc.name == "apply_fix":
                            if tool_result.get("status") == "ok":
                                result.verdict = "pass"
                                result.fix_applied = tool_result.get("replacement", "")
                                result.reason = tool_result.get("action", "fix applied")
                            else:
                                result.reason = f"apply_fix failed: {tool_result.get('message', 'unknown')}"
                        elif tc.name == "skip_error":
                            result.verdict = "uncertain"
                            result.reason = tc.arguments.get("reason", "skipped")

                    if result.verdict in ("pass", "uncertain"):
                        break
                else:
                    messages.append(
                        ChatMessage(role="user", content="请使用工具处理此错误，不要只回复文本。")
                    )

            if result.verdict not in ("pass", "uncertain"):
                result.reason = f"No terminating tool call within {self._max_rounds} rounds"
                break

            if result.verdict in ("pass", "uncertain"):
                # 先更新错误队列状态
                if result.verdict == "pass":
                    fix_text = result.fix_applied or error.fix_applied or ""
                    self._queue.mark_fixed(
                        error.error_id,
                        fix=fix_text,
                        verdict="pass",
                        reason=result.reason,
                    )
                elif result.verdict == "uncertain":
                    self._queue.mark_skipped(error.error_id, reason=result.reason)

                # 然后保存 checkpoint
                self._tracker.save_correction(error)
                result.duration = time.time() - start_time
                return result

        if result.verdict not in ("pass", "uncertain"):
            if not result.reason:
                result.reason = f"All {self._max_retries} attempts failed"
            error.retry_count = result.retry_count
            self._queue.mark_failed(error.error_id, reason=result.reason)
            self._tracker.save_correction(error)

        result.duration = time.time() - start_time
        return result


# ─── 完整管线 ────────────────────────────────────────────


def run_pipeline(novel_path: str, dry_run: bool = False, resume: bool = False,
                 max_errors: Optional[int] = None, max_rounds: int = 5,
                 max_decision_retries: int = 2,
                 agent_tool_mode: bool = False):
    print(f"\n{'='*55}")
    print(f"  FreeTheAI Correction - {Path(novel_path).name}")
    print(f"{'='*55}\n")

    # Phase 0: 加载文本
    print("[1/4] Loading text...")
    text = TextLoader().load(novel_path)
    print(f"  {text.line_count()} lines, {len(text.text)} chars")

    # 初始化免费 API 客户端
    api_config = load_free_api_config()
    print(f"  API: {api_config['base_url']}")
    print(f"  Model: {api_config['model']}")

    config = ModelConfig(
        base_url=api_config["base_url"],
        api_key=api_config["api_key"],
        model=api_config["model"],
        timeout=60.0,
        retries=3,
        retry_delay=10.0,
    )
    client = RateLimitedClient(config, min_interval=7.0)

    # 测试连接
    print("  Testing connection...")
    status = client.check_connection()
    if not status.ok:
        print(f"  Connection failed: {status.message}")
        return
    print(f"  Connection OK: {status.message}")

    # 初始化 tracker（使用独立 checkpoint 目录，避免与 Ollama 版冲突）
    tracker = ProgressTracker(novel_path, checkpoint_dir=".checkpoint_free")

    # Phase 1: 全量检测
    print("\n[2/4] Detecting errors...")
    pipeline = DetectorPipeline()

    if resume and tracker.has_checkpoint():
        processed_ids = tracker.get_processed_ids()
        print(f"  Resuming, {len(processed_ids)} already processed")
        queue = pipeline.run_with_checkpoint(text, tracker)
    else:
        queue = pipeline.run(text)
        tracker.init_checkpoint(queue)

    stats = queue.type_summary()
    print(f"  Total: {queue.total} errors")
    for t, c in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    if queue.total == 0:
        print("\n[OK] No errors found!")
        return

    if dry_run:
        print("\n[Dry-run] Errors found:")
        for err in queue.all():
            if err.status == "pending":
                print(f"  [{err.error_id}] L{err.line_number:5d} {err.error_type:18s} {err.original_text[:60]}")
        print(f"\n  {queue.remaining()} errors would need fixing.")
        return

    # Phase 2: Agent 修正（使用优化的 Agent，跳过 Verifier LLM）
    mode_name = "agent-tool" if agent_tool_mode else "candidate-decision"
    print(f"\n[3/4] Correcting errors (mode={mode_name})...")

    round_num = 0
    max_pipeline_rounds = 5

    while queue.remaining() > 0 and round_num < max_pipeline_rounds:
        round_num += 1
        pending_before = queue.remaining()

        to_process = min(pending_before, max_errors) if max_errors else pending_before

        print(f"\n  --- Round {round_num}: {pending_before} errors remaining (processing up to {to_process}) ---")

        if agent_tool_mode:
            agent = FastCorrectionAgent(
                text_doc=text,
                error_queue=queue,
                model_client=client,
                tracker=tracker,
                max_rounds=max_rounds,
            )
        else:
            agent = CandidateDecisionAgent(
                text_doc=text,
                error_queue=queue,
                model_client=client,
                tracker=tracker,
                verifier=CorrectionVerifier(),
                max_decision_retries=max_decision_retries,
            )

        count = 0
        start_time = time.time()

        def show_progress(processed, total, result):
            nonlocal count
            count += 1
            elapsed = time.time() - start_time
            speed = count / elapsed * 60 if elapsed > 0 else 0
            eta = (to_process - count) / speed if speed > 0 else 0
            bar_len = 20
            filled = int(bar_len * count / to_process) if to_process > 0 else bar_len
            bar = "#" * filled + "-" * (bar_len - filled)
            pct = count / to_process * 100 if to_process > 0 else 100
            verdict_short = {"pass": "FIX", "uncertain": "SKIP", "fail": "FAIL"}.get(result.verdict, "?")
            print(f"\r    [{bar}] {pct:5.1f}% ({count}/{to_process}) "
                  f"{result.error_id}: {verdict_short} "
                  f"eta {eta:.0f}s  ", end="", flush=True)
            if count % 10 == 0 or count == to_process:
                print()
            if max_errors and count >= max_errors:
                raise StopIteration("Reached max_errors limit")

        try:
            results = agent.run_all(progress_callback=show_progress)
        except StopIteration:
            print(f"    Reached max_errors limit ({max_errors})")
            break

        passes = sum(1 for r in results if r.verdict == "pass")
        skips = sum(1 for r in results if r.verdict == "uncertain")
        fails = sum(1 for r in results if r.verdict == "fail")
        elapsed = time.time() - start_time
        print(f"    Round {round_num} done: {passes} fixed, {skips} skipped, {fails} failed ({elapsed:.0f}s)")

        tracker.update_progress(queue)

        if max_errors and count >= max_errors:
            break

        # Phase 3: 重新检测
        print("    Re-detecting...")
        new_queue = pipeline.run(text)
        if new_queue.total == 0:
            print(f"\n[OK] All errors fixed after round {round_num}!")
            break

        fresh_queue = ErrorQueue()
        for err in new_queue:
            if err.error_id not in tracker.get_processed_ids():
                fresh_queue.add(err)

        if fresh_queue.remaining() == 0:
            print(f"\n[OK] All errors fixed!")
            break

        if fresh_queue.remaining() >= pending_before:
            print(f"\n[!] No progress, stopping to avoid infinite loop")
            break

        queue = fresh_queue
        print(f"  {fresh_queue.remaining()} new errors found")

    # 生成报告
    print(f"\n{'='*55}")
    print(f"[4/4] Generating report...")
    report = tracker.generate_report(error_queue=queue, output_dir="output")
    s = report["summary"]
    print(f"  Total: {s['total_errors']}, Fixed: {s['fixed']}, Skipped: {s['skipped']}, Failed: {s['failed']}")
    print(f"  Report: output/correction_report.json")
    print(f"{'='*55}\n")


# ─── 入口 ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="FreeTheAI API Correction Pipeline")
    parser.add_argument("novel", help="Novel file path")
    parser.add_argument("--detect", action="store_true", help="Detect only, no correction")
    parser.add_argument("--dry-run", action="store_true", help="Print errors without calling LLM")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--max-errors", type=int, default=None, help="Max errors to process in this run")
    parser.add_argument("--max-rounds", type=int, default=5, help="Max Agent rounds per attempt")
    parser.add_argument("--max-decision-retries", type=int, default=2, help="Max candidate decision calls per error")
    parser.add_argument("--agent-tool-mode", action="store_true", help="Use legacy tool-calling Agent mode")
    args = parser.parse_args()

    if not Path(args.novel).exists():
        print(f"File not found: {args.novel}")
        sys.exit(1)

    run_pipeline(
        args.novel,
        dry_run=args.dry_run,
        resume=args.resume,
        max_errors=args.max_errors,
        max_rounds=args.max_rounds,
        max_decision_retries=args.max_decision_retries,
        agent_tool_mode=args.agent_tool_mode,
    )


if __name__ == "__main__":
    main()
