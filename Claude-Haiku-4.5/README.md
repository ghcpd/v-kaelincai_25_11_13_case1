# Payment API Migration - Projects A & B

Complete evaluation framework for API change migrations in payment/settlement flows.

## Overview

This project demonstrates a migration from POST `/api/v1/charge` (minimal fields, simple boolean response) to POST `/api/v2/payments/authorize` (richer fields, complex responses with async webhook support).

### Project Structure

```
├── Project_A_PreChange/          # Legacy v1 integration
│   ├── src/
│   │   └── service_pre.py        # Settlement service calling v1
│   ├── mocks/
│   │   └── mock_v1.py            # Mock v1 API server
│   ├── tests/
│   │   ├── test_pre_unit.py
│   │   └── test_pre_e2e.py
│   ├── logs/
│   ├── results/
│   ├── requirements.txt
│   ├── setup.sh
│   └── run_tests.py
├── Project_B_PostChange/         # v2 integration with fallback
│   ├── src/
│   │   ├── service_post.py       # Settlement service calling v2
│   │   └── adapter.py            # v1/v2 adapter layer
│   ├── mocks/
│   │   └── mock_v2.py            # Mock v2 API server
│   ├── tests/
│   │   ├── test_post_unit.py
│   │   └── test_post_e2e.py
│   ├── logs/
│   ├── results/
│   ├── requirements.txt
│   ├── setup.sh
│   └── run_tests.py
├── test_data.json                # Canonical test cases (5+ scenarios)
├── run_all.py                    # Master orchestration script
├── compare_report.md             # Generated comparison report
└── results/                      # Aggregated results
    ├── results_pre.json
    ├── results_post.json
    ├── aggregated_metrics.json
    └── compare_report.md
```

## Quick Start

### Prerequisites
- Python 3.8+
- pip

### Setup

```bash
# Clone/extract repository
cd c:\c\chatWorkspace

# Install dependencies for both projects
cd Project_A_PreChange
pip install -r requirements.txt

cd ../Project_B_PostChange
pip install -r requirements.txt

cd ..
```

### Run All Tests (Recommended)

```bash
# From repository root
python run_all.py
```

This will:
1. Run Project A unit tests
2. Run Project B unit tests
3. Generate comparison report
4. Aggregate results and metrics

**Expected output**:
- `results/results_pre.json` - Project A results
- `results/results_post.json` - Project B results
- `results/aggregated_metrics.json` - Combined metrics
- `results/compare_report.md` - Analysis and recommendations

### Run Individual Project Tests

```bash
# Project A only
cd Project_A_PreChange
python run_tests.py

# Project B only
cd Project_B_PostChange
python run_tests.py
```

## Test Data & Scenarios

See `test_data.json` for canonical test cases covering:

1. **TEST_001_SYNC_AUTH** - Normal sync authorization (immediate success)
2. **TEST_002_3DS_REQUIRED** - 3DS required flow with webhook confirmation
3. **TEST_003_ASYNC_PENDING** - Async pending status with webhook confirmation
4. **TEST_004_V2_ERROR_FALLBACK** - v2 error triggers fallback to v1
5. **TEST_005_FRAUD_DECLINE** - High fraud score results in decline

### Test Case Structure

```json
{
  "test_id": "TEST_001_SYNC_AUTH",
  "description": "Normal sync authorization...",
  "input": {
    "orderId": "O001",
    "amount": 10000,
    "paymentMethod": "card",
    "currency": "USD",
    "countryCode": "US"
  },
  "mock_v1_config": {
    "status_code": 200,
    "response": {"success": true}
  },
  "mock_v2_config": {
    "status_code": 200,
    "response": {
      "transactionId": "TXN_001_SYNC",
      "fraudScore": 5,
      "requiresAuth": false,
      "status": "authorized"
    },
    "webhook": null
  },
  "expected_outcome": {
    "project_a_status": "success",
    "project_b_status": "authorized",
    "webhook_called": false
  }
}
```

