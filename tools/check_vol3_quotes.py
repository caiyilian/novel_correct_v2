"""Check Vol 3 remaining curved quotes"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('output/corrected_第3卷.txt', 'r', encoding='utf-8') as f:
    text = f.read()

for sym, name in [('\u201c', 'left-double'), ('\u201d', 'right-double'),
                   ('\u2018', 'left-single'), ('\u2019', 'right-single'),
                   ('"', 'straight-double')]:
    positions = [m.start() for m in re.finditer(re.escape(sym), text)]
    print('\n=== %s (%s) found %d times ===' % (repr(sym), name, len(positions)))
    for pos in positions[:10]:
        ctx = text[max(0,pos-50):pos+50].replace('\n', ' ')
        print('  offset %d: ...%s...' % (pos, ctx))