"""Stage 21a verification: verifier checks rule candidates."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.candidates import CorrectionCandidate  # noqa: E402
from src.agent.decision import CandidateDecisionAgent  # noqa: E402
from src.core.error_queue import ErrorQueue  # noqa: E402
from src.core.error_record import ErrorRecord  # noqa: E402
from src.core.progress import ProgressTracker  # noqa: E402
from src.core.text import TextDoc  # noqa: E402
from src.verifier.agent import CorrectionVerifier  # noqa: E402


results = []
errors = []


def check(name, condition, detail=""):
    if condition:
        results.append(f"  [OK] {name}{': ' + detail if detail else ''}")
    else:
        errors.append(f"  [FAIL] {name}{': ' + detail if detail else ''}")


def make_agent(text: TextDoc, queue: ErrorQueue, checkpoint_dir: str):
    return CandidateDecisionAgent(
        text_doc=text,
        error_queue=queue,
        model_client=None,
        tracker=ProgressTracker("stage21a.txt", checkpoint_dir=checkpoint_dir),
        verifier=CorrectionVerifier(),
        rule_precheck=True,
        llm_fallback=False,
    )


def make_error(offset: int = 0) -> ErrorRecord:
    return ErrorRecord(
        error_type="wrong_symbol",
        line_number=1,
        offset=offset,
        context_before="",
        context_after="",
        original_text="[",
    )


print("=" * 55)
print("  Stage 21a Verification Report — Rule Candidate Verifier")
print("=" * 55)

try:
    with tempfile.TemporaryDirectory() as tmp:
        text = TextDoc("[\u4f60\u597d]")
        queue = ErrorQueue()
        error = make_error(0)
        queue.add(error)
        agent = make_agent(text, queue, tmp)
        candidate = CorrectionCandidate(
            candidate_id="c1",
            error_id=error.error_id,
            error_type=error.error_type,
            start_offset=0,
            end_offset=len(text.text),
            replacement="\u300c\u4f60\u597d\u300d",
            description="standardize brackets",
        )
        result = agent._apply_candidate(error, candidate, "rule candidate")
        check("valid candidate passes", result.verdict == "pass", result.reason)
        check("valid candidate applied", text.text == "\u300c\u4f60\u597d\u300d", text.text)
        check("queue marked fixed", queue.get(error.error_id).status == "fixed")
except Exception as exc:
    errors.append(f"  [FAIL] valid candidate verifier: {exc}")

try:
    with tempfile.TemporaryDirectory() as tmp:
        text = TextDoc("\u300c\u4f60\u597d\u300d")
        queue = ErrorQueue()
        error = make_error(1)
        queue.add(error)
        agent = make_agent(text, queue, tmp)
        candidate = CorrectionCandidate(
            candidate_id="c-bad",
            error_id=error.error_id,
            error_type=error.error_type,
            start_offset=1,
            end_offset=3,
            replacement="\u300c\u574f",
            description="introduce consecutive bracket",
        )
        before = text.text
        result = agent._apply_candidate(error, candidate, "bad rule candidate")
        check("bad candidate rejected", result.verdict == "uncertain", result.reason)
        check("bad candidate not applied", text.text == before, text.text)
        check("queue marked skipped", queue.get(error.error_id).status == "skipped")
        check("verifier reason kept", "Verifier rejected" in result.reason, result.reason)
except Exception as exc:
    errors.append(f"  [FAIL] rejected candidate verifier: {exc}")

try:
    verifier = CorrectionVerifier()
    original = "[x] \u300d\u300d"
    fixed_one = "\u300cx\u300d \u300d\u300d"
    error = make_error(0)
    result = verifier.verify(error, original, fixed_one)
    check("existing consecutive tolerated", result.verdict == "pass", result.reason)
except Exception as exc:
    errors.append(f"  [FAIL] consecutive delta verifier: {exc}")

print()
for r in results:
    print(r)
for e in errors:
    print(e)
print(f"\n  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
sys.exit(1 if errors else 0)
