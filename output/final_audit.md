# Final Cross-Volume Audit

- Pass: `false`
- Enforced volumes: `2, 3, 4, 5, 6, 7, 8, 9, 10`
- Failure count: `6`

| Vol | Status | Corrected | Answer | Gap | Paragraph Imbalance | Brackets | Evidence |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | frozen_reference | 1346/1346 | 1349/1349 | +3/+3 | 57 | 0/0 |  |
| 2 | fail_with_manual_evidence | 1425/1425 | 1425/1425 | +0/+0 | 376 | 0/0 | manual, whitelist |
| 3 | fail_with_manual_evidence | 1183/1183 | 1215/1215 | +32/+32 | 0 | 0/0 | manual |
| 4 | fail | 1561/1561 | 1561/1561 | +0/+0 | 2 | 0/0 | whitelist |
| 5 | fail_with_manual_evidence | 1455/1455 | 1459/1459 | +4/+4 | 0 | 0/0 | manual |
| 6 | fail_with_manual_evidence | 1201/1201 | 1202/1202 | +1/+1 | 0 | 0/0 | manual, whitelist |
| 7 | fail_with_manual_evidence | 1172/1172 | 1176/1176 | +4/+4 | 0 | 0/0 | manual, whitelist |
| 8 | pass | 930/930 | 930/930 | +0/+0 | 0 | 0/0 |  |
| 9 | pass | 997/997 | 997/997 | +0/+0 | 0 | 0/0 |  |
| 10 | pass | 1462/1462 | 1462/1462 | +0/+0 | 0 | 0/0 |  |

## Blocking Volumes

- Vol 2: fail_with_manual_evidence; reasons=paragraph_imbalance; manual=output\vol2_bracket_manual_queue_fix5.json
- Vol 3: fail_with_manual_evidence; reasons=quote_count_gap; manual=output\vol3_manual_review_queue.json, output\vol3_manual_review_queue.md
- Vol 4: fail; reasons=paragraph_imbalance; manual=none
- Vol 5: fail_with_manual_evidence; reasons=quote_count_gap; manual=output\vol5_source_missing_gap_queue_fix10_5.json, output\vol5_source_missing_gap_queue_fix10_5.md
- Vol 6: fail_with_manual_evidence; reasons=quote_count_gap; manual=output\vol6_gap_manual_queue_fix9.json, output\vol6_gap_manual_queue_fix9.md
- Vol 7: fail_with_manual_evidence; reasons=quote_count_gap; manual=output\vol7_manual_review_queue_fix10_7.json, output\vol7_manual_review_queue_fix10_7.md
