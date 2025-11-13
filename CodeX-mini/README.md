# Evaluation of Prime, Secondary, Haiku, and gpt-5-mini on Feature & improvement — API change

## Scenario & Contract
The legacy settlement service (`Project_A_PreChange`) calls `POST /api/v1/charge` with minimal payload:

```
v1 request:
{
  "orderId": "O123",
  "amount": 1000,
  "paymentMethod": "card"
}

v1 response:
{
  "success": true
}
```

The migrated service (`Project_B_PostChange`) calls `POST /api/v2/payments/authorize` and validates the richer contract:

```
v2 request:
{
  "orderId": "O123",
  "amount": 1000,
  "currency": "USD",
  "countryCode": "US",
  "paymentMethod": "card",
  "3DS_token": null
}

v2 sync response:
{
  "transactionId": "T567",
  "fraudScore": 12,
  "requiresAuth": false,
  "status": "authorized"
}

v2 async response:
{
  "transactionId": "T890",
  "requiresAuth": true,
  "status": "pending_auth"
}

Webhook POST `/webhook/payments`:
{
  "transactionId": "T890",
  "status": "authorized",
  "fraudScore": 8
}
```

### Acceptance Criteria

- Project B issues `/api/v2/payments/authorize` calls with the enriched payload and validates required fields.
- The migrated service records `transactionId`, `fraudScore`, and `requiresAuth` responses, updating internal status via webhook confirmations.
- `requiresAuth` and asynchronous paths complete after webhook events while keeping idempotent semantics.
- Fallback to v1 is feature-flagged (`FEATURE_FLAG_USE_V2`) and triggers when v2 is unavailable or error-prone.
- All canonical tests in `test_data.json` pass, and generated logs/results capture the expected side-effects (calls, retries, webhook receipts).

## Setup & Execution

### Per-project
- `Project_A_PreChange/setup.sh` installs the Flask-based legacy service dependencies.
- `Project_B_PostChange/setup.sh` prepares the v2-aware service, adapter, and webhook listener.

Each project can be tested with:

```
bash Project_A_PreChange/run_tests.sh
bash Project_B_PostChange/run_tests.sh
```

### Master workflow

```
bash run_all.sh
```

`run_all.sh` runs both suites sequentially, copies each `results_*.json` to `results/`, records webhook events, populates `results/aggregated_metrics.json`, and writes `compare_report.md`.

## Environment Variables & Feature Flags

- `PAYMENT_API_BASE_URL`: v2 mock endpoint (default `http://localhost:6001` for Project B).
- `LEGACY_PAYMENT_API_BASE_URL`: legacy mock endpoint (`http://localhost:5001` or `5101` depending on project).
- `FEATURE_FLAG_USE_V2`: `true` enables v2 path; flip to `false` to force fallback.
- `FALLBACK_ENABLED`: `true` allows fallback to `/api/v1/charge` when v2 is down.
- `WEBHOOK_SECRET`: shared secret for validating `/webhook/payments`.
- `SETTLEMENT_PORT`: port where the settlement service listens (`5002`/`6102` by default).
- `PAYMENT_TIMEOUT`, `PAYMENT_RETRY_COUNT`: control timeouts/retries shown in tests.
- `LOG_FILE`: override log target per service.

To simulate webhooks manually, `POST` to `http://localhost:<service-port>/webhook/payments` with header `X-Webhook-Secret: <WEBHOOK_SECRET>` and payload matching the canonical webhook body.

## Test Data & Validation

Shared canonical cases are in `test_data.json` (also copied to `Project_A_PreChange/data/test_data.json`). Each entry defines:

| Test ID | Validates |
| --- | --- |
| `sync_authorized_v2` | Payload transformation, fraud/final-status mapping for synchronous v2 success. |
| `3ds_required_flow` | RequiresAuth logic, webhook confirmation, idempotent handler. |
| `async_confirmation` | Async pending + webhook completion without 3DS. |
| `v2_timeout_fallback` | Timeout/server-error fallback path to v1, retries, default statuses. |
| `fraud_decline` | High fraud score/decline logging and status propagation. |

Project B also saves per-case expectations in `Project_B_PostChange/data/expected_postchange.json`.

## Logs, Results & Artifacts

- `Project_A_PreChange/logs/log_pre.txt` / `Project_B_PostChange/logs/log_post.txt`: settlement logs with masked sensitive fields; 3DS tokens are not recorded to protect privacy.
- `Project_A_PreChange/results/results_pre.json` & `Project_B_PostChange/results/results_post.json`: machine-readable outcomes with `test_id`, input, upstream calls, retries, webhook receipts, and final statuses.
- `Project_B_PostChange/results/webhook_event_log.json`: captures all webhook payloads processed for audit.
- Root `results/` stores aggregated `results_pre.json`, `results_post.json`, `aggregated_metrics.json`, `webhook_event_log.json`, and `compare_report.md`.

## Observability & Side-effects

- Every upstream call is logged (with `orderId` and outcome) to build an audit trail.
- The migrated service stores the richer `transactionId`, `fraudScore`, and webhook flags in its in-memory records, exposed via `/records`.
- `results_*.json` include `calls_to_upstream`, enabling tracing and comparing retries or fallback triggers.
- Both e2e suites start mock upstreams and the settlement service inside `pytest`, so the recorded `results_*.json` contain a faithful trace of HTTP calls, webhook receipts, and stored states.

## Pitfalls & Mitigations

1. **Idempotency** — Webhook handler checks if a transaction is already confirmed and ignores duplicates.
2. **Race conditions** — Async flows poll `/records/<orderId>` until the expected state arrives; new entries update `lastUpdated` timestamps to signal liveness.
3. **Webhook security** — Every webhook request must include `X-Webhook-Secret`; the shared secret should be rotated and kept out of logs.
4. **Time window for final confirmation** — The service treats statuses other than `authorized`/`declined` as pending, leaving the record open until the webhook or a retry updates it.
5. **Sensitive data exposure** — 3DS tokens are not logged; logs and telemetry only store `orderId`, `transactionId`, and fraud results.
6. **Observability and correlation** — Use `orderId` + `transactionId` pairs for tracing, and log upstream errors with contextual metadata.
7. **Robustness** — Circuit breakers/retries use `PAYMENT_RETRY_COUNT` and `PAYMENT_TIMEOUT` with exponential backoff patterns; fallback to v1 ensures continuity.
8. **Canary rollout strategy** — Gate `FEATURE_FLAG_USE_V2`, deploy to a small percentage first, and monitor fraudScore/timeouts before full rollout.

## Limitations

- Mocks approximate v1 and v2 behaviors and cannot replace production regression suites; real gateway testing is required for network resilience and slipstream 3DS flows.
- The 3DS redirect interaction is simulated via webhook events — actual user-driven flows must be validated in staging with real payment providers.
- Webhook timing and retries are simplified; production should adjust webhook retry policies and use queueing systems to smooth bursts.

## Next Steps

1. Review `results/compare_report.md` after running `bash run_all.sh` for functional parity insights.
2. Inspect `aggregated_metrics.json` to validate latency and webhook volumes compared to previous runs.
3. Toggle `FEATURE_FLAG_USE_V2` and `FALLBACK_ENABLED` as needed during rollout, rerun `run_tests.sh`, and refresh `compare_report.md`.
