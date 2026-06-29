"""
Split high-risk candidate JSONL files into small, auditable batches.

The tool is intentionally read-only with respect to source text. It only reads
candidate records and writes grouped JSONL batches plus a summary report.

Usage:
    python tools/split_high_risk_batches.py output/style_candidates_第2卷_high.jsonl --output-dir output/high_risk_batches
    python tools/split_high_risk_batches.py output/style_candidates_第2卷.jsonl output/style_candidates_第3卷.jsonl --batch-size 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, List


MAX_BATCH_SIZE = 50


def load_jsonl(path: Path) -> List[dict]:
    """Load non-empty JSONL records from a file."""
    records: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_no}: expected object, got {type(item).__name__}")
            item.setdefault("_source_file", str(path))
            item.setdefault("_source_line", line_no)
            records.append(item)
    return records


def normalize_risk(record: dict) -> str:
    """Return a normalized risk label for grouping/filtering."""
    risk = str(record.get("risk_level", "") or "").strip().lower()
    if risk:
        return risk
    if record.get("auto_applicable") is True:
        return "low"
    if record.get("auto_applicable") is False:
        return "high"
    return "unknown"


def infer_volume(record: dict, source_path: Path) -> str:
    """Infer a stable volume label from record fields or source filename."""
    for key in ("volume", "novel", "novel_name"):
        value = str(record.get(key, "") or "").strip()
        if value:
            return value

    path_text = str(source_path)
    match = re.search(r"第\d+卷", path_text)
    if match:
        return match.group(0)
    return "unknown"


def sanitize_filename_part(value: str) -> str:
    """Make a short value safe for use inside a filename."""
    safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value.strip(), flags=re.UNICODE)
    safe = safe.strip("._")
    return safe or "unknown"


def group_key(record: dict, source_path: Path) -> tuple[str, str, str]:
    volume = infer_volume(record, source_path)
    candidate_type = str(record.get("type", "unknown") or "unknown")
    risk = normalize_risk(record)
    return volume, candidate_type, risk


def should_include(record: dict, include_low_risk: bool) -> bool:
    """Default behavior keeps high/unknown candidates and skips low risk."""
    if include_low_risk:
        return True
    return normalize_risk(record) != "low"


def iter_batches(records: List[dict], batch_size: int) -> Iterable[List[dict]]:
    for start in range(0, len(records), batch_size):
        yield records[start:start + batch_size]


def build_batches(input_paths: List[Path], batch_size: int, include_low_risk: bool = False) -> tuple[list[dict], dict]:
    """Build batch descriptors and summary data without writing files."""
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    skipped_low_risk = 0
    total_records = 0

    for path in input_paths:
        for index, record in enumerate(load_jsonl(path), start=1):
            total_records += 1
            if not should_include(record, include_low_risk):
                skipped_low_risk += 1
                continue
            enriched = dict(record)
            enriched["_source_index"] = index
            enriched["_risk"] = normalize_risk(record)
            enriched["_volume"] = infer_volume(record, path)
            groups[group_key(enriched, path)].append(enriched)

    batch_descriptors: list[dict] = []
    batch_number = 1
    for key in sorted(groups.keys(), key=_sort_key):
        volume, candidate_type, risk = key
        records = groups[key]
        records.sort(key=lambda item: (str(item.get("_source_file", "")), int(item.get("_source_line", 0))))
        for group_batch_index, records_batch in enumerate(iter_batches(records, batch_size), start=1):
            batch_id = f"batch-{batch_number:03d}"
            filename = (
                f"{batch_id}_{sanitize_filename_part(volume)}_"
                f"{sanitize_filename_part(candidate_type)}_{sanitize_filename_part(risk)}.jsonl"
            )
            rows = []
            for row_index, item in enumerate(records_batch, start=1):
                row = dict(item)
                row["case_id"] = row.get("case_id") or f"{batch_id}-{row_index:03d}"
                row["batch_id"] = batch_id
                rows.append(row)
            batch_descriptors.append({
                "batch_id": batch_id,
                "filename": filename,
                "volume": volume,
                "type": candidate_type,
                "risk": risk,
                "group_batch_index": group_batch_index,
                "count": len(rows),
                "records": rows,
            })
            batch_number += 1

    summary = {
        "input_files": [str(path) for path in input_paths],
        "batch_size": batch_size,
        "include_low_risk": include_low_risk,
        "total_records": total_records,
        "skipped_low_risk": skipped_low_risk,
        "included_records": sum(batch["count"] for batch in batch_descriptors),
        "batch_count": len(batch_descriptors),
        "groups": [
            {
                "volume": volume,
                "type": candidate_type,
                "risk": risk,
                "count": len(records),
            }
            for (volume, candidate_type, risk), records in sorted(groups.items(), key=lambda item: _sort_key(item[0]))
        ],
    }
    return batch_descriptors, summary


def _sort_key(key: tuple[str, str, str]) -> tuple[int, str, str, str]:
    volume, candidate_type, risk = key
    match = re.search(r"第(\d+)卷", volume)
    volume_num = int(match.group(1)) if match else 9999
    return volume_num, volume, candidate_type, risk


def write_batches(batch_descriptors: list[dict], summary: dict, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    batches_for_summary = []

    for batch in batch_descriptors:
        path = output_dir / batch["filename"]
        with path.open("w", encoding="utf-8") as f:
            for record in batch["records"]:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        batch_summary = {k: batch[k] for k in ("batch_id", "filename", "volume", "type", "risk", "count")}
        batch_summary["path"] = str(path)
        batches_for_summary.append(batch_summary)

    final_summary = dict(summary)
    final_summary["batches"] = batches_for_summary
    summary_path = output_dir / "high_risk_batch_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
    final_summary["summary_path"] = str(summary_path)
    return final_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="candidate JSONL files")
    parser.add_argument("--output-dir", default="output/high_risk_batches", help="directory for batch JSONL files")
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH_SIZE, help="records per batch, max 50")
    parser.add_argument("--include-low-risk", action="store_true", help="also include low-risk/auto-applicable records")
    parser.add_argument("--dry-run", action="store_true", help="print summary without writing files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1 or args.batch_size > MAX_BATCH_SIZE:
        print(f"Error: --batch-size must be between 1 and {MAX_BATCH_SIZE}", file=sys.stderr)
        return 1

    input_paths = [Path(path) for path in args.inputs]
    missing = [str(path) for path in input_paths if not path.exists()]
    if missing:
        print(f"Error: input file(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        batches, summary = build_batches(input_paths, args.batch_size, include_low_risk=args.include_low_risk)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  Split High-risk Candidate Batches")
    print("=" * 60)
    print(f"  Input files:       {len(input_paths)}")
    print(f"  Total records:     {summary['total_records']}")
    print(f"  Included records:  {summary['included_records']}")
    print(f"  Skipped low risk:  {summary['skipped_low_risk']}")
    print(f"  Batch size:        {summary['batch_size']}")
    print(f"  Batch count:       {summary['batch_count']}")

    for group in summary["groups"]:
        print(f"    {group['volume']} / {group['type']} / {group['risk']}: {group['count']}")

    if args.dry_run:
        return 0

    final_summary = write_batches(batches, summary, Path(args.output_dir))
    print(f"\n  Wrote batches to: {args.output_dir}")
    print(f"  Summary: {final_summary['summary_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
