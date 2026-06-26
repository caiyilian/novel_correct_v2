"""Cross-volume final audit with machine-readable pass/fail output."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from src.io.loader import TextLoader


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
JSON_REPORT = OUTPUT_DIR / "final_audit.json"
MD_REPORT = OUTPUT_DIR / "final_audit.md"
VOLUMES = list(range(1, 11))
ENFORCED_VOLUMES = set(range(2, 11))


def load_text(path: Path) -> str:
    return TextLoader().load(str(path)).text


def count_paragraph_imbalances(text: str) -> int:
    return sum(1 for para in text.splitlines() if para.count("「") != para.count("」"))


def find_evidence(vol: int, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        for path in OUTPUT_DIR.glob(pattern.format(vol=vol)):
            matches.append(str(path.relative_to(ROOT)))
    return sorted(set(matches))


def audit_volume(vol: int) -> dict[str, object]:
    corrected_path = OUTPUT_DIR / f"corrected_第{vol}卷.txt"
    answer_path = ROOT / "data" / "answer" / f"answer_第{vol}卷.txt"
    corrected = load_text(corrected_path)
    answer = load_text(answer_path)

    corrected_left = corrected.count("「")
    corrected_right = corrected.count("」")
    answer_left = answer.count("「")
    answer_right = answer.count("」")
    bracket_left = corrected.count("[")
    bracket_right = corrected.count("]")
    nonstandard = {
        "《": corrected.count("《"),
        "》": corrected.count("》"),
        "“": corrected.count("“"),
        "”": corrected.count("”"),
        "【": corrected.count("【"),
        "】": corrected.count("】"),
        "［": corrected.count("［"),
        "］": corrected.count("］"),
    }
    nonstandard = {k: v for k, v in nonstandard.items() if v}
    paragraph_imbalances = count_paragraph_imbalances(corrected)

    count_matches = corrected_left == answer_left and corrected_right == answer_right
    quote_balanced = corrected_left == corrected_right
    answer_balanced = answer_left == answer_right
    brackets_clear = bracket_left == 0 and bracket_right == 0
    no_empty = "「」" not in corrected
    paragraph_balanced = paragraph_imbalances == 0

    manual_evidence = find_evidence(
        vol,
        [
            f"vol{vol}_manual*.json",
            f"vol{vol}_manual*.md",
            f"vol{vol}_*manual*.json",
            f"vol{vol}_*manual*.md",
            f"vol{vol}_source_missing*.json",
            f"vol{vol}_source_missing*.md",
            f"vol{vol}_*source_missing*.json",
            f"vol{vol}_*source_missing*.md",
        ],
    )
    whitelist_evidence = find_evidence(
        vol,
        [
            f"vol{vol}_*whitelist*.json",
            f"vol{vol}_*whitelist*.md",
            f"whitelist_第{vol}卷*.json",
            f"whitelist_第{vol}卷*.md",
        ],
    )

    enforced = vol in ENFORCED_VOLUMES
    blocking_reasons: list[str] = []
    if enforced and not count_matches:
        blocking_reasons.append("quote_count_gap")
    if enforced and not quote_balanced:
        blocking_reasons.append("quote_unbalanced")
    if enforced and not answer_balanced:
        blocking_reasons.append("answer_unbalanced")
    if enforced and not brackets_clear:
        blocking_reasons.append("square_bracket_residual")
    if enforced and not no_empty:
        blocking_reasons.append("empty_dialogue")
    if enforced and not paragraph_balanced:
        blocking_reasons.append("paragraph_imbalance")

    status = "pass"
    if not enforced:
        status = "frozen_reference"
    elif blocking_reasons:
        status = "fail_with_manual_evidence" if manual_evidence else "fail"
    elif nonstandard and not whitelist_evidence:
        status = "needs_whitelist_review"

    return {
        "volume": vol,
        "enforced": enforced,
        "corrected_path": str(corrected_path.relative_to(ROOT)),
        "answer_path": str(answer_path.relative_to(ROOT)),
        "corrected": {"left": corrected_left, "right": corrected_right},
        "answer": {"left": answer_left, "right": answer_right},
        "gap": {"left": answer_left - corrected_left, "right": answer_right - corrected_right},
        "quote_balanced": quote_balanced,
        "answer_balanced": answer_balanced,
        "paragraph_imbalance_count": paragraph_imbalances,
        "brackets": {"left_square": bracket_left, "right_square": bracket_right},
        "empty_dialogue_count": corrected.count("「」"),
        "nonstandard_symbols": nonstandard,
        "manual_evidence": manual_evidence,
        "whitelist_evidence": whitelist_evidence,
        "blocking_reasons": blocking_reasons,
        "status": status,
    }


def build_report() -> dict[str, object]:
    volumes = [audit_volume(v) for v in VOLUMES]
    totals = {
        "corrected_left": sum(v["corrected"]["left"] for v in volumes),  # type: ignore[index]
        "corrected_right": sum(v["corrected"]["right"] for v in volumes),  # type: ignore[index]
        "answer_left": sum(v["answer"]["left"] for v in volumes),  # type: ignore[index]
        "answer_right": sum(v["answer"]["right"] for v in volumes),  # type: ignore[index]
        "bracket_left": sum(v["brackets"]["left_square"] for v in volumes),  # type: ignore[index]
        "bracket_right": sum(v["brackets"]["right_square"] for v in volumes),  # type: ignore[index]
    }
    totals["gap_left"] = totals["answer_left"] - totals["corrected_left"]
    totals["gap_right"] = totals["answer_right"] - totals["corrected_right"]

    enforced_failures = [v for v in volumes if v["enforced"] and v["status"] != "pass"]
    return {
        "schema_version": 1,
        "enforced_volumes": sorted(ENFORCED_VOLUMES),
        "pass": not enforced_failures,
        "totals": totals,
        "volumes": volumes,
        "failure_count": len(enforced_failures),
        "failed_volumes": [v["volume"] for v in enforced_failures],
    }


def write_reports(report: dict[str, object]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Final Cross-Volume Audit",
        "",
        f"- Pass: `{str(report['pass']).lower()}`",
        f"- Enforced volumes: `{', '.join(str(v) for v in report['enforced_volumes'])}`",
        f"- Failure count: `{report['failure_count']}`",
        "",
        "| Vol | Status | Corrected | Answer | Gap | Paragraph Imbalance | Brackets | Evidence |",
        "|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["volumes"]:  # type: ignore[index]
        corrected = item["corrected"]  # type: ignore[index]
        answer = item["answer"]  # type: ignore[index]
        gap = item["gap"]  # type: ignore[index]
        brackets = item["brackets"]  # type: ignore[index]
        evidence = []
        if item["manual_evidence"]:  # type: ignore[index]
            evidence.append("manual")
        if item["whitelist_evidence"]:  # type: ignore[index]
            evidence.append("whitelist")
        lines.append(
            "| {vol} | {status} | {cl}/{cr} | {al}/{ar} | {gl:+}/{gr:+} | {pi} | {bl}/{br} | {ev} |".format(
                vol=item["volume"],  # type: ignore[index]
                status=item["status"],  # type: ignore[index]
                cl=corrected["left"],
                cr=corrected["right"],
                al=answer["left"],
                ar=answer["right"],
                gl=gap["left"],
                gr=gap["right"],
                pi=item["paragraph_imbalance_count"],  # type: ignore[index]
                bl=brackets["left_square"],
                br=brackets["right_square"],
                ev=", ".join(evidence) if evidence else "",
            )
        )

    failed = [item for item in report["volumes"] if item["enforced"] and item["status"] != "pass"]  # type: ignore[index]
    if failed:
        lines.extend(["", "## Blocking Volumes", ""])
        for item in failed:
            lines.append(
                "- Vol {vol}: {status}; reasons={reasons}; manual={manual}".format(
                    vol=item["volume"],
                    status=item["status"],
                    reasons=", ".join(item["blocking_reasons"]) or "none",
                    manual=", ".join(item["manual_evidence"]) or "none",
                )
            )
    MD_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_table(report: dict[str, object]) -> None:
    print("=" * 96)
    print("FINAL CROSS-VOLUME AUDIT")
    print("=" * 96)
    print()
    print(
        "%-6s %-18s %-18s %-14s %-18s %-12s %s"
        % ("Vol", "Corrected (L/R)", "Answer (L/R)", "Gap (L/R)", "Status", "ParaImb", "Brackets []")
    )
    print("-" * 96)
    for item in report["volumes"]:  # type: ignore[index]
        corrected = item["corrected"]  # type: ignore[index]
        answer = item["answer"]  # type: ignore[index]
        gap = item["gap"]  # type: ignore[index]
        brackets = item["brackets"]  # type: ignore[index]
        print(
            "%-6d %04d/%-04d     %04d/%-04d     %+3d/%-+3d   %-18s %-12d %d/%d"
            % (
                item["volume"],  # type: ignore[index]
                corrected["left"],
                corrected["right"],
                answer["left"],
                answer["right"],
                gap["left"],
                gap["right"],
                item["status"],  # type: ignore[index]
                item["paragraph_imbalance_count"],  # type: ignore[index]
                brackets["left_square"],
                brackets["right_square"],
            )
        )

    totals = report["totals"]  # type: ignore[index]
    print()
    print("=" * 96)
    print("TOTALS")
    print("=" * 96)
    print("Corrected JP:      %d / %d" % (totals["corrected_left"], totals["corrected_right"]))
    print("Answer JP:         %d / %d" % (totals["answer_left"], totals["answer_right"]))
    print("Gap:               %+d / %+d" % (totals["gap_left"], totals["gap_right"]))
    print("Brackets []:       %d [ + %d ]" % (totals["bracket_left"], totals["bracket_right"]))
    print("Pass:              %s" % report["pass"])
    print("JSON report:       %s" % JSON_REPORT.relative_to(ROOT))
    print("Markdown report:   %s" % MD_REPORT.relative_to(ROOT))

    ori = load_text(ROOT / "data" / "ori_story" / "第1卷.txt")
    print("\nOriginal JP in Vol 1: %d" % (ori.count("「") + ori.count("」")))


def main() -> int:
    report = build_report()
    write_reports(report)
    print_table(report)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
