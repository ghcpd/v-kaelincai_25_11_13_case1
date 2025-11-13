# Payments API Migration Test Harness

This repository contains two projects demonstrating migration from POST /api/v1/charge to POST /api/v2/payments/authorize.

- Project_A_PreChange: Legacy integration using v1
- Project_B_PostChange: Migrated integration using v2 with adapter, webhook, idempotent webhook handling, and fallback strategies

Shared artifacts include canonical test inputs and the orchestration script `run_all.sh` to execute all tests and generate a comparison report in `results/`.

The test harness implements the following test scenarios: v2 sync authorized, 3DS flow with async webhook, async pending with webhook, v2 error fallback to v1, and fraud/decline.

Run everything:

- On a *nix or WSL environment: ./run_all.sh
- On Windows PowerShell: .\run_all.sh or run project scripts individually

Outputs:
- `shared/test_data.json` — canonical input cases
- `results/results_pre.json` and `results/results_post.json` — aggregated machine-readable per-test results
- `results/compare_report.md` — comparison report summarizing the migration behavior

See each project's README for per-project detail and usage.
