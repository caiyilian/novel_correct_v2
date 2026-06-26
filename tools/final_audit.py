"""Stage 7-10: Cross-volume final audit and summary"""
import sys, io; sys.path.insert(0, '.'); sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from src.io.loader import TextLoader

volumes = list(range(1, 11))
total_corr_l = total_corr_r = 0
total_ans_l = total_ans_r = 0
total_bracket_l = total_bracket_r = 0

print("=" * 80)
print("FINAL CROSS-VOLUME AUDIT")
print("=" * 80)
print()
print("%-6s %-18s %-18s %-14s %-12s %s" % (
    "Vol", "Corrected (L/R)", "Answer (L/R)", "Gap (L/R)", "Imbalance", "Brackets []"))
print("-" * 80)

for v in volumes:
    corr = TextLoader().load('output/corrected_第%d卷.txt' % v).text
    ans = TextLoader().load('data/answer/answer_第%d卷.txt' % v).text
    
    c_l = corr.count('\u300c')
    c_r = corr.count('\u300d')
    a_l = ans.count('\u300c')
    a_r = ans.count('\u300d')
    
    b_l = corr.count('[')
    b_r = corr.count(']')
    
    # Check per-paragraph balance
    paras = corr.split('\n')
    imba = 0
    for para in paras:
        if para.count('\u300c') != para.count('\u300d'):
            imba += 1
    
    total_corr_l += c_l
    total_corr_r += c_r
    total_ans_l += a_l
    total_ans_r += a_r
    total_bracket_l += b_l
    total_bracket_r += b_r
    
    status = "BALANCED" if imba == 0 else "IMBALANCE(%d)" % imba
    print("%-6d %04d/%-04d     %04d/%-04d     %+3d/%-+3d   %-12s %d/%d" % (
        v, c_l, c_r, a_l, a_r, a_l-c_l, a_r-c_r, status, b_l, b_r))

print()
print("=" * 80)
print("TOTALS")
print("=" * 80)
print("Corrected JP:      %d / %d" % (total_corr_l, total_corr_r))
print("Answer JP:         %d / %d" % (total_ans_l, total_ans_r))
print("Gap:               %+d / %+d" % (total_ans_l - total_corr_l, total_ans_r - total_corr_r))
print("Brackets []:       %d [" % total_bracket_l + " + %d ]" % total_bracket_r)

# Check original reference
ori = TextLoader().load('data/ori_story/第1卷.txt').text
print("\nOriginal JP in Vol 1: %d" % (ori.count('\u300c') + ori.count('\u300d')))