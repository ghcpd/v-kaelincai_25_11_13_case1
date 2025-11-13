import json
import os

ROOT = os.path.dirname(os.path.dirname(__file__))
PRE = os.path.join(ROOT, 'Project_A_PreChange', 'results', 'results_pre.json')
POST = os.path.join(ROOT, 'Project_B_PostChange', 'results', 'results_post.json')
OUT = os.path.join(ROOT, 'compare_report.md')

def load_results(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        return [json.loads(l) for l in f if l.strip()]

pre = load_results(PRE)
post = load_results(POST)

# Build comparison
rows = []
for p in pre:
    tid = p['test_id']
    matched = next((x for x in post if x['test_id'] == tid), None)
    pre_status = p['final_status'].get('status') if isinstance(p['final_status'], dict) else (p['final_status'] if isinstance(p['final_status'], str) else p['final_status'])
    post_status = None
    post_tid = None
    post_fraud = None
    if matched:
        if isinstance(matched['final_status'], dict):
            post_status = matched['final_status'].get('status')
            post_tid = matched['final_status'].get('transactionId')
            post_fraud = matched['final_status'].get('fraudScore')
        else:
            post_status = matched['final_status']
    rows.append({'test_id': tid, 'pre_status': pre_status, 'post_status': post_status, 'post_tid': post_tid, 'post_fraud': post_fraud, 'post': matched})

with open(OUT, 'w') as f:
    f.write('# Compare Report\n\n')
    f.write('This report compares the pre-change v1 behavior vs post-change v2 behavior across canonical test cases.\n\n')
    f.write('| Test ID | Pre Status | Post Status | TransactionId (post) | FraudScore (post) |\n')
    f.write('|---|---|---|---|---|\n')
    for r in rows:
        f.write(f"| {r['test_id']} | {r['pre_status']} | {r['post_status']} | {r['post_tid'] or ''} | {r['post_fraud'] or ''} |\n")

# Aggregate metrics
metrics = {'pre': {}, 'post': {}}
metrics['pre']['tests'] = len(pre)
metrics['post']['tests'] = len(post)
metrics['post']['authorized'] = sum(1 for r in post if (r['final_status'].get('status') if isinstance(r['final_status'], dict) else r['final_status']) == 'authorized')
metrics['post']['declined'] = sum(1 for r in post if (r['final_status'].get('status') if isinstance(r['final_status'], dict) else r['final_status']) == 'declined')

with open(os.path.join(ROOT, 'results', 'aggregated_metrics.json'), 'w') as mf:
    json.dump(metrics, mf, indent=2)

print('Compare report generated at', OUT)
print('Metrics saved to results/aggregated_metrics.json')
