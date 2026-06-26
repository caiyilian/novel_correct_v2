"""Stage 6b: Fix small volumes (5,7,8,9,10) missing dialogues"""
import sys, io; sys.path.insert(0, '.'); sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from src.io.loader import TextLoader
import re

volumes = [5, 7, 8, 9, 10]
total_missing = 0

for v in volumes:
    corr_path = 'output/corrected_第%d卷.txt' % v
    ans_path = 'data/answer/answer_第%d卷.txt' % v
    
    corr = TextLoader().load(corr_path).text
    ans = TextLoader().load(ans_path).text
    
    # Extract dialogue pairs
    corr_dlgs = set(re.findall(r'\u300c[^\u300c\u300d]*\u300d', corr))
    ans_dlgs = set(re.findall(r'\u300c[^\u300c\u300d]*\u300d', ans))
    
    # Reduce noise: normalize common variants
    def norm(s):
        return s.replace('·','•').replace('著','着').replace('吶','呐').replace('──','——').replace('─','—')
    
    corr_norm = set(norm(d) for d in corr_dlgs)
    ans_norm = set(norm(d) for d in ans_dlgs)
    
    # Find truly missing (after normalization)
    missing = ans_norm - corr_norm
    
    # Also count: how many normalized dialogues in ans vs corr
    corr_gross = len(corr_dlgs)
    ans_gross = len(ans_dlgs)
    # The "real" gap is the difference in total count, even when many match
    # after normalization, some answer dialogues are completely missing
    
    print("Vol %d: corr=%d dialogues, ans=%d" % (v, corr_gross, ans_gross))
    print("  Gap(totals): %d" % (ans_gross - corr_gross))
    # Truly missing after normalization:
    print("  Truly unmatched after normalization: %d" % len(missing))
    total_missing += len(missing)
    if missing and len(missing) <= 15:
        for d in sorted(missing):
            print("    「%s」" % d[:60])
    print()

print("Total truly missing after normalization: %d" % total_missing)