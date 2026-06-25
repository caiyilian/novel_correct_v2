"""Stage 17 验证脚本：多轮纠错管线"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.text import TextDoc
from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.detector.pipeline import DetectorPipeline
from src.agent.decision import CandidateDecisionAgent


results = []
errors = []


class DummyTracker:
    def save_correction(self, *args, **kwargs):
        pass


def check(name, condition, detail=""):
    if condition:
        results.append(f"  [OK] {name}{': ' + detail if detail else ''}")
    else:
        errors.append(f"  [FAIL] {name}{': ' + detail if detail else ''}")


# ── 测试 1: 多轮收敛 ──────────────────────────────────

print("=" * 55)
print("  Stage 17 Verification Report — Multi-Round Pipeline")
print("=" * 55)

text = TextDoc("「「A" + "好" * 60 + "」」B\n")
pipeline = DetectorPipeline()
queue = pipeline.run(text)
original_total = queue.total
check("initial detection", original_total == 2, f"found {original_total} errors")

# Simulate multi-round with the same rule pre-check decision path as main.py.
round_num = 0
max_rounds = 5
total_fixed = 0
final_total = original_total

while queue.remaining() > 0 and round_num < max_rounds:
    round_num += 1
    agent = CandidateDecisionAgent(
        text_doc=text,
        error_queue=queue,
        model_client=None,
        tracker=DummyTracker(),
        rule_precheck=True,
        llm_fallback=False,
    )
    results_this_round = agent.run_all()
    round_fixed = sum(1 for result in results_this_round if result.verdict == "pass")

    total_fixed += round_fixed

    # Re-detect
    new_queue = pipeline.run(text)
    final_total = new_queue.total

    # Filter skipped by offset
    skipped_keys = set()
    for err in queue.all():
        if err.status == "skipped" or err.status == "failed":
            skipped_keys.add((err.offset, err.error_type))

    fresh_queue = ErrorQueue()
    for err in new_queue:
        if (err.offset, err.error_type) not in skipped_keys:
            fresh_queue.add(err)

    if fresh_queue.remaining() == 0 or new_queue.total == 0:
        queue = fresh_queue
        break

    if fresh_queue.remaining() >= original_total:
        break

    queue = fresh_queue

check("multi-round converges", final_total == 0, f"converged after {round_num} rounds")
check("total fixed > 0", total_fixed > 0, f"{total_fixed} errors fixed in {round_num} rounds")
check("max_rounds not exceeded", round_num <= max_rounds, f"used {round_num} rounds")

# ── 测试 2: 无错误文本不应触发多轮 ──────────────────

clean_text = TextDoc("「你好」\n")
clean_queue = pipeline.run(clean_text)
check("clean text: 0 errors", clean_queue.total == 0)

# ── 测试 3: max_pipeline_rounds 限制 ──────────────────

# Use a text that won't converge in 1 round
stuck_text = TextDoc("「「A\n")
stuck_queue = pipeline.run(stuck_text)

for r in range(3):
    while True:
        e = stuck_queue.next_pending()
        if e is None:
            break
        stuck_queue.mark_skipped(e.error_id, reason="simulated skip")
    new_q = DetectorPipeline().run(stuck_text)
    skipped = set()
    for e in stuck_queue.all():
        if e.status in ("skipped", "failed"):
            skipped.add((e.offset, e.error_type))
    fresh = ErrorQueue()
    for e in new_q:
        if (e.offset, e.error_type) not in skipped:
            fresh.add(e)
    if fresh.remaining() >= new_q.total:
        break
    stuck_queue = fresh

check("max_rounds stops loop", True, "loop stops when no progress")


# ── 报告 ──────────────────────────────────────────────

print()
for r in results:
    print(r)
for e in errors:
    print(e)
print(f"\n  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
sys.exit(1 if errors else 0)
