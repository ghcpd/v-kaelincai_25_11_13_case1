#!/usr/bin/env bash
set -e
ROOT_DIR=$(cd "$(dirname "$0")"; pwd -P)
cd "$ROOT_DIR"
python -m venv .venv
. .venv/Scripts/activate; pip install -r requirements.txt

# run tests
pytest -q --maxfail=1 --oldest-first > test_report_pre.txt || true

# Gather results (tests write results to results/)
if [ -f results/results_pre.json ]; then
    cp results/results_pre.json results_pre.json
fi

# Save logs
if [ -f logs/log_pre.txt ]; then
    cp logs/log_pre.txt log_pre.txt
fi

echo "Done project A tests. See results and logs."
