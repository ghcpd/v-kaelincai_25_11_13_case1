#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p logs results
rm -f results/results_pre.json

pytest tests/test_pre_unit.py tests/test_pre_e2e.py | tee logs/run_pre.log