## API Contracts

### v1 API (Legacy)

**Endpoint**: `POST /api/v1/charge`

**Request**:
```json
{
  "orderId": "O123",
  "amount": 1000,
  "paymentMethod": "card"
}
```

**Response**:
```json
{
  "success": true
}
```

### v2 API (New)

**Endpoint**: `POST /api/v2/payments/authorize`

**Request**:
```json
{
  "orderId": "O123",
  "amount": 1000,
  "currency": "USD",
  "countryCode": "US",
  "paymentMethod": "card",
  "3DS_token": null
}
```

**Response (Sync)**:
```json
{
  "transactionId": "TXN567",
  "fraudScore": 12,
  "requiresAuth": false,
  "status": "authorized"
}
```

**Response (Async Pending)**:
```json
{
  "transactionId": "TXN890",
  "fraudScore": 15,
  "requiresAuth": true,
  "status": "pending_auth",
  "authUrl": "https://gateway.example.com/3ds/TXN890"
}
```

**Webhook Event** (async confirmation):
```json
{
  "event": "payment.authorized",
  "transactionId": "TXN890",
  "status": "authorized",
  "fraudScore": 8,
  "timestamp": "2025-11-13T10:30:00Z"
}
```

## Configuration

### Environment Variables

#### Project A & B Common
```bash
TIMEOUT=10                      # Request timeout in seconds
LOG_FILE=logs/log_pre.txt       # Log file path
```

#### Project A Specific
```bash
PAYMENT_API_BASE_URL=http://localhost:5001  # v1 API URL
```

#### Project B Specific
```bash
PAYMENT_API_BASE_URL=http://localhost:5002  # v2 API URL
FEATURE_FLAG_USE_V2=true                    # Enable v2 (true/false)
ALLOW_FALLBACK=true                         # Allow v1 fallback (true/false)
WEBHOOK_SECRET=test-secret                  # Webhook verification secret
```

### Mock Server Configuration

Mock servers expose `/mock/config` endpoint for test configuration:

```bash
# Configure mock v1 to simulate error
curl -X POST http://localhost:5001/mock/config \
  -H "Content-Type: application/json" \
  -d '{
    "delay_ms": 100,
    "status_code": 500,
    "response": {"error": "Server error"},
    "enabled": true
  }'

# Configure mock v2 with webhook
curl -X POST http://localhost:5002/mock/config \
  -H "Content-Type: application/json" \
  -d '{
    "delay_ms": 150,
    "status_code": 200,
    "response": {
      "transactionId": "TXN123",
      "fraudScore": 10,
      "requiresAuth": false,
      "status": "authorized"
    },
    "webhook": {
      "delay_ms": 2000,
      "event": "payment.authorized",
      "data": {
        "status": "authorized",
        "fraudScore": 8
      }
    },
    "enabled": true
  }'
```

## Feature Flags & Rollout

### Canary Deployment Strategy

```bash
# Phase 1: Disable v2 (v1 only)
export FEATURE_FLAG_USE_V2=false
export ALLOW_FALLBACK=true

# Phase 2: Enable v2 with fallback (5% traffic)
export FEATURE_FLAG_USE_V2=true
export ALLOW_FALLBACK=true

# Phase 3: Enable v2, limited fallback (50% traffic)
# Keep ALLOW_FALLBACK=true but monitor fallback rate

# Phase 4: Full v2 migration (100% traffic)
# Can set ALLOW_FALLBACK=false after stable period
```

### Monitoring Fallback Rate

The adapter logs all fallback activations:

```bash
grep "Falling back to v1" logs/log_post.txt | wc -l
```

Expected targets:
- Week 1: 0-2% fallback rate
- Week 2: < 1% fallback rate
- Week 3+: < 0.1% fallback rate

## Webhook Handling

### Webhook Flow (Async Payments)

1. Settlement service calls v2 API
2. v2 returns `status: "pending_auth"` or `"pending_confirmation"`
3. v2 sends async webhook to `POST /webhook/payments` (service)
4. Service updates settlement record with final status
5. Idempotency check prevents duplicate processing

