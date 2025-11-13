#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p logs results
rm -f results/results_post.json results/webhook_event_log.json

pytest tests/test_post_unit.py tests/test_post_e2e.py | tee logs/run_post.log
