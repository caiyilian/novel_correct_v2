"""Stage 5b: Fix Vol 6 JP quote imbalance (1200/1199 -> 1202/1202)"""
import sys; sys.path.insert(0, '.')
from src.io.loader import TextLoader

text = TextLoader().load('output/corrected_第6卷.txt').text
ans = TextLoader().load('data/answer/answer_第6卷.txt').text

import re
def extract_dialogues(t):
    return re.findall(r'\u300c[^\u300c\u300d]*\u300d', t)

corr_dlgs = extract_dialogues(text)
ans_dlgs = extract_dialogues(ans)

print("Vol 6: corrected=%d dialogues, answer=%d" % (len(corr_dlgs), len(ans_dlgs)))
print("JP quotes: corrected %d/%d, answer %d/%d" % (
    text.count('\u300c'), text.count('\u300d'),
    ans.count('\u300c'), ans.count('\u300d')))
print("Gap: need +%d left, +%d right" % (
    ans.count('\u300c') - text.count('\u300c'),
    ans.count('\u300d') - text.count('\u300d')))

# Find first imbalance
paras = text.split('\n')
cum_l = cum_r = 0
imbalance_paras = []
for i, para in enumerate(paras):
    pl = para.count('\u300c')
    pr = para.count('\u300d')
    cum_l += pl
    cum_r += pr
    if cum_l != cum_r and len(imbalance_paras) < 10:
        imbalance_paras.append((i, cum_l, cum_r, cum_l-cum_r, para[:80]))
        
print("\nFirst imbalance positions:")
for p in imbalance_paras:
    print("  para %d: cum %d/%d diff=%d | %s" % p)