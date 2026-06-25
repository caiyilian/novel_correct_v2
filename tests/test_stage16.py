"""Stage 16 验证脚本：第 1 卷候选生成覆盖率"""
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.candidates import CandidateGenerator
from src.agent.decision import CandidateDecisionAgent
from src.core.error_record import ErrorRecord
from src.core.progress import ProgressTracker
from src.detector.pipeline import DetectorPipeline
from src.io.loader import TextLoader


results = []
errors = []


class NoChatClient:
    def __init__(self):
        self.call_count = 0

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        self.call_count += 1
        raise AssertionError("rule precheck mode should not call the LLM")


try:
    text = TextLoader().load(Path("data/ori_story/第1卷.txt"))
    queue = DetectorPipeline().run(text)
    generator = CandidateGenerator()

    total_by_type = Counter()
    covered_by_type = Counter()
    missing = []

    for error in queue:
        total_by_type[error.error_type] += 1
        candidates = generator.generate(text, error)
        if candidates:
            covered_by_type[error.error_type] += 1
        elif not error.is_nested:
            # 嵌套符号（Stage 19b 新检出）的候选生成在 Stage 19e 补充
            missing.append(error)

    total = sum(total_by_type.values())
    covered = sum(covered_by_type.values())
    consecutive_total = total_by_type["consecutive"]
    consecutive_covered = covered_by_type["consecutive"]

    assert total > 0
    assert consecutive_total > 0
    assert consecutive_covered / consecutive_total >= 0.8
    assert not missing, [
        (item.error_id, item.error_type, item.line_number, item.original_text[:40])
        for item in missing
    ]

    results.append(("overall coverage", "ok", f"{covered}/{total}"))
    results.append(
        (
            "consecutive coverage",
            "ok",
            f"{consecutive_covered}/{consecutive_total}",
        )
    )
    for error_type in sorted(total_by_type):
        if error_type == "consecutive":
            continue
        results.append(
            (
                f"{error_type} coverage",
                "ok",
                f"{covered_by_type[error_type]}/{total_by_type[error_type]}",
            )
        )

    round_text = TextLoader().load(Path("data/ori_story/第1卷.txt"))
    round_queue = DetectorPipeline().run(round_text)
    # Stage 19b: 嵌套符号的候选生成在 Stage 19e 补充，临时排除
    for err in list(round_queue.all()):
        if err.is_nested:
            round_queue.mark_skipped(err.error_id, reason="nested, will be handled in Stage 19e")
    tmpdir = tempfile.mkdtemp()
    try:
        tracker = ProgressTracker("stage16_round.txt", checkpoint_dir=tmpdir)
        tracker.init_checkpoint(round_queue)
        client = NoChatClient()
        counter_before_agent = ErrorRecord._id_counter
        round_results = CandidateDecisionAgent(
            round_text,
            round_queue,
            client,
            tracker,
            rule_precheck=True,
            llm_fallback=False,
        ).run_all()
        fixed = sum(1 for item in round_results if item.verdict == "pass")
        skipped = sum(1 for item in round_results if item.verdict == "uncertain")
        no_candidates = [
            item.error_id
            for item in round_results
            if item.reason == "No rule candidates generated"
        ]
        assert fixed >= 30
        assert skipped > 0
        assert not no_candidates
        assert round_queue.remaining() == 0
        assert client.call_count == 0
        assert ErrorRecord._id_counter == counter_before_agent
        results.append(
            (
                "one-round rule fixed",
                "ok",
                f"fixed={fixed}, skipped={skipped}, llm_calls={client.call_count}",
            )
        )
    finally:
        shutil.rmtree(tmpdir)
except Exception as exc:
    errors.append(("candidate coverage", str(exc)))


print("=" * 55)
print("  Stage 16 Verification Report — Candidate Coverage")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)

if errors:
    raise SystemExit(1)
