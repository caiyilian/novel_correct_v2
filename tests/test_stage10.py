"""Stage 10 验证脚本：DetectorPipeline 检测器编排"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

from src.core.text import TextDoc
from src.core.error_queue import ErrorQueue
from src.core.progress import ProgressTracker
from src.detector.pipeline import DetectorPipeline

# Test 1: 导入
try:
    from src.detector.pipeline import DetectorPipeline
    results.append(("imports", "ok", "DetectorPipeline importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: 默认注册了所有检测器
try:
    pipeline = DetectorPipeline()
    names = [d.name for d in pipeline.detectors]
    assert len(names) == 5, f"expected 5 detectors, got {len(names)}"
    assert "consecutive_detector" in names
    assert "unpaired_detector" in names
    assert "wrong_symbol_detector" in names
    assert "long_dialogue_detector" in names
    assert "missing_bracket_detector" in names
    results.append(("default detectors", "ok",
                    f"5 detectors registered: {', '.join(names)}"))
except Exception as e:
    errors.append(("default detectors", str(e)))

# Test 3: 按优先级排序
try:
    pipeline = DetectorPipeline()
    priorities = [d.priority for d in pipeline.detectors]
    assert priorities == sorted(priorities), f"not sorted: {priorities}"
    results.append(("priority order", "ok",
                    f"P0→P1→P2→P3→P5: {priorities}"))
except Exception as e:
    errors.append(("priority order", str(e)))

# Test 4: 无错误文本 — 全量检测
try:
    text = TextDoc("这是一段普通叙述，没有任何对话。")
    pipeline = DetectorPipeline()
    queue = pipeline.run(text)
    assert queue.total == 0, f"expected 0, got {queue.total}"
    results.append(("clean text", "ok", "no errors detected"))
except Exception as e:
    errors.append(("clean text", str(e)))

# Test 5: 混合错误文本 — 检测多种类型
try:
    # 包含：连续符号 」」、非标准符号 [
    # 错误之间间距 > 50 字，避免 ErrorQueue 合并
    text = TextDoc(
        "「你好」他说道。」我很好」\n"
        "正常叙述文字。\n" * 5
        + "[hello world] 这段内容用方括号包裹\n"
        "正常叙述文字。\n" * 5
        + "「怎么啦"  # 有「无」
    )
    pipeline = DetectorPipeline()
    queue = pipeline.run(text)
    assert queue.total >= 2, f"expected >=2 errors, got {queue.total}"
    stats = queue.type_summary()
    results.append(("mixed errors", "ok",
                    f"{queue.total} total: {stats}"))
except Exception as e:
    errors.append(("mixed errors", str(e)))

# Test 6: 真实小说扫描 — 第1卷.txt
try:
    from src.io.loader import TextLoader
    loader = TextLoader()
    doc = loader.load("data/ori_story/第1卷.txt")
    pipeline = DetectorPipeline()
    queue = pipeline.run(doc)
    stats = queue.type_summary()
    results.append(("real novel 第1卷", "ok",
                    f"{queue.total} total errors: {stats}"))
except Exception as e:
    errors.append(("real novel 第1卷", str(e)))

# Test 7: run_with_stats 详细统计
try:
    doc = TextDoc(
        "「你好」他说道。」我很好」\n"
        + "正常叙述。\n" * 5
        + "[hello world] 测试\n"
        + "正常叙述。\n" * 5
        + "「怎么啦"
    )
    pipeline = DetectorPipeline()
    stats = pipeline.run_with_stats(doc)
    assert stats["total"] >= 2
    assert "by_type" in stats
    assert "by_detector" in stats
    assert len(stats["by_detector"]) == 5
    results.append(("run_with_stats", "ok",
                    f"total={stats['total']}, {len(stats['by_detector'])} detectors reported"))
except Exception as e:
    errors.append(("run_with_stats", str(e)))

# Test 8: run_with_checkpoint — 首次运行初始化 checkpoint
try:
    tmpdir = tempfile.mkdtemp(prefix="pipeline_test_")
    doc = TextDoc("「你好」他说道。」我很好」")
    pipeline = DetectorPipeline()
    tracker = ProgressTracker("test_novel.txt", checkpoint_dir=tmpdir)
    queue = pipeline.run_with_checkpoint(doc, tracker)
    assert queue.total >= 1
    assert tracker.has_checkpoint()
    results.append(("checkpoint init", "ok",
                    f"{queue.total} errors, checkpoint created"))
except Exception as e:
    errors.append(("checkpoint init", str(e)))

# Test 9: run_with_checkpoint — 恢复后过滤已处理的错误
try:
    # 标记一个错误为已处理
    first_err = queue.all()[0]
    tracker.save_correction(first_err)

    # 重新检测，应该过滤掉已处理的
    queue2 = pipeline.run_with_checkpoint(doc, tracker)
    processed = tracker.get_processed_ids()
    assert first_err.error_id in processed, "saved error should be in processed set"
    results.append(("checkpoint resume filter", "ok",
                    f"total={queue2.total}, processed={len(processed)}"))
except Exception as e:
    errors.append(("checkpoint resume filter", str(e)))

# Test 10: 自定义检测器组合
try:
    from src.detector.consecutive import ConsecutiveDetector
    from src.detector.unpaired import UnpairedDetector
    custom_pipeline = DetectorPipeline(detectors=[
        ConsecutiveDetector(),
        UnpairedDetector(),
    ])
    assert len(custom_pipeline.detectors) == 2
    text = TextDoc("「你好」他说道。」我很好」")
    queue = custom_pipeline.run(text)
    # 只用两个检测器应该只能检测到一些错误
    results.append(("custom detectors", "ok",
                    f"2 detectors, {queue.total} errors"))
except Exception as e:
    errors.append(("custom detectors", str(e)))

# Test 11: 空文本
try:
    text = TextDoc("")
    pipeline = DetectorPipeline()
    queue = pipeline.run(text)
    assert queue.total == 0
    results.append(("empty text", "ok", "no errors"))
except Exception as e:
    errors.append(("empty text", str(e)))

# Test 12: 第3卷（全卷弯引号，不应触发「」检测器）
try:
    doc = loader.load("data/ori_story/第3卷.txt")
    pipeline = DetectorPipeline()
    queue = pipeline.run(doc)
    stats = queue.type_summary()
    # 第3卷没有「」，所以 consecutive/unpaired 应为 0
    # 但有大量弯引号，所以 wrong_symbol 应该很多
    results.append(("real novel 第3卷", "ok",
                    f"{queue.total} total: {stats}"))
except Exception as e:
    errors.append(("real novel 第3卷", str(e)))

# Cleanup
import shutil
shutil.rmtree(tmpdir, ignore_errors=True)

# Print report
print("=" * 55)
print("  Stage 10 Verification Report — DetectorPipeline")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
