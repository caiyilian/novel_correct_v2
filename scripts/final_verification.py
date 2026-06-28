import os, glob
data_dir = r'data'
dirs = sorted([d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))])
total_l = total_r = 0
all_ok = True
report = []
report.append('# 全卷「」配平终验报告\n')
report.append(f'验时间: 2026-06-28\n')
report.append('=' * 80 + '\n')
report.append(f'{"系列":<30} {"文件":<40} {"「":>8} {"」":>8} {"差":>6} {"状态":>8}\n')
report.append('-' * 80 + '\n')
for d in dirs:
    base = os.path.join(data_dir, d)
    files = sorted(glob.glob(os.path.join(base, '*.txt')))
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
        total_l += l
        total_r += r
        status = 'OK' if l == r else f'IMBA({l-r:+d})'
        if l != r:
            all_ok = False
        report.append(f'{d:<28} {os.path.basename(fp):<38} {l:>8} {r:>8} {l-r:>+6} {status:>8}\n')

report.append('\n' + '=' * 80 + '\n')
report.append(f'总计: {total_l}/{total_r} diff={total_l-total_r}\n')
if all_ok:
    report.append('全部配平 ✅\n')
else:
    report.append('仍有文件未配平 ❌\n')

os.makedirs('output', exist_ok=True)
with open('output/final_verification_report.txt', 'w', encoding='utf-8') as f:
    f.writelines(report)

print('Final verification report written to output/final_verification_report.txt')
print(f'Total: {total_l}/{total_r} diff={total_l-total_r}')
print(f'All OK: {all_ok}')
