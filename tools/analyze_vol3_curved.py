"""Analyze Vol 3 curved quotes - find ALL positions"""
import re

with open('output/corrected_第3卷.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# \u201c (left double) and \u201d (right double)
ld = [(m.start(), text[max(0,m.start()-50):m.start()+80].replace('\n',' ')) 
      for m in re.finditer('\u201c', text)]
rd = [(m.start(), text[max(0,m.start()-50):m.start()+80].replace('\n',' ')) 
      for m in re.finditer('\u201d', text)]

print('=== LEFT DOUBLE \u201c (%d total) ===' % len(ld))
for off, ctx in ld:
    print('  off %d: ...%s...' % (off, ctx.strip()))

print('\n=== RIGHT DOUBLE \u201d (%d total) ===' % len(rd))
for off, ctx in rd:
    print('  off %d: ...%s...' % (off, ctx.strip()))