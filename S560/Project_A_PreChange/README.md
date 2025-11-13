# Project A — PreChange (Legacy Integration)

This project implements the legacy settlement service calling POST /api/v1/charge.

Usage:
- Setup: ./setup.sh (Linux/Mac) or run via PowerShell on Windows
- Run e2e tests: ./run_tests.sh
- Service entrypoint: src/service_pre.py
- Mocks: mocks/mock_v1.py

Environment variables:
- PAYMENT_API_BASE_URL — base URL of payment upstream (default: http://localhost:8001)
- LOG_FILE — path for logs
- RESULTS_FILE — path for storage file used by the service

Outputs:
- tests write `results/results_pre.json` with aggregated test entries
- service writes `results/storage_pre.json` file with stored settlements
- logs/log_pre.txt contains logs of outgoing calls and events
