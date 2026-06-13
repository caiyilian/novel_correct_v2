"""Stage 5 验证脚本：ProgressTracker 进度持久化"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

from src.core.error_record import ErrorRecord, ErrorStatus
from src.core.error_queue import ErrorQueue
from src.core.progress import ProgressTracker

# Test 1: 导入
try:
    from src.core.progress import ProgressTracker, Checkpoint
    results.append(("imports", "ok", "ProgressTracker, Checkpoint importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: 初始化 checkpoint
try:
    tmpdir = tempfile.mkdtemp(prefix="checkpoint_test_")
    tracker = ProgressTracker("test_novel.txt", checkpoint_dir=tmpdir)

    q = ErrorQueue()
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=1, offset=100))
    q.add(ErrorRecord(error_type="consecutive", line_number=5, offset=500))
    q.add(ErrorRecord(error_type="unpaired", line_number=10, offset=1000))

    tracker.init_checkpoint(q, hard_indicators={
        "bracket_balanced": False,
        "no_consecutive": False,
    })

    assert tracker.has_checkpoint()
    assert tracker.progress_path.exists()
    assert tracker.indicators_path.exists()

    results.append(("init_checkpoint", "ok",
                    f"dir={tracker._novel_dir.name}, files created"))
except Exception as e:
    errors.append(("init_checkpoint", str(e)))

# Test 3: 保存修正记录
try:
    err = q.all()[0]
    err.mark_fixed(fix="[ -> 「", verdict="pass", reason="obvious dialog")
    tracker.save_correction(err, {"evidence": "line 2 shows speaker"})

    # 检查 jsonl
    assert tracker.corrections_path.exists()
    with open(tracker.corrections_path, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["error_id"] == err.error_id
    assert entry["status"] == "fixed"
    assert entry["fix_applied"] == "[ -> 「"

    results.append(("save_correction", "ok",
                    f"written to corrections.jsonl, entry={entry['error_id']}"))
except Exception as e:
    errors.append(("save_correction", str(e)))

# Test 4: 保存跳过/失败记录
try:
    err2 = q.all()[1]
    err2.mark_skipped(reason="not a dialog bracket")
    tracker.save_correction(err2)

    err3 = q.all()[2]
    err3.mark_failed(reason="verifier rejected")
    tracker.save_correction(err3)

    with open(tracker.corrections_path, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    assert len(entries) == 3

    statuses = {e["error_id"]: e["status"] for e in entries}
    assert "skipped" in statuses.values()
    assert "failed" in statuses.values()

    results.append(("save multi-status", "ok",
                    f"3 entries: fixed/skipped/failed"))
except Exception as e:
    errors.append(("save multi-status", str(e)))

# Test 5: 更新进度
try:
    tracker.update_progress(q)

    with open(tracker.progress_path, encoding="utf-8") as f:
        progress = json.load(f)

    assert progress["progress"]["total"] == 3
    assert progress["progress"]["fixed"] == 1
    assert progress["progress"]["skipped"] == 1
    assert progress["progress"]["failed"] == 1
    assert progress["novel_path"] == tracker.novel_path
    assert "timestamp" in progress

    results.append(("update_progress", "ok",
                    f"total={progress['progress']['total']}"))
except Exception as e:
    errors.append(("update_progress", str(e)))

# Test 6: 获取已处理的 ID
try:
    processed = tracker.get_processed_ids()
    assert len(processed) == 3
    assert err.error_id in processed
    assert err2.error_id in processed
    assert err3.error_id in processed

    results.append(("get_processed_ids", "ok",
                    f"{len(processed)} processed IDs"))
except Exception as e:
    errors.append(("get_processed_ids", str(e)))

# Test 7: 加载 checkpoint
try:
    loaded_queue = tracker.load_checkpoint()
    assert loaded_queue is not None
    loaded_all = loaded_queue.all()
    assert len(loaded_all) == 3

    # 加载后状态应该保留
    status_map = {e.error_id: e.status for e in loaded_all}
    assert status_map[err.error_id] == "fixed"

    results.append(("load_checkpoint", "ok",
                    f"loaded {len(loaded_all)} records with status preserved"))
except Exception as e:
    errors.append(("load_checkpoint", str(e)))

# Test 8: 无 checkpoint 时返回 None
try:
    tracker2 = ProgressTracker("nonexistent.txt", checkpoint_dir=tmpdir)
    assert tracker2.has_checkpoint() is False
    assert tracker2.load_checkpoint() is None

    results.append(("no checkpoint", "ok",
                    "returns None when no checkpoint exists"))
except Exception as e:
    errors.append(("no checkpoint", str(e)))

# Test 9: 加载修正记录列表
try:
    corrections = tracker.load_corrections()
    assert len(corrections) == 3
    assert corrections[0]["error_id"] == err.error_id

    results.append(("load_corrections", "ok",
                    f"{len(corrections)} correction entries"))
except Exception as e:
    errors.append(("load_corrections", str(e)))

# Test 10: 进度摘要
try:
    summary = tracker.get_progress_summary()
    assert summary is not None
    assert summary["progress"]["total"] == 3

    indicators = tracker.get_indicators()
    assert indicators is not None
    assert indicators["bracket_balanced"] is False

    results.append(("progress/indicators query", "ok",
                    "summary and indicators loadable"))
except Exception as e:
    errors.append(("progress/indicators query", str(e)))

# Test 11: 生成报告
try:
    report = tracker.generate_report(error_queue=q)
    assert report["summary"]["total_errors"] == 3
    assert report["summary"]["fixed"] == 1
    assert report["summary"]["skipped"] == 1
    assert report["summary"]["failed"] == 1
    assert "hard_indicators" in report
    assert "generated_at" in report

    results.append(("generate_report", "ok",
                    f"report summary: {report['summary']}"))
except Exception as e:
    errors.append(("generate_report", str(e)))

# Test 12: 生成报告并写入文件
try:
    output_dir = os.path.join(tmpdir, "report_output")
    report = tracker.generate_report(error_queue=q, output_dir=output_dir)

    json_path = os.path.join(output_dir, "correction_report.json")
    txt_path = os.path.join(output_dir, "correction_report.txt")
    assert os.path.exists(json_path)
    assert os.path.exists(txt_path)

    with open(txt_path, encoding="utf-8") as f:
        txt_content = f.read()
    assert "纠错报告" in txt_content
    assert "已修正" in txt_content

    results.append(("report output to files", "ok",
                    "both json and txt reports written"))
except Exception as e:
    errors.append(("report output to files", str(e)))

# Test 13: 清除 checkpoint
try:
    assert tracker._novel_dir.exists()
    tracker.clear()
    assert not tracker._novel_dir.exists()

    results.append(("clear checkpoint", "ok",
                    "checkpoint directory removed"))
except Exception as e:
    errors.append(("clear checkpoint", str(e)))

# Test 14: 多种错误类型的报告
try:
    q2 = ErrorQueue()
    for i in range(5):
        q2.add(ErrorRecord(error_type="wrong_symbol", line_number=i, offset=i*100))
    for i in range(3):
        q2.add(ErrorRecord(error_type="consecutive", line_number=i+10, offset=i*100+1000))

    tracker3 = ProgressTracker("multi_type.txt", checkpoint_dir=tmpdir)
    tracker3.init_checkpoint(q2)

    # 标记部分完成
    all_errs = q2.all()
    for i, e in enumerate(all_errs):
        if i < 4:
            e.mark_fixed(fix=f"fix-{i}")
            tracker3.save_correction(e)
        elif i < 6:
            e.mark_skipped(f"skip-{i}")
            tracker3.save_correction(e)
    tracker3.update_progress(q2)

    report = tracker3.generate_report(error_queue=q2)
    assert report["summary"]["fixed"] == 4
    assert report["summary"]["skipped"] == 2
    assert report["summary"]["remaining"] == 2

    results.append(("multi-type report", "ok",
                    f"fixed={report['summary']['fixed']}, "
                    f"skipped={report['summary']['skipped']}, "
                    f"remaining={report['summary']['remaining']}"))
except Exception as e:
    errors.append(("multi-type report", str(e)))

# Test 15: 从 checkpoint 恢复（验证已处理ID集合）
try:
    # 先验证 tracker3 的 corrections 文件存在且非空
    assert tracker3.corrections_path.exists(), \
        f"corrections file missing: {tracker3.corrections_path}"
    
    with open(tracker3.corrections_path, encoding="utf-8") as f:
        raw_lines = [l for l in f if l.strip()]
    
    assert len(raw_lines) > 0, "corrections.jsonl is empty"
    
    processed_ids = tracker3.get_processed_ids()
    assert len(processed_ids) == 6, \
        f"expected 6 processed IDs, got {len(processed_ids)}: {processed_ids}"

    results.append(("get_processed_ids count", "ok",
                    f"{len(processed_ids)} IDs from corrections.jsonl"))
except Exception as e:
    errors.append(("get_processed_ids count", str(e)))

# Cleanup
shutil.rmtree(tmpdir, ignore_errors=True)

# Print report
print("=" * 55)
print("  Stage 5 Verification Report — ProgressTracker")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
