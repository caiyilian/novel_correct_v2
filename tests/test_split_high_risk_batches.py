"""Tests for tools/split_high_risk_batches.py."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.split_high_risk_batches import build_batches


results = []
errors = []


def check(name, condition, detail=""):
    if condition:
        results.append(f"  [OK] {name}{': ' + detail if detail else ''}")
    else:
        errors.append(f"  [FAIL] {name}{': ' + detail if detail else ''}")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


try:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        candidates = tmp_path / "style_candidates_第2卷_high.jsonl"
        rows = [
            {"type": "period", "offset": i, "original": ".", "candidate": "。", "risk_level": "high", "auto_applicable": False}
            for i in range(5)
        ]
        rows.extend([
            {"type": "question_mark", "offset": 100 + i, "original": "?", "candidate": "？", "risk_level": "low", "auto_applicable": True}
            for i in range(2)
        ])
        write_jsonl(candidates, rows)

        batches, summary = build_batches([candidates], batch_size=2)
        check("summary counts total records", summary["total_records"] == 7)
        check("summary skips low risk by default", summary["skipped_low_risk"] == 2)
        check("summary includes high risk only", summary["included_records"] == 5)
        check("batch count splits by size", summary["batch_count"] == 3)
        check("volume inferred from filename", batches[0]["volume"] == "第2卷")
        check("case ids assigned", all("case_id" in row for batch in batches for row in batch["records"]))
        check("batch sizes do not exceed limit", all(batch["count"] <= 2 for batch in batches))
except Exception as exc:
    errors.append(f"  [FAIL] build_batches: {exc}")


try:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        candidates = tmp_path / "vol3_candidates.jsonl"
        write_jsonl(candidates, [
            {"volume": "第3卷", "type": "curly_quote", "offset": 1, "risk_level": "high", "auto_applicable": False},
            {"volume": "第3卷", "type": "curly_quote", "offset": 2, "risk_level": "high", "auto_applicable": False},
            {"volume": "第3卷", "type": "bracket", "offset": 3, "auto_applicable": False},
        ])
        out_dir = tmp_path / "batches"

        completed = subprocess.run(
            [
                sys.executable,
                "tools/split_high_risk_batches.py",
                str(candidates),
                "--output-dir",
                str(out_dir),
                "--batch-size",
                "2",
            ],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
        )
        check("CLI returns zero", completed.returncode == 0, completed.stderr)
        summary_path = out_dir / "high_risk_batch_summary.json"
        check("CLI writes summary", summary_path.exists())
        with summary_path.open("r", encoding="utf-8") as f:
            summary = json.load(f)
        check("CLI summary includes 2 batches", summary["batch_count"] == 2)
        batch_paths = [Path(batch["path"]) for batch in summary["batches"]]
        check("CLI writes batch files", all(path.exists() for path in batch_paths))
        first_lines = batch_paths[0].read_text(encoding="utf-8").splitlines()
        first_record = json.loads(first_lines[0])
        check("CLI batch enriches batch_id", first_record.get("batch_id") == "batch-001")
except Exception as exc:
    errors.append(f"  [FAIL] CLI write: {exc}")


try:
    completed = subprocess.run(
        [sys.executable, "tools/split_high_risk_batches.py", "missing.jsonl", "--batch-size", "51"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
    )
    check("CLI rejects oversize batch", completed.returncode != 0)
    check("CLI explains batch-size limit", "batch-size" in completed.stderr)
except Exception as exc:
    errors.append(f"  [FAIL] CLI invalid batch size: {exc}")


print()
for r in results:
    print(r)
for e in errors:
    print(e)
print(f"\n  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
sys.exit(1 if errors else 0)
