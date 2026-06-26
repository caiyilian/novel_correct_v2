import json
r = json.load(open('output/apply_report_第3卷_stage3c.json', encoding='utf-8'))
for o in r['operations']:
    if o['status'] == 'rolled_back':
        print("idx=%s reason=%s" % (o['candidate_index'], str(o.get('reason',''))[:100]))