### Webhook Security

- Signature verification using `X-Webhook-Signature` header
- Webhook event ID deduplication
- Timestamp validation

### Testing Webhooks

```bash
# Simulate webhook manually (for testing)
curl -X POST http://localhost:5011/webhook/payments \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: test-signature" \
  -d '{
    "transactionId": "TXN123",
    "status": "authorized",
    "fraudScore": 8,
    "timestamp": "2025-11-13T10:30:00Z"
  }'
```

## Running Services Manually

Useful for debugging and integration testing:

```bash
# Terminal 1: Mock v1
cd Project_A_PreChange/mocks
python mock_v1.py
# Listens on http://localhost:5001

# Terminal 2: Mock v2
cd Project_B_PostChange/mocks
python mock_v2.py
# Listens on http://localhost:5002

# Terminal 3: Service (Project A)
cd Project_A_PreChange/src
python service_pre.py
# Listens on http://localhost:5010

# Terminal 4: Service (Project B)
cd Project_B_PostChange/src
export FEATURE_FLAG_USE_V2=true
python service_post.py
# Listens on http://localhost:5011

# Terminal 5: Test client
curl -X POST http://localhost:5010/api/settle \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "O001",
    "amount": 10000,
    "paymentMethod": "card"
  }'
```

## Test Results

### Results Files

- `results/results_pre.json` - Project A test results
- `results/results_post.json` - Project B test results
- `results/aggregated_metrics.json` - Combined metrics

### Sample Results

```json
{
  "project": "Project_B_PostChange",
  "start_time": "2025-11-13T10:00:00.000000",
  "tests": {
    "unit": {
      "passed": true,
      "timestamp": "2025-11-13T10:00:15.000000"
    },
    "e2e": {
      "passed": true,
      "timestamp": "2025-11-13T10:01:30.000000"
    }
  },
  "end_time": "2025-11-13T10:02:00.000000"
}
```

## Logs

All services output structured logs to `logs/` directory:

- `logs/log_pre.txt` - Project A service logs
- `logs/log_post.txt` - Project B service logs
- `logs/mock_v1.log` - Mock v1 API logs
- `logs/mock_v2.log` - Mock v2 API logs

Log format includes timestamps, log level, and structured data.

## Adapter Layer (Project B)

The `adapter.py` module provides:

### PaymentAdapter
- `build_v1_request()` - Transform data to v1 format
- `build_v2_request()` - Transform data to v2 format
- `map_v1_response()` - Normalize v1 response
- `map_v2_response()` - Normalize v2 response
- `map_webhook_response()` - Process webhook events
- `should_fallback()` - Determine fallback eligibility

### IdempotencyManager
- Duplicate request detection
- Result caching
- Cache clearing for testing

### WebhookVerifier
- Transaction state tracking
- Webhook signature verification (simplified)
- Pending transaction registration

## Pitfalls & Mitigations

### 1. Webhook Idempotency
**Problem**: Duplicate webhooks cause duplicate settlements

**Solution**:
```python
# Check if webhook already processed
if settlement.get("webhook_received"):
    return {"status": "ok"}, 200  # Idempotent

# Mark as received atomically
settlement["webhook_received"] = True
settlement["final_status"] = webhook_data["status"]
```

### 2. Race Condition in Async Flow
**Problem**: Polling and webhook both update settlement state

**Solution**:
- Use transactionId as unique key
- Implement optimistic locking with version fields
- Check webhook timestamp vs stored timestamp

### 3. 3DS Token Logging
**Problem**: 3DS tokens logged in plaintext = security risk

**Solution**:
```python
# Never log sensitive fields
logger.info(f"3DS token hash: {hash(token)}")  # NOT the token itself

# Implement field masking
def mask_sensitive(data):
    data_copy = data.copy()
    if "3DS_token" in data_copy:
        data_copy["3DS_token"] = "***MASKED***"
    return data_copy
```

