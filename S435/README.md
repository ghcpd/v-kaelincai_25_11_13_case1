# API Migration: v1 -> v2 Payments Migration Test Harness

This repo contains two projects demonstrating a migration from POST /api/v1/charge to POST /api/v2/payments/authorize with async webhook support.

- Project_A_PreChange — legacy integration (v1)
- Project_B_PostChange — migrated integration (v2) with adapter and webhook handling

Run tests:
- Ensure Python 3.10+ is installed.
- Run `./run_all.sh` to execute both projects' tests and create comparison report in `compare_report.md`.

Configuration:
- Set `PAYMENT_API_BASE_URL` to point to mock upstream servers.
- `FEATURE_FLAG_USE_V2` toggles v2 usage in `service_post.py`.
- `WEBHOOK_SECRET` sets the expected webhook signature.

Outputs:
- results_pre.json and results_post.json — machine-readable per-test results
- compare_report.md — per-test comparison

Notes: For Windows PowerShell, use `bash` or adapt the scripts to PowerShell equivalents.
