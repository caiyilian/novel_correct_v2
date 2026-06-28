"""
魔女之旅全卷「」配平审计工具

功能：
1. 扫描每个文件，追踪「」累积配平
2. 输出每个偏差点位置（行号、上下文）
3. 分类：真缺失 / 多余 / 跨段对话（误报）
4. 生成审计报告
"""

import os, glob, sys
from pathlib import Path

TARGET = Path(r'E:\projects\novel_correct_v2\data\魔女之旅')
FILES = [
    '第一卷.txt', '第十六卷.txt', '第十五卷 短篇集.txt',
    '番外 莉莉艾尔与祈祷之国.txt', '第五卷.txt',
]

def load_text(fp: Path) -> str:
    with open(fp, 'rb') as f:
        raw = f.read()
    if raw[:2] == b'\xff\xfe':
        return raw.decode('utf-16-le')
    elif raw[:2] == b'\xfe\xff':
        return raw.decode('utf-16-be')
    else:
        return raw.decode('utf-8')

def audit_file(name: str) -> list:
    """返回不平衡事件列表: [(line_no, col, type, context_before, context_mid, context_after), ...]"""
    fp = TARGET / name
    text = load_text(fp)
    lines = text.split('\n')

    events = []
    balance = 0
    for lineno, line in enumerate(lines, 1):
        for col, ch in enumerate(line):
            if ch == '\u300c':
                balance += 1
            elif ch == '\u300d':
                balance -= 1
            # Record when balance goes negative (too many closing)
            if balance < 0:
                # find the position of the closing quote that caused it
                # Find the last 「 or 」 near col
                start = max(0, col - 80)
                end = min(len(line), col + 80)
                ctx_before = lines[max(0, lineno-3):lineno]
                ctx_mid = line
                ctx_after = lines[lineno:min(len(lines), lineno+3)]
                events.append({
                    'line': lineno, 'col': col, 'balance': balance, 'type': '多余」',
                    'char': ch, 'context_before': ctx_before, 'context_mid': ctx_mid,
                    'context_after': ctx_after
                })
                # Fix: we don't reset balance here since it's already negative
                # We'll report each negative event only once
                break  # Only report first negative event per line to avoid spam

    # After scanning, if balance > 0, report as missing closing quotes
    # Need more accurate detection: find lines where cumulative balance peaks and ends non-zero
    # Let's do a more thorough scan
    
    # Reset and do thorough second pass
    balance = 0
    gap_positions = []  # (line, col, cum_balance_before)
    for lineno, line in enumerate(lines, 1):
        for col, ch in enumerate(line):
            if ch == '\u300c':
                gap_positions.append((lineno, col, balance, 'open'))
                balance += 1
            elif ch == '\u300d':
                balance -= 1
                gap_positions.append((lineno, col, balance, 'close'))
    
    # Now analyze: find mismatches
    # Method: scan through gappositions and find when close makes balance negative
    # or when balance > 0 at EOF
    mismatches = []
    bal = 0
    open_positions = []  # stack
    
    for lineno, col, prev_bal, typ in gap_positions:
        if typ == 'open':
            bal += 1
            open_positions.append((lineno, col))
        else:  # close
            if bal <= 0:
                # closing without matching open
                start = max(0, col - 60)
                end = min(len(lines[lineno-1]), col + 60)
                mismatches.append({
                    'line': lineno, 'col': col,
                    'type': '多余」', 'char': '」',
                    'balance_before': bal,
                    'context': f"...{lines[lineno-1][start:end]}..."
                })
            else:
                bal -= 1
                open_positions.pop()
    
    # Unmatched opens
    for open_lineno, open_col in open_positions:
        start = max(0, open_col - 60)
        end = min(len(lines[open_lineno-1]), open_col + 60)
        mismatches.append({
            'line': open_lineno, 'col': open_col,
            'type': '缺失」', 'char': '「',
            'balance_before': -1,
            'context': f"...{lines[open_lineno-1][start:end]}..."
        })
    
    return mismatches

def main():
    report = []
    report.append('# 魔女之旅全卷「」配平审计报告\n')
    report.append(f'审计时间: 2026-06-28\n')
    report.append(f'目标目录: {TARGET}\n\n')

    total_mismatches = 0
    for name in FILES:
        fp = TARGET / name
        if not fp.exists():
            report.append(f'## {name}\n文件不存在，跳过。\n\n')
            continue
        
        text = load_text(fp)
        l_count = text.count('\u300c')
        r_count = text.count('\u300d')
        diff = l_count - r_count
        mismatches = audit_file(name)
        total_mismatches += len(mismatches)
        
        report.append(f'## {name}\n')
        report.append(f'- 「: {l_count}, 」: {r_count}, 差: {diff:+d}\n')
        report.append(f'- 检出偏差点: {len(mismatches)}\n\n')
        
        if not mismatches:
            report.append('> ✅ 完全配平，无偏差点\n\n')
        else:
            for i, m in enumerate(mismatches, 1):
                report.append(f'### 偏差 #{i}: 第{m["line"]}行')
                if m['type'] == '多余」':
                    report.append(f'(多余「」)')
                else:
                    report.append(f'(缺失「」)')
                report.append('\n\n')
                report.append(f'- **类型**: {m["type"]}\n')
                report.append(f'- **位置**: 第{m["line"]}行，第{m["col"]}列\n')
                report.append(f'- **平衡状态**: 之前为 {m["balance_before"]}\n')
                report.append(f'- **上下文**:\n\n```\n{m["context"]}\n```\n\n')
    
    report.append(f'---\n## 合计\n\n')
    report.append(f'- 偏差点总计: {total_mismatches}\n')
    
    # Write report
    out_path = Path(r'E:\projects\novel_correct_v2\output\majourney_audit.md')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(report), encoding='utf-8')
    print(f'报告已写入: {out_path}')
    print(f'偏差点总计: {total_mismatches}')

    # Also write a summary line for verification
    by_file = {}
    for name in FILES:
        fp = TARGET / name
        if fp.exists():
            text = load_text(fp)
            l = text.count('\u300c')
            r = text.count('\u300d')
            by_file[name] = {'l': l, 'r': r, 'diff': l-r, 'mismatches': len(audit_file(name))}
    
    print('\n详细统计:')
    print(f'{"卷":-<26} {"「":>7} {"」":>7} {"差":>5} {"偏差点":>7}')
    print('-' * 55)
    for name in FILES:
        d = by_file.get(name, {})
        print(f'{name:<24} {d.get("l",0):>7} {d.get("r",0):>7} {d.get("diff",0):>+5} {d.get("mismatches",0):>7}')
    print('-' * 55)

if __name__ == '__main__':
    main()
