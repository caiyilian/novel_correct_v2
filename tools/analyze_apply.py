"""Analyze apply report for Stage 3c"""
import json
r = json.load(open('output/apply_report_第3卷_stage3c.json', encoding='utf-8'))
ops = r['operations']
for o in ops[:5]:
    print(f"idx={o['candidate_index']} status={o['status']} reason={str(o.get('reason',''))[:100]}")
print(f"\nTotal: {len(ops)} ops")
print(f"Applied: {r['applied']}")
print(f"Failed: {r['failed']}")
statuses = {}
for o in ops:
    statuses[o['status']] = statuses.get(o['status'], 0) + 1
print(f"Statuses: {statuses}")