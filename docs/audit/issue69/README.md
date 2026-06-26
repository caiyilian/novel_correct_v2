# Issue #69 - Ollama Tail Polish 审计报告

> 第 1 卷最终产物验收审计。

## 产物链

```
corrected_第1卷.txt (原始, 1357 非空 + 13 空「」)
  → clean_empty_dialogues (Stage 24b)
  → corrected_第1卷_clean.txt (1345 非空, 0 空)
  → generate_style_candidates --apply-low-risk (Stage 24c)
    → 674 低风险: ?→? !→！ ~→～
    → 344 高风险 period (.→。) 暂缓裁决
  → corrected_第1卷_style.txt (exact 252, punct 43, content 1050)
  → run_polish_judge (Stage 25a, Ollama qwen3:32b)
    → 344 条高风险 period 裁决 (339 apply, 4 keep, 1 uncertain)
  → apply_polish_decisions --verify (Stage 25b)
    → 339/339 应用, 0 回滚
  → corrected_第1卷.txt (最终, 1345 非空, 0 空)
```

## 文件清单

### 最终审计报告（可信，作为验收依据）

| 文件 | 说明 | 生成命令 |
|------|------|----------|
| `polish_decisions_full.jsonl` | 344 条 period 裁决 (339 apply, 4 keep, 1 uncertain, 205,895 tokens) | `run_polish_judge.py --candidates style_candidates_high.jsonl` |
| `apply_report_v2.json` | 约束应用报告 (339 applied, 0 failed) | `apply_polish_decisions.py ...` |
| `compare_final_report.json` | 对齐报告 (exact 252, punct 43, content 1050, align diffs 20) | `compare_dialogues.py --json --align` |
| `verify_report.json` | 答案匹配报告 (match rate 98.36%, 空「」0, quote 1346/1346) | `verify_against_answer.py --json` |

### 关键指标

| 指标 | 值 |
|------|-----|
| 修正非空对话 | 1345 |
| 答案非空对话 | 1349 |
| 空「」 | 0（原 13） |
| exact 匹配 | 252 (18.7%) |
| 仅标点不同 | 43 (3.2%) |
| 内容有差异 | 1050 (78.1%) |
| ignore-whitespace match rate | 98.36% |
| quote balance | 1346/1346 [OK] |
| non-standard symbols | 0 |
| alignment diffs | 20 (12 answer_split, 7 corrected_split, 1 corrected_extra) |

### 历史中间产物（不作为最终验收依据）

`output/` 目录中的以下文件是历史/中间产物，非最终验收依据：

| 文件 | 阶段 | 说明 |
|------|------|------|
| `apply_report.json` | 20 条样例测试，非全量 | 旧, Stage 25b 小样本验证 |
| `audit_compare.json` | 旧主产物 | 仍显示 97.59%, 空「」未修 |
| `audit_verify.json` | 旧主产物 | 同上 |
| `compare_第1卷.json` | 旧比对 | 修空括号前 |
| `compare_第1卷_clean.json` | clean 阶段 | 修空括号后, 未做标点 |
| `polish_decisions_20.jsonl` | 20 条样例测试 | Stage 25a 小样本验证 |
| `polish_decisions.jsonl` | 10 条样例测试 | 更早的 mock 测试 |
| `corrected_第1卷_clean.txt` | clean 阶段 | 仅清空括号, 未做标点 |
| `corrected_第1卷_style.txt` | style 阶段 | 仅低风险标点 |
| `corrected_第1卷_final20.txt` | 旧 final | 从 clean 只应用 19 条, 未继承 style |
| `corrected_第1卷_final_v2.txt` | 全量 final | 与主产物一致 |

## 未处理的结构差异

`compare_dialogues --align` 报告了 20 个分段结构差异：

- **answer_split (12)**: 答案 2 段 = 修正 1 段。答案把一句对话拆成了两句（例如加了一声应答「嗯。」）
- **corrected_split (7)**: 修正 2 段 = 答案 1 段。修正保留了独立的短句「对。」「说得对。」
- **corrected_extra (1)**: 修正多出一段

这些属于两版人工/规则分割粒度的正常差异，后续可人工审阅是否需要对齐。

## 遗留

- 344 个 high-risk period (`.`→`。`) 已通过 Ollama 裁决完毕，但未输出独立的人工审阅列表
- 第 2~11 卷可重用本卷相同的工具链分批处理
- content-diff 1050 段 (78.1%) 属于两版文字本身的语义差异，不在标点规范范围内
