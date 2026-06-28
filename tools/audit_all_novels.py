"""Audit all novel files in data/ for 「」 imbalance - output detailed report"""
import os, glob

data_dir = r'E:\projects\novel_correct_v2\data'
out_file = r'E:\projects\novel_correct_v2\output\all_novels_audit_report.md'

series_dirs = sorted([d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))])

def find_imbalance_positions(text):
    """Find positions where running balance deviates from expected"""
    positions = []
    balance = 0
    in_dialogue = False
    last_open_line = -1

    lines = text.split('\n')
    line_starts = [0]
    for line in lines[:-1]:
        line_starts.append(line_starts[-1] + len(line) + 1)

    for i, ch in enumerate(text):
        if ch == '\u300c':  # 「
            if balance == 0:
                # Starting a new dialogue segment
                line_num = 0
                for idx, start in enumerate(line_starts):
                    if start > i:
                        break
                    line_num = idx + 1
                last_open_line = line_num
            balance += 1
        elif ch == '\u300d':  # 」
            balance -= 1
            if balance < 0:
                # Extra closing bracket
                line_num = 0
                for idx, start in enumerate(line_starts):
                    if start > i:
                        break
                    line_num = idx + 1
                positions.append({
                    'pos': i, 'line': line_num, 'type': 'extra_close',
                    'context': get_context(text, i)
                })
                balance = 0

    # Check final balance - indicates missing closing brackets
    if balance > 0:
        positions.append({
            'pos': len(text), 'line': last_open_line, 'type': 'missing_close',
            'count': balance
        })
    elif balance < 0:
        positions.append({
            'pos': len(text), 'line': -1, 'type': 'extra_open',
            'count': -balance
        })
    return positions

def get_context(text, pos, window=40):
    start = max(0, pos - window)
    end = min(len(text), pos + window)
    ctx = text[start:end].replace('\n', '\\n')
    return ctx

lines = []
lines.append('# 全卷「」配平审计报告\n')
lines.append(f'审计时间: 2026-06-28\n')
lines.append('=' * 80 + '\n')

total_imbalanced = 0
total_l = total_r = 0

for series in series_dirs:
    series_path = os.path.join(data_dir, series)
    files = sorted(glob.glob(os.path.join(series_path, '*.txt')))
    if not files:
        continue

    series_l = series_r = 0
    series_imbalanced = []

    for fp in files:
        with open(fp, 'rb') as fh:
            raw = fh.read()
        if raw[:2] == b'\xff\xfe':
            text = raw.decode('utf-16-le')
        elif raw[:2] == b'\xfe\xff':
            text = raw.decode('utf-16-be')
        else:
            text = raw.decode('utf-8', errors='replace')

        l = text.count('\u300c')
        r = text.count('\u300d')
        series_l += l
        series_r += r

        if l != r:
            positions = find_imbalance_positions(text)
            series_imbalanced.append({
                'file': os.path.basename(fp), 'l': l, 'r': r, 'diff': l - r,
                'positions': positions
            })

    lines.append(f'\n## {series}\n')
    lines.append(f'总「: {series_l}  总」: {series_r}  差: {series_l - series_r:+d}\n')

    if series_imbalanced:
        total_imbalanced += len(series_imbalanced)
        lines.append(f'不配平文件数: {len(series_imbalanced)}\n')
        for item in series_imbalanced:
            lines.append(f'\n### {item["file"]}\n')
            lines.append(f'「: {item["l"]}  」: {item["r"]}  差: {item["diff"]:+d}\n')
            lines.append('偏差点:\n')
            for p in item['positions']:
                if p['type'] == 'extra_close':
                    lines.append(f'  - line {p["line"]}: 多余」 - {p["context"]}\n')
                elif p['type'] == 'missing_close':
                    lines.append(f'  - line {p["line"]}: 缺失」 x{p["count"]}\n')
                elif p['type'] == 'extra_open':
                    lines.append(f'  - 末尾: 多余「 x{p["count"]}\n')
    else:
        lines.append('全部配平 ✅\n')

lines.append(f'\n{"=" * 80}\n')
lines.append(f'总结: {total_imbalanced} 个文件不配平\n')

os.makedirs(os.path.dirname(out_file), exist_ok=True)
with open(out_file, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f'Audit complete: {total_imbalanced} imbalanced files, report at {out_file}')