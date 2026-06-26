"""Vol 2 Stage 4e convergence verification"""
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'tools')
from src.io.loader import TextLoader
from verify_against_answer import generate_report as vr

text = TextLoader().load('output/corrected_第2卷_stage4d.txt').text
jp_l = text.count('\u300c')
jp_r = text.count('\u300d')
br_l = text.count('[')
br_r = text.count(']')

print("Vol 2 Stage 4d Final:")
print("  JP: %d/%d balanced=%s" % (jp_l, jp_r, str(jp_l==jp_r)))
print("  Target: 1425/1425 gap=%d/%d" % (1425-jp_l, 1425-jp_r))
print("  [: %d  ]: %d" % (br_l, br_r))
print("  Non-std: %d" % (br_l+br_r))

v = vr('output/corrected_第2卷_stage4d.txt', 'data/answer/answer_第2卷.txt')
print("  Match rate: %.4f" % v['matching']['match_rate'])
print("  Diff snippets: %d" % v['diff_snippets_count'])
target_met = (jp_l == 1425 and jp_r == 1425 and br_l == 0 and br_r == 0)
print("  Target met: %s" % str(target_met))
print("  Conclusion: NOT_YET_CONVERGED - 72 brackets + 33 imbalance to Stage 8")
