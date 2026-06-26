"""Stage 5a: Fix Vol 4 JP quote imbalance (1560/1557)"""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'tools')
from src.io.loader import TextLoader

text = TextLoader().load('output/corrected_第4卷.txt').text
paragraphs = text.split('\n')

# Find where cumulative balance diverges
cum_l = cum_r = 0
imbalance_paras = []
for i, para in enumerate(paragraphs):
    pl = para.count('\u300c')
    pr = para.count('\u300d')
    cum_l += pl
    cum_r += pr
    if cum_l != cum_r:
        imbalance_paras.append((i, cum_l, cum_r, cum_l - cum_r, para[:80]))
    if len(imbalance_paras) >= 10:
        break

print("First imbalance positions:")
for p in imbalance_paras:
    print("  para %d: cum %d/%d diff=%d | %s" % p)

# Check answer target
ans = TextLoader().load('data/answer/answer_第4卷.txt').text
print("\nAnswer target: %d/%d" % (ans.count('\u300c'), ans.count('\u300d')))
print("Current: %d/%d" % (text.count('\u300c'), text.count('\u300d')))
print("Gap: %d left, %d right" % (1561-text.count('\u300c'), 1561-text.count('\u300d')))