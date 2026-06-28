"""Final audit for all majourney files"""
import os

target = r'E:\projects\novel_correct_v2\data\魔女之旅'
files = sorted([f for f in os.listdir(target) if f.endswith('.txt')])

print('魔女之旅全卷「」配平终验')
print('=' * 60)
print(f'{"卷":<26} {"「":>7} {"」":>7} {"差":>5} {"状态":>6}')
print('-' * 60)

total_l = total_r = 0
all_ok = True
for f in files:
    fp = os.path.join(target, f)
    with open(fp, 'rb') as fh:
        raw = fh.read()
    if raw[:2] == b'\xff\xfe':
        text = raw.decode('utf-16-le')
    elif raw[:2] == b'\xfe\xff':
        text = raw.decode('utf-16-be')
    else:
        text = raw.decode('utf-8')
    l = text.count('\u300c')
    r = text.count('\u300d')
    d = l - r
    total_l += l
    total_r += r
    if d == 0:
        status = 'PASS'
    else:
        status = f'FAIL({d:+d})'
        all_ok = False
    print(f'{f:<24} {l:>7} {r:>7} {d:>+5} {status:>6}')

print('-' * 60)
print(f'{"合计":<24} {total_l:>7} {total_r:>7} {total_l-total_r:>5}')
print()
if all_ok:
    print('>>> 全部配平，验收通过！ <<<')
else:
    print('>>> 仍有未配平项，请核查 <<<')

# Also write a report file
report = []
report.append('# 魔女之旅全卷「」配平终验报告\n\n')
report.append(f'审计时间: 2026-06-28\n\n')
report.append('| 卷 | 「 | 」 | 差 | 状态 |\n')
report.append('|---|:---:|:---:|:---:|:---:|\n')
for f in files:
    fp = os.path.join(target, f)
    with open(fp, 'rb') as fh:
        raw = fh.read()
    if raw[:2] == b'\xff\xfe':
        text = raw.decode('utf-16-le')
    elif raw[:2] == b'\xfe\xff':
        text = raw.decode('utf-16-be')
    else:
        text = raw.decode('utf-8')
    l = text.count('\u300c')
    r = text.count('\u300d')
    d = l - r
    status = 'PASS' if d == 0 else f'FAIL({d:+d})'
    name = f.replace('.txt', '')
    report.append(f'| {name} | {l} | {r} | {d:+d} | {status} |\n')
report.append(f'\n| **合计** | **{total_l}** | **{total_r}** | **{total_l-total_r}** | {"✅ 全部配平" if all_ok else "⚠️ 未完全配平"} |\n')

with open(r'E:\projects\novel_correct_v2\output\majourney_final_audit.md', 'w', encoding='utf-8') as fh:
    fh.writelines(report)
print(f'\n报告已写入: E:\projects\novel_correct_v2\output\majourney_final_audit.md')