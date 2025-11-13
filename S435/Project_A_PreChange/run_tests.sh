#!/usr/bin/env bash
set -e
# Simple runner: start servers and run pytest
python -m venv .venv || true
. .venv/bin/activate || true
pip install -r requirements.txt
mkdir -p results logs
# Export env for mock/service ports
export MOCK_V1_PORT=5001
export SERVICE_PORT=5000
export PAYMENT_API_BASE_URL=http://localhost:$MOCK_V1_PORT
# Run tests
pytest -q tests/test_pre_e2e.py::test_tc1_sync_authorized -q || true
pytest -q tests/test_pre_e2e.py::test_tc4_v2_error_fallback -q || true
# After pytest, results_pre.json should be populated by tests
