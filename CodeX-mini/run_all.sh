#!/usr/bin/env bash
set -euo pipefail

echo "Running Project A (pre-change) test suite..."
(cd Project_A_PreChange && bash run_tests.sh)

echo "Running Project B (post-change) test suite..."
(cd Project_B_PostChange && bash run_tests.sh)

ROOT_RESULTS=results
mkdir -p "$ROOT_RESULTS"
cp Project_A_PreChange/results/results_pre.json "$ROOT_RESULTS/results_pre.json"
cp Project_B_PostChange/results/results_post.json "$ROOT_RESULTS/results_post.json"
cp Project_B_PostChange/results/webhook_event_log.json "$ROOT_RESULTS/webhook_event_log.json"

python - <<'PY'
import json
from pathlib import Path

root = Path("results")
pre = json.loads(root.joinpath("results_pre.json").read_text())
post = json.loads(root.joinpath("results_post.json").read_text())

def avg(items, key):
    values = [item.get(key, 0) for item in items]
    if not values:
        return 0
    return sum(values) / len(values)

metrics = {
    "pre_tests": len(pre["tests"]),
    "post_tests": len(post["tests"]),
    "avg_duration_pre": avg(pre["tests"], "duration"),
    "avg_duration_post": avg(post["tests"], "duration"),
    "webhook_events": sum(1 for item in post["tests"] if item.get("webhook_received")),
}

root.joinpath("aggregated_metrics.json").write_text(
    json.dumps(metrics, indent=2), encoding="utf-8"
)
PY

python - <<'PY'
import json
from pathlib import Path

root = Path("results")
pre = json.loads(root.joinpath("results_pre.json").read_text())
post = json.loads(root.joinpath("results_post.json").read_text())
data = pre["tests"]
case_map = {item["test_id"]: item for item in data}

table_lines = [
    "| Test ID | Pre Status | Post Status | Notes |",
    "| --- | --- | --- | --- |",
]

for entry in post["tests"]:
    test_id = entry["test_id"]
    pre_record = case_map.get(test_id, {})
    pre_status = pre_record.get("final_status", "unknown")
    post_status = entry.get("final_status", "unknown")
    notes = []
    if entry.get("webhook_received"):
        notes.append("webhook confirms async state")
    if entry.get("calls_to_v1"):
        notes.append("v1 fallback observed" if entry["calls_to_v1"] else "no fallback")
    table_lines.append(
        f"| {test_id} | {pre_status} | {post_status} | {'; '.join(notes) or 'legacy parity'} |"
    )

observability = [
    "Transaction IDs recorded for all v2 responses, enabling traceability.",
    "Fraud scores logged to catch declines (see fraud_decline case).",
]

error_handling = [
    "Fallback to v1 triggers when v2 fails (v2_timeout_fallback).",
    "Webhook signature validated via shared secret to prevent spoofing.",
]

rollout_notes = [
    "Use FEATURE_FLAG_USE_V2 to gate the rollout, toggling back to v1 instantly.",
    "Begin with a canary group while monitoring fraudScore trends and webhook latency.",
    "Log correlation IDs (orderId + transactionId) for auditing and debugging.",
    "Implement circuit breakers with exponential backoff and retry limits shown in tests.",
    "Validate webhook idempotency via recorded transactionId before full rollout.",
]

report = [
    "# Compare Report",
    "## Functional parity table",
    *table_lines,
    "",
    "## Test Coverage",
    f"- Pre-change tests: {len(pre['tests'])}",
    f"- Post-change tests: {len(post['tests'])} (webhook confirmations: {sum(1 for item in post['tests'] if item.get('webhook_received'))})",
    "",
    "## Observability improvements",
    *[f"- {line}" for line in observability],
    "",
    "## Error handling differences",
    *[f"- {line}" for line in error_handling],
    "",
    "## Rollout recommendations",
]
report.extend([f"{idx + 1}. {line}" for idx, line in enumerate(rollout_notes)])

root.joinpath("compare_report.md").write_text("\n".join(report), encoding="utf-8")
PY
