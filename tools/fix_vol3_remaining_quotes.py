"""Fix Vol 3 curved quotes: convert only clear dialogue boundaries"""
with open('output/corrected_第3卷.txt', 'r', encoding='utf-8') as f:
    text = list(f.read())

conversions = {
    47339: '\u300c',   # " -> 「 (dialogue opener at line start)
    75869: '\u300c',   # " -> 「 (dialogue opener at line start)
    103306: '\u300c',  # " -> 「 (dialogue opener)
    113097: '\u300d',  # " -> 」 (dialogue closer)
    46499: '\u300d',   # " -> 」 (dialogue closer)
}

applied = []
for off, new_char in sorted(conversions.items()):
    old_char = text[off]
    text[off] = new_char
    applied.append((off, old_char, new_char))

result = ''.join(text)

with open('output/corrected_第3卷.txt', 'w', encoding='utf-8') as f:
    f.write(result)

for off, old, new in applied:
    print('  offset %d: %s -> %s' % (off, repr(old), repr(new)))

nl = result.count('\u300c')
nr = result.count('\u300d')
print('Vol 3: %d/%d (was 1183/1183)' % (nl, nr))
print('Gap vs answer 1215/1215: %+d/%+d' % (1215-nl, 1215-nr))
print('Remaining \u201c=%d \u201d=%d' % (result.count('\u201c'), result.count('\u201d')))

# Check cumulative balance
cum_l = cum_r = 0
for i, p in enumerate(result.split('\n')):
    cum_l += p.count('\u300c')
    cum_r += p.count('\u300d')
    if cum_l != cum_r:
        print('IMBALANCE at para %d: cum %d/%d diff=%+d' % (i, cum_l, cum_r, cum_l-cum_r))
        print('  -> %s' % p[:80].replace('\n',' '))
        break