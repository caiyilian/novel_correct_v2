"""Comprehensive diagnosis: investigate each problematic volume"""
import sys, io, json, re
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from src.io.loader import TextLoader

volumes = {
    2: 'output/corrected_第2卷.txt',
    3: 'output/corrected_第3卷.txt',
    4: 'output/corrected_第4卷.txt',
    5: 'output/corrected_第5卷.txt',
    6: 'output/corrected_第6卷.txt',
    7: 'output/corrected_第7卷.txt',
}

def extract_dialogues(text):
    return re.findall(r'\u300c[^\u300c\u300d]*\u300d', text)

for v, corr_path in sorted(volumes.items()):
    ans_path = 'data/answer/answer_第%d卷.txt' % v
    corr = TextLoader().load(corr_path).text
    ans = TextLoader().load(ans_path).text
    
    c_l = corr.count('\u300c')
    c_r = corr.count('\u300d')
    a_l = ans.count('\u300c')
    a_r = ans.count('\u300d')
    
    corr_dlgs = extract_dialogues(corr)
    ans_dlgs = extract_dialogues(ans)
    
    print("=" * 80)
    print("Vol %d: %d/%d -> answer %d/%d (gap %+d/%+d)" % (
        v, c_l, c_r, a_l, a_r, a_l-c_l, a_r-c_r))
    
    # Count nonstandard symbols
    for sym in ['"', '\u201c', '\u201d', '\u2018', '\u2019', '[', ']', '{', '}']:
        cnt = corr.count(sym)
        if cnt:
            print("  [%s] x %d" % (repr(sym), cnt))
    
    # paragraph imbalance: detailed
    paras = corr.split('\n')
    imba_paras = [(i, p.count('\u300c'), p.count('\u300d'), p[:100]) 
                  for i, p in enumerate(paras) 
                  if p.count('\u300c') != p.count('\u300d')]
    
    print("  Paragraph imbalance: %d / %d total paras" % (len(imba_paras), len(paras)))
    
    if v in [2, 4]:
        # Show sample of imbalance
        print("  Imbalance samples (first 5):")
        for i, lc, rc, preview in imba_paras[:5]:
            diff = lc - rc
            print("    para %d: L=%d R=%d diff=%+d | %s" % (i, lc, rc, diff, preview.replace('\n',' ')[:80]))
    
    # For gap volumes: compare structure
    if v in [3, 5, 6, 7]:
        missing = set(ans_dlgs) - set(corr_dlgs)
        print("  Unmatched answer dialogues (set diff): %d" % len(missing))
        
        # Categorize: how many are "already in text but alignment mismatch"
        already_in_text = 0
        truly_missing = 0
        for md in list(missing)[:30]:
            # Check if content (without brackets) appears anywhere in corr
            content = md[1:-1]  # strip 「」
            # Normalize common variants
            content_norm = content.replace('?', '？').replace('!', '！').replace('...', '……')
            if content[:30] in corr or content_norm[:30] in corr:
                already_in_text += 1
            else:
                truly_missing += 1
        
        print("    - Content already in text (alignment mismatch): ~%d" % already_in_text)
        print("    - Truly missing content: ~%d" % truly_missing)

print()
print("=" * 80)
print("SUMMARY")
print("=" * 80)

# Check Vol 2 imbalance more carefully
print("\n--- Vol 2 paragraph imbalance deep dive ---")
corr2 = TextLoader().load('output/corrected_第2卷.txt').text
paras2 = corr2.split('\n')
imba_types = {}
for i, p in enumerate(paras2):
    lc = p.count('\u300c')
    rc = p.count('\u300d')
    if lc != rc:
        diff = lc - rc
        # Count non-「」 quotes and brackets in these paras
        has_other_quotes = any(s in p for s in ['"', '\u201c', '\u201d', '[', ']', '{', '}', '\u300e', '\u300f'])
        key = 'diff=%+d' % diff
        if has_other_quotes:
            key += '+other_symbols'
        imba_types[key] = imba_types.get(key, 0) + 1

for k, v in sorted(imba_types.items()):
    print("  %s: %d paras" % (k, v))

# Check Vol 4 imbalance
print("\n--- Vol 4 paragraph imbalance deep dive ---")
corr4 = TextLoader().load('output/corrected_第4卷.txt').text
paras4 = corr4.split('\n')
for i, p in enumerate(paras4):
    lc = p.count('\u300c')
    rc = p.count('\u300d')
    if lc != rc:
        print("  para %d: L=%d R=%d diff=%+d | %s" % (
            i, lc, rc, lc-rc, p.replace('\n',' ')[:100]))