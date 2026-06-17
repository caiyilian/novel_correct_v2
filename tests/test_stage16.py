"""Stage 16 验证脚本：第 1 卷候选生成覆盖率"""
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.candidates import CandidateGenerator
from src.agent.decision import CandidateDecisionAgent
from src.core.progress import ProgressTracker
from src.detector.pipeline import DetectorPipeline
from src.io.loader import TextLoader
from src.model.client import ChatResult


results = []
errors = []


class ApplyFirstClient:
    def __init__(self):
        self.call_count = 0

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        self.call_count += 1
        return ChatResult(
            content=json.dumps(
                {"decision": "apply", "choice_id": "c1", "reason": "规则候选可应用"},
                ensure_ascii=False,
            ),
            raw={},
        )


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
        else:
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
    tmpdir = tempfile.mkdtemp()
    try:
        tracker = ProgressTracker("stage16_round.txt", checkpoint_dir=tmpdir)
        tracker.init_checkpoint(round_queue)
        client = ApplyFirstClient()
        round_results = CandidateDecisionAgent(
            round_text,
            round_queue,
            client,
            tracker,
        ).run_all()
        fixed = sum(1 for item in round_results if item.verdict == "pass")
        no_candidates = [
            item.error_id
            for item in round_results
            if item.reason == "No rule candidates generated"
        ]
        assert fixed >= 30
        assert not no_candidates
        assert round_queue.remaining() == 0
        results.append(("one-round mock fixed", "ok", f"{fixed}/{len(round_results)}"))
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
