# Fix 12 全卷最终验收报告

本报告基于最新 `master` 运行 `python tools/final_audit.py` 后生成。

## 结论

当前全卷最终验收未通过。

- `tools/final_audit.py` exit code：1
- `output/final_audit.json`：`pass=false`
- 强制验收范围：第2卷至第10卷
- 失败卷：第2、3、4、5、6、7卷
- 通过卷：第8、9、10卷
- 第1卷：冻结参考，不纳入本轮强制通过判定

## 当前卷级状态

| 卷 | 状态 | 当前 `「/」` | 答案 `「/」` | 缺口 | 阻塞原因 |
|---:|---|---:|---:|---:|---|
| 1 | frozen_reference | 1346/1346 | 1349/1349 | +3/+3 | 第1卷按前序讨论冻结 |
| 2 | fail_with_manual_evidence | 1425/1425 | 1425/1425 | +0/+0 | paragraph_imbalance=376 |
| 3 | fail_with_manual_evidence | 1183/1183 | 1215/1215 | +32/+32 | quote_count_gap，已有人工队列 |
| 4 | fail | 1561/1561 | 1561/1561 | +0/+0 | paragraph_imbalance=2 |
| 5 | fail_with_manual_evidence | 1455/1455 | 1459/1459 | +4/+4 | 4 个答案侧独立 `「……」` 在 OCR 主产物中无可包裹原文 |
| 6 | fail_with_manual_evidence | 1201/1201 | 1202/1202 | +1/+1 | 答案侧缺失句在 OCR 主产物中未找到 |
| 7 | fail_with_manual_evidence | 1172/1172 | 1176/1176 | +4/+4 | 4 处涉及答案侧额外文本或 OCR 文本差异 |
| 8 | pass | 930/930 | 930/930 | +0/+0 | 已通过 |
| 9 | pass | 997/997 | 997/997 | +0/+0 | 已通过 |
| 10 | pass | 1462/1462 | 1462/1462 | +0/+0 | 已通过 |

## 已提交的关键线索

- 第3卷：`output/vol3_manual_review_queue.json`、`output/vol3_manual_review_queue.md`
- 第5卷：`output/vol5_source_missing_gap_queue_fix10_5.json`、`output/vol5_source_missing_gap_queue_fix10_5.md`
- 第6卷：`output/vol6_gap_manual_queue_fix9.json`、`output/vol6_gap_manual_queue_fix9.md`
- 第7卷：`output/vol7_manual_review_queue_fix10_7.json`、`output/vol7_manual_review_queue_fix10_7.md`
- 第4/6/7卷白名单线索：对应 `output/*whitelist*.json`

## 后续建议

不能把当前状态标记为全卷完成。后续应单独开新阶段处理：

1. 第2卷、第4卷 paragraph imbalance 的真实含义复核，区分检测器误报、合法书名号/嵌套符号与实际 P0/P1 结构错误。
2. 第3卷 32 对缺口的人工队列复核；仅允许包裹 OCR 已有文本，不复制答案正文。
3. 第5、6、7卷来源缺失项的产品决策：如果允许插入答案侧缺失的沉默符号或短句，需要另开明确授权阶段；否则这些应作为 OCR/答案版本差异记录。

本阶段未修改任何 `output/corrected_第X卷.txt` 主产物。
