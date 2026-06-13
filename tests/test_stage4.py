"""Stage 4 验证脚本：ErrorRecord & ErrorQueue"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

# Test 1: 导入
try:
    from src.core.error_record import (
        ErrorRecord, ErrorType, ErrorStatus, VerifierVerdict
    )
    from src.core.error_queue import ErrorQueue
    results.append(("imports", "ok", "all classes importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: ErrorRecord 创建
try:
    err = ErrorRecord(
        error_type="wrong_symbol",
        line_number=42,
        offset=1234,
        context_before="...前面的内容",
        context_after="后面的内容...",
        original_text="[你好吗]",
    )
    assert err.error_id.startswith("e-"), f"unexpected error_id: {err.error_id}"
    assert err.error_type == "wrong_symbol"
    assert err.line_number == 42
    assert err.offset == 1234
    assert err.original_text == "[你好吗]"
    assert err.status == "pending"
    assert err.verifier_verdict == "pending"
    assert err.is_resolved is False
    results.append(("ErrorRecord create", "ok",
                    f"id={err.error_id}, type={err.error_type}, L{err.line_number}"))
except Exception as e:
    errors.append(("ErrorRecord create", str(e)))

# Test 3: ErrorRecord 状态转换
try:
    err = ErrorRecord(error_type="consecutive", line_number=10, offset=500)
    assert err.is_resolved is False

    err.mark_fixed(fix="」→「", verdict="pass", reason="correct")
    assert err.status == "fixed"
    assert err.fix_applied == "」→「"
    assert err.verifier_verdict == "pass"
    assert err.is_resolved is True

    err2 = ErrorRecord(error_type="unpaired", line_number=20, offset=600)
    err2.mark_skipped(reason="not an error")
    assert err2.status == "skipped"
    assert err2.skip_reason == "not an error"
    assert err2.is_resolved is True

    err3 = ErrorRecord(error_type="wrong_symbol", line_number=30, offset=700)
    err3.mark_failed(reason="verifier rejected")
    assert err3.status == "failed"
    assert err3.fail_reason == "verifier rejected"
    assert err3.is_resolved is True

    results.append(("ErrorRecord state transitions", "ok",
                    "fixed/skipped/failed all work"))
except Exception as e:
    errors.append(("ErrorRecord state transitions", str(e)))

# Test 4: ErrorRecord 枚举值
try:
    assert ErrorType.CONSECUTIVE.value == "consecutive"
    assert ErrorType.WRONG_SYMBOL.value == "wrong_symbol"
    assert ErrorStatus.PENDING.value == "pending"
    assert ErrorStatus.FIXED.value == "fixed"
    assert VerifierVerdict.PASS.value == "pass"
    results.append(("ErrorRecord enums", "ok", "all enum values correct"))
except Exception as e:
    errors.append(("ErrorRecord enums", str(e)))

# Test 5: ErrorRecord 序列化
try:
    err = ErrorRecord(
        error_type="wrong_symbol", line_number=5, offset=100,
        original_text="[test]"
    )
    err.mark_fixed(fix="「test」", verdict="pass")
    d = err.to_dict()
    assert d["error_id"] == err.error_id
    assert d["error_type"] == "wrong_symbol"
    assert d["status"] == "fixed"
    assert d["fix_applied"] == "「test」"

    # 反序列化
    err2 = ErrorRecord.from_dict(d)
    assert err2.error_id == err.error_id
    assert err2.error_type == "wrong_symbol"
    assert err2.status == "fixed"
    assert err2.fix_applied == "「test」"

    results.append(("ErrorRecord serialization", "ok",
                    "to_dict/from_dict round-trip works"))
except Exception as e:
    errors.append(("ErrorRecord serialization", str(e)))

# Test 6: ErrorSummary
try:
    err = ErrorRecord(
        error_type="wrong_symbol", line_number=7, offset=200,
        original_text="【注意】这是注释"
    )
    summary = err.summary
    assert "e-" in summary
    assert "L7" in summary
    assert "wrong_symbol" in summary
    results.append(("ErrorRecord summary", "ok", f"summary={summary[:60]}"))
except Exception as e:
    errors.append(("ErrorRecord summary", str(e)))

# Test 7: ErrorQueue 基础操作
try:
    q = ErrorQueue()
    assert len(q) == 0
    assert q.total == 0
    assert q.remaining() == 0
    assert q.next_pending() is None
    results.append(("ErrorQueue empty", "ok", "empty queue behaves correctly"))
except Exception as e:
    errors.append(("ErrorQueue empty", str(e)))

# Test 8: ErrorQueue 添加和排序
try:
    q = ErrorQueue()
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=3, offset=300))
    q.add(ErrorRecord(error_type="consecutive", line_number=1, offset=100))
    q.add(ErrorRecord(error_type="unpaired", line_number=2, offset=200))

    all_errors = q.all()
    assert len(all_errors) == 3
    # 应该按 offset 排序
    assert all_errors[0].offset == 100
    assert all_errors[1].offset == 200
    assert all_errors[2].offset == 300

    results.append(("ErrorQueue ordering", "ok",
                    "errors sorted by offset"))
except Exception as e:
    errors.append(("ErrorQueue ordering", str(e)))

# Test 9: ErrorQueue 自动去重合并
try:
    q = ErrorQueue()
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=5, offset=500))
    # 在合并半径内添加另一个错误
    q.add(ErrorRecord(error_type="consecutive", line_number=5, offset=520))
    # 应该合并，总数还是 1
    assert len(q) == 1, f"expected 1 after merge, got {len(q)}"
    # 保留优先级更高的类型 (wrong_symbol > consecutive)
    merged = q.all()[0]
    assert merged.error_type == "wrong_symbol", \
        f"expected wrong_symbol (higher priority), got {merged.error_type}"

    # 在合并半径外添加
    q.add(ErrorRecord(error_type="unpaired", line_number=10, offset=600))
    assert len(q) == 2, f"expected 2, got {len(q)}"

    results.append(("ErrorQueue dedup/merge", "ok",
                    "50-char merge radius works"))
except Exception as e:
    errors.append(("ErrorQueue dedup/merge", str(e)))

# Test 10: ErrorQueue 进度查询
try:
    q = ErrorQueue()
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=1, offset=100))
    q.add(ErrorRecord(error_type="consecutive", line_number=2, offset=200))
    q.add(ErrorRecord(error_type="unpaired", line_number=3, offset=300))
    q.add(ErrorRecord(error_type="long_dialogue", line_number=4, offset=400))

    p = q.progress()
    assert p["total"] == 4
    assert p["pending"] == 4
    assert p["remaining"] == 4

    q.mark_fixed(q.all()[0].error_id, fix="fix1")
    q.mark_skipped(q.all()[1].error_id, reason="skip1")

    p = q.progress()
    assert p["fixed"] == 1
    assert p["skipped"] == 1
    assert p["pending"] == 2
    assert p["remaining"] == 2

    results.append(("ErrorQueue progress", "ok",
                    f"total={p['total']}, fixed={p['fixed']}, skipped={p['skipped']}, "
                    f"pending={p['pending']}"))
except Exception as e:
    errors.append(("ErrorQueue progress", str(e)))

# Test 11: ErrorQueue next_pending
try:
    q = ErrorQueue()
    q.add(ErrorRecord(error_type="consecutive", line_number=1, offset=100))
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=2, offset=200))
    q.add(ErrorRecord(error_type="unpaired", line_number=3, offset=300))

    first = q.next_pending()
    assert first is not None
    assert first.line_number == 1  # 按 offset 排序，第一个

    q.mark_fixed(first.error_id, fix="done")
    second = q.next_pending()
    assert second is not None
    assert second.line_number == 2

    results.append(("ErrorQueue next_pending", "ok",
                    "iterates in order"))
except Exception as e:
    errors.append(("ErrorQueue next_pending", str(e)))

# Test 12: ErrorQueue 过滤
try:
    q = ErrorQueue()
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=1, offset=100))
    q.add(ErrorRecord(error_type="consecutive", line_number=2, offset=200))
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=3, offset=300))

    ws = q.by_type("wrong_symbol")
    assert len(ws) == 2

    pending = q.by_status("pending")
    assert len(pending) == 3

    q.mark_fixed(ws[0].error_id, fix="done")
    pending = q.by_status("pending")
    assert len(pending) == 2

    results.append(("ErrorQueue filtering", "ok",
                    "by_type and by_status work"))
except Exception as e:
    errors.append(("ErrorQueue filtering", str(e)))

# Test 13: ErrorQueue type_summary
try:
    q = ErrorQueue()
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=1, offset=100))
    q.add(ErrorRecord(error_type="consecutive", line_number=2, offset=200))
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=3, offset=300))
    q.add(ErrorRecord(error_type="unpaired", line_number=4, offset=400))

    summary = q.type_summary()
    assert summary["wrong_symbol"] == 2
    assert summary["consecutive"] == 1
    assert summary["unpaired"] == 1

    results.append(("ErrorQueue type_summary", "ok",
                    f"distribution: {summary}"))
except Exception as e:
    errors.append(("ErrorQueue type_summary", str(e)))

# Test 14: ErrorQueue 序列化
try:
    q = ErrorQueue()
    q.add(ErrorRecord(error_type="wrong_symbol", line_number=1, offset=100))
    q.add(ErrorRecord(error_type="consecutive", line_number=2, offset=200))
    q.mark_fixed(q.all()[0].error_id, fix="done")

    dlist = q.to_dict_list()
    assert len(dlist) == 2

    q2 = ErrorQueue.from_dict_list(dlist)
    assert len(q2) == 2
    assert q2.all()[0].error_type == "wrong_symbol"
    assert q2.all()[0].status == "fixed"

    json_str = q.to_json()
    parsed = json.loads(json_str)
    assert len(parsed) == 2

    results.append(("ErrorQueue serialization", "ok",
                    "to_dict_list/from_dict_list/to_json all work"))
except Exception as e:
    errors.append(("ErrorQueue serialization", str(e)))

# Test 15: 批量添加
try:
    q = ErrorQueue()
    records = [
        ErrorRecord(error_type="wrong_symbol", line_number=i, offset=i * 100)
        for i in range(1, 6)
    ]
    q.extend(records)
    assert len(q) == 5
    results.append(("ErrorQueue extend", "ok", f"batch added {len(q)} records"))
except Exception as e:
    errors.append(("ErrorQueue extend", str(e)))

# Test 16: 空的 Progress
try:
    q = ErrorQueue()
    p = q.progress()
    assert p["total"] == 0
    assert p["remaining"] == 0
    assert p["percent"] == 100.0
    results.append(("ErrorQueue empty progress", "ok",
                    "empty queue shows 100% done"))
except Exception as e:
    errors.append(("ErrorQueue empty progress", str(e)))

# Print report
print("=" * 55)
print("  Stage 4 Verification Report — ErrorRecord & ErrorQueue")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
