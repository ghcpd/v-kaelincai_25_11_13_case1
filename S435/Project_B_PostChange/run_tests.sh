#!/usr/bin/env bash
set -e
python -m venv .venv || true
. .venv/bin/activate || true
pip install -r requirements.txt
mkdir -p results logs
# Set env for mocks and services
export MOCK_V2_PORT=6001
export MOCK_V1_PORT=5001
export SERVICE_PORT=6000
export PAYMENT_API_BASE_URL=http://localhost:$MOCK_V2_PORT
export FEATURE_FLAG_USE_V2=true
export WEBHOOK_SECRET=secret
pytest -q tests/test_post_e2e.py -q || true
