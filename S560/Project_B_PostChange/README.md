# Project B — PostChange (v2 Integration & Adapter)

This project implements the migrated settlement service calling POST /api/v2/payments/authorize with fallback to v1.

Usage:
- Setup: ./setup.sh
- Run e2e tests: ./run_tests.sh
- Service entrypoint: src/service_post.py
- Mocks: mocks/mock_v2.py and mocks/mock_v1.py

Environment variables:
- PAYMENT_API_BASE_URL — base URL for the v2 API (default: http://localhost:9001)
- PAYMENT_API_V1_BASE_URL — base URL for v1 fallback (defaults to PAYMENT_API_BASE_URL)
- FEATURE_FLAG_USE_V2 — true/false to toggle use of v2
- LOG_FILE — path for logs
- RESULTS_FILE — path for storage file used by service
- WEBHOOK_SECRET — secret header for webhook validation

Outputs:
- tests write `results/results_post.json` with aggregated test entries
- service writes `results/storage_post.json` with stored settlements
- logs/log_post.txt contains logs of outgoing calls and events
