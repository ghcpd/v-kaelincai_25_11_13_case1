#!/usr/bin/env bash
set -e
ROOT_DIR=$(cd "$(dirname "$0")"; pwd -P)
cd "$ROOT_DIR"
python -m venv .venv
. .venv/Scripts/activate; pip install -r requirements.txt

# run tests
pytest -q --maxfail=1 --oldest-first > test_report_post.txt || true

# copy outputs
if [ -f results/results_post.json ]; then
    cp results/results_post.json results_post.json
fi
cp logs/log_post.txt log_post.txt || true

echo "Done project B tests. See results and logs."