### 4. Webhook Delivery Timeout
**Problem**: Long-pending transactions with no webhook confirmation

**Solution**:
```python
# Set timeout for final confirmation
if pending_since > WEBHOOK_TIMEOUT:
    settlement["status"] = "declined"
    settlement["reason"] = "payment_confirmation_timeout"
    send_notification("Long pending payment", settlement)
```

### 5. Feature Flag Stuck State
**Problem**: Flag in intermediate state causes cascading failures

**Solution**:
- Use centralized feature flag service (LaunchDarkly, Unleash)
- Implement feature flag versioning
- Add alerts for flag state changes
- Require approval for production changes

## Security Considerations

1. **Webhook Verification**: Always verify HMAC-SHA256 signatures
2. **Sensitive Data**: Never log payment methods, 3DS tokens, PCI data
3. **Idempotency Keys**: Use UUID v4 with cryptographic randomness
4. **Rate Limiting**: Implement per-merchant rate limits
5. **Circuit Breaker**: Disable v2 if error rate > threshold
6. **Database Encryption**: Store sensitive transaction data encrypted

## Monitoring & Observability

### Key Metrics

1. **Success Rate**: % of successful authorizations
2. **Fallback Rate**: % triggering v1 fallback
3. **Webhook Delivery Rate**: % of webhooks successfully delivered
4. **Latency**: p50, p95, p99 response times
5. **Fraud Distribution**: Average fraudScore, decline rate

### Recommended Alerts

- Fallback rate > 1% (5-minute window)
- Webhook delivery success < 95% (1-hour window)
- p95 latency > 5s (degradation)
- Error rate > 1% (issues with v2)

## Troubleshooting

### Service Won't Start
```bash
# Check if port is in use
netstat -an | grep 5010  # Project A
netstat -an | grep 5011  # Project B
netstat -an | grep 5001  # Mock v1
netstat -an | grep 5002  # Mock v2

# Kill existing process
kill -9 <PID>

# Or use different ports
export SERVICE_PORT=5010
python src/service_pre.py
```

### Tests Failing
```bash
# Run with verbose output
python -m pytest tests/ -vv -s

# Check logs
tail -f logs/log_pre.txt
tail -f logs/log_post.txt

# Check mock configuration
curl http://localhost:5001/mock/config
curl http://localhost:5002/mock/config
```

### Webhooks Not Delivered
```bash
# Check mock v2 webhook config
curl http://localhost:5002/mock/config | grep webhook

# Set webhook callback URL
curl -X POST http://localhost:5002/mock/webhook-callback \
  -H "Content-Type: application/json" \
  -d '{"callbackUrl": "http://localhost:5011/webhook/payments"}'

# Check service logs for webhook receipt
grep "WEBHOOK" logs/log_post.txt
```

## Production Checklist

- [ ] Feature flag service integrated (LaunchDarkly/Unleash)
- [ ] Webhook signature verification implemented (HMAC-SHA256)
- [ ] Database idempotency tracking added
- [ ] Circuit breaker configured (fallback on 5xx)
- [ ] Monitoring/alerting configured
- [ ] Canary deployment plan documented
- [ ] Rollback procedure tested
- [ ] Webhook retry/exponential backoff implemented
- [ ] Audit logging enabled (no sensitive field logging)
- [ ] Load testing completed (throughput, p99 latency)

## References

- [PCI DSS Compliance](https://www.pcisecuritystandards.org/)
- [Strong Customer Authentication (3DS)](https://en.wikipedia.org/wiki/3-D_Secure)
- [Idempotent APIs](https://stripe.com/blog/idempotency)
- [Webhook Best Practices](https://zapier.com/blog/webhook/)

## Support & Questions

For issues or questions, refer to:
1. `results/compare_report.md` - Detailed analysis
2. `logs/` directory - Service logs
3. Test code in `tests/` - Example usage

---

**Last Updated**: 2025-11-13  
**Framework Version**: 1.0
