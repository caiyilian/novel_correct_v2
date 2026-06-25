"""Stage 19e 验证脚本：新增 wrong_symbol 候选覆盖。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.candidates import CandidateGenerator
from src.core.text import TextDoc
from src.detector.pipeline import DetectorPipeline
from src.detector.wrong_symbol import WrongSymbolDetector
from src.io.loader import TextLoader


results = []
errors = []


def wrong_symbol_errors(text: str):
    doc = TextDoc(text)
    errors = WrongSymbolDetector().detect(doc)
    return doc, errors


try:
    doc, detected = wrong_symbol_errors("「这是[重要的事]，别忘了。」")
    assert len(detected) == 2, [
        (item.offset, item.original_text, item.is_nested)
        for item in detected
    ]
    assert all(item.is_nested for item in detected)
    generator = CandidateGenerator()
    for error in detected:
        candidates = generator.generate(doc, error)
        assert candidates, (error.offset, error.original_text)
        replacements = {item.replacement for item in candidates}
        assert "「" in replacements or "」" in replacements
    results.append(("nested square bracket candidates", "ok", "2/2 nested symbols covered"))
except Exception as exc:
    errors.append(("nested square bracket candidates", str(exc)))


try:
    doc, detected = wrong_symbol_errors("「他说“你好”。」")
    assert len(detected) == 2, [
        (item.offset, item.original_text, item.is_nested)
        for item in detected
    ]
    assert all(item.is_nested for item in detected)
    generator = CandidateGenerator()
    for error in detected:
        candidates = generator.generate(doc, error)
        assert candidates, (error.offset, error.original_text)
        replacements = {item.replacement for item in candidates}
        assert "「" in replacements or "」" in replacements
    results.append(("nested curly quote candidates", "ok", "2/2 nested quotes covered"))
except Exception as exc:
    errors.append(("nested curly quote candidates", str(exc)))


try:
    corrected_files = sorted(Path("output").glob("corrected_*.txt"))
    assert corrected_files, "no corrected_*.txt found in output/"
    doc = TextLoader().load(corrected_files[0])
    queue = DetectorPipeline().run(doc)
    generator = CandidateGenerator()

    total = 0
    covered = 0
    nested_total = 0
    nested_covered = 0
    missing = []

    for error in queue:
        if error.error_type != "wrong_symbol":
            continue
        total += 1
        if error.is_nested:
            nested_total += 1
        candidates = generator.generate(doc, error)
        if candidates:
            covered += 1
            if error.is_nested:
                nested_covered += 1
        else:
            missing.append((error.error_id, error.line_number, error.offset, error.original_text))

    if total:
        assert covered / total >= 0.95, missing[:10]
    if nested_total:
        assert nested_covered / nested_total >= 0.95, missing[:10]
    results.append((
        "corrected novel wrong_symbol coverage",
        "ok",
        f"wrong_symbol={covered}/{total}, nested={nested_covered}/{nested_total}",
    ))
except Exception as exc:
    errors.append(("corrected novel wrong_symbol coverage", str(exc)))


print("=" * 55)
print("  Stage 19e Verification Report — Candidate Coverage")
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
