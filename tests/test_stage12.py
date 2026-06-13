"""Stage 12 验证脚本：Agent Loop 主循环"""
import sys, os, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.text import TextDoc
from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.core.progress import ProgressTracker
from src.model.client import ChatResult, ToolCall
from src.agent.loop import CorrectionAgent

results = []
errors = []

# ── Mock Model Client ───────────────────────────────
class MockModelClient:
    def __init__(self, mode="fix"):
        self.mode = mode
        self.call_count = 0

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        self.call_count += 1
        eid = "e-0001"
        for msg in messages:
            if hasattr(msg, 'content') and '错误 ID:' in msg.content:
                for part in msg.content.split():
                    if part.startswith("e-"):
                        eid = part
                        break

        if self.mode == "fix":
            return ChatResult(content="", tool_calls=[
                ToolCall(id="c1", name="apply_fix",
                         arguments={"error_id": eid, "start_offset": 0, "end_offset": 6,
                                    "replacement": "「修正」"})
            ], raw={})
        elif self.mode == "skip":
            return ChatResult(content="", tool_calls=[
                ToolCall(id="c1", name="skip_error",
                         arguments={"error_id": eid, "reason": "Not an error"})
            ], raw={})
        elif self.mode == "fail":
            return ChatResult(content="I don't know", raw={})
        elif self.mode == "text_then_fix":
            if self.call_count == 1:
                return ChatResult(content="Let me analyze...", raw={})
            return ChatResult(content="", tool_calls=[
                ToolCall(id="c2", name="apply_fix",
                         arguments={"error_id": eid, "start_offset": 0, "end_offset": 6,
                                    "replacement": "「修正」"})
            ], raw={})

# ── Test cases ──────────────────────────────────────
TEST_CASES = [
    ("fix mode", "fix", 3),
    ("skip mode", "skip", 1),
    ("fail mode", "fail", 1),
    ("text then fix", "text_then_fix", 3),
]

TEXT = TextDoc("【错误内容】结束")

for test_name, mode, max_retries in TEST_CASES:
    try:
        q = ErrorQueue()
        q.add(ErrorRecord(error_type="wrong_symbol", line_number=1, offset=0, original_text=f"【{mode}】"))
        tmpdir = tempfile.mkdtemp()
        t = ProgressTracker(f"{mode}.txt", checkpoint_dir=tmpdir)
        t.init_checkpoint(q)
        mock = MockModelClient(mode=mode)
        agent = CorrectionAgent(TEXT, q, mock, t, max_retries=max_retries)
        r = agent.run_all()
        assert len(r) == 1
        verdict = r[0].verdict
        results.append((test_name, "ok",
                       f"verdict={verdict}, calls={mock.call_count}"))
        import shutil
        shutil.rmtree(tmpdir)
    except Exception as e:
        errors.append((test_name, str(e)))

# Test: progress callback
try:
    q = ErrorQueue()
    for i in range(3):
        q.add(ErrorRecord(error_type="wrong_symbol", line_number=i+1, offset=i*100, original_text=f"【E{i}】"))
    tmpdir = tempfile.mkdtemp()
    t = ProgressTracker("cb.txt", checkpoint_dir=tmpdir)
    t.init_checkpoint(q)
    mock = MockModelClient(mode="fix")
    agent = CorrectionAgent(TEXT, q, mock, t)
    cb_log = []
    agent.run_all(progress_callback=lambda p, total, r: cb_log.append(r.verdict))
    assert len(cb_log) == 3
    results.append(("progress callback", "ok", f"{len(cb_log)} callbacks: {cb_log}"))
    import shutil
    shutil.rmtree(tmpdir)
except Exception as e:
    errors.append(("progress callback", str(e)))

# Test: empty queue
try:
    q = ErrorQueue()
    tmpdir = tempfile.mkdtemp()
    t = ProgressTracker("empty.txt", checkpoint_dir=tmpdir)
    t.init_checkpoint(q)
    mock = MockModelClient(mode="fix")
    agent = CorrectionAgent(TEXT, q, mock, t)
    r = agent.run_all()
    assert len(r) == 0
    results.append(("empty queue", "ok", "no errors"))
    import shutil
    shutil.rmtree(tmpdir)
except Exception as e:
    errors.append(("empty queue", str(e)))

# Print
print("=" * 55)
print("  Stage 12 Verification Report — Agent Loop")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
