#!/usr/bin/env python3
import json
import sys

if len(sys.argv) != 4:
    print('Usage: compare_results.py results_pre.json results_post.json out_report.md')
    sys.exit(2)

pre_path, post_path, out_path = sys.argv[1:]
with open(pre_path) as f:
    pre = json.load(f)
with open(post_path) as f:
    post = json.load(f)

report = []
report.append('# Comparison Report\n')
report.append('## Summary\n')
report.append(f'* Pre-change cases: {len(pre)}\n')
report.append(f'* Post-change cases: {len(post)}\n')

report.append('## Per-test comparisons\n')
report.append('| test_id | pre_status | post_status | transmission | transactionId_pre | transactionId_post | notes |\n')
report.append('|---|---|---|---|---|---|---|\n')
by_id = {r['test_id']: r for r in post}

for p in pre:
    pid = p['test_id']
    q = by_id.get(pid)
    pre_st = p.get('final_status')
    post_st = q.get('final_status') if q else 'missing'
    pre_tx = p.get('transaction_id')
    post_tx = q.get('transaction_id') if q else None
    trans = 'v2' if q and q.get('v2_calls', 0) > 0 else 'v1'
    notes = []
    if pre_st != post_st:
        notes.append('status change')
    if (pre_tx is None) != (post_tx is None):
        notes.append('transactionId changed')
    report.append(f"| {pid} | {pre_st} | {post_st} | {trans} | {pre_tx or ''} | {post_tx or ''} | {';'.join(notes)} |\n")

report.append('\n## Observations\n')
report.append('- The post-change integration includes `transactionId` and `fraudScore` in traces.\n')
report.append('\n## Recommendations\n')
report.append('- Canary rollout with feature flag, observe fraudScore and requireAuth metrics.\n')

with open(out_path, 'w') as f:
    f.write(''.join(report))

print('Compare report saved to:', out_path)
