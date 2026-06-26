"""Stage 6a-6b: Small volumes (5,7,8,9,10) comprehensive gap audit + fix"""
import sys; sys.path.insert(0, '.')
from src.io.loader import TextLoader
import re

volumes = {
    5: ('output/corrected_第5卷.txt', 'data/answer/answer_第5卷.txt'),
    7: ('output/corrected_第7卷.txt', 'data/answer/answer_第7卷.txt'),
    8: ('output/corrected_第8卷.txt', 'data/answer/answer_第8卷.txt'),
    9: ('output/corrected_第9卷.txt', 'data/answer/answer_第9卷.txt'),
   10: ('output/corrected_第10卷.txt', 'data/answer/answer_第10卷.txt'),
}

results = {}
for v, (corr_path, ans_path) in sorted(volumes.items()):
    text = TextLoader().load(corr_path).text
    ans = TextLoader().load(ans_path).text
    
    c_l = text.count('\u300c')
    c_r = text.count('\u300d')
    a_l = ans.count('\u300c')
    a_r = ans.count('\u300d')
    
    # Find first imbalance
    paras = text.split('\n')
    cum_l = cum_r = 0
    first_imba = None
    for i, para in enumerate(paras):
        pl = para.count('\u300c')
        pr = para.count('\u300d')
        cum_l += pl
        cum_r += pr
        if cum_l != cum_r:
            first_imba = (i, cum_l, cum_r, cum_l-cum_r)
            break
    
    # [] brackets
    c_b = text.count('[') + text.count(']')
    
    results[v] = {
        'corrected': (c_l, c_r),
        'answer': (a_l, a_r),
        'gap': (a_l-c_l, a_r-c_r),
        'first_imba': first_imba,
        'brackets': (text.count('['), text.count(']'))
    }

print("=== Vol 5,7,8,9,10 Gap Audit (Stage 6a) ===\n")
print("%-6s  %-18s  %-18s  %-16s  %s" % ("Vol", "Corrected (L/R)", "Answer (L/R)", "Gap (L/R)", "First Imba"))
print("-" * 80)
for v in sorted(results):
    r = results[v]
    print("%-6d  %-4d/%-4d (%d/%d)  %-4d/%-4d (%d/%d)  %+3d/%-+3d    para %s" % (
        v, r['corrected'][0], r['corrected'][1],
        r['corrected'][0], r['corrected'][1],
        r['answer'][0], r['answer'][1],
        r['answer'][0], r['answer'][1],
        r['gap'][0], r['gap'][1],
        r['first_imba'][0] if r['first_imba'] else 'NONE'))

print("\n[] brackets:")
for v in sorted(results):
    r = results[v]
    print("  Vol %d: %d [ + %d ]" % (v, r['brackets'][0], r['brackets'][1]))

# Summary
total_corr_l = sum(results[v]['corrected'][0] for v in results)
total_corr_r = sum(results[v]['corrected'][1] for v in results)
total_ans_l = sum(results[v]['answer'][0] for v in results)
total_ans_r = sum(results[v]['answer'][1] for v in results)
print("\nVol 5+7+8+9+10 total: corrected %d/%d, answer %d/%d" % (
    total_corr_l, total_corr_r, total_ans_l, total_ans_r))
print("Total gap: %+d left, %+d right" % (total_ans_l-total_corr_l, total_ans_r-total_corr_r))