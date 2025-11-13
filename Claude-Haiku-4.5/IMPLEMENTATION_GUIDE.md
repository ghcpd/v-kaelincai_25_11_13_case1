# Implementation Guide - Payment API Migration

## Overview

This document describes the complete implementation of Project A and Project B for the payment API migration evaluation.

## Architecture

### Project A - Legacy v1 Integration

**Service**: `src/service_pre.py`
- Flask-based settlement service on port 5010
- Calls `POST /api/v1/charge` endpoint
- Minimal request: `{orderId, amount, paymentMethod}`
- Simple response: `{success: boolean}`
- In-memory settlement storage

**Mock API**: `mocks/mock_v1.py`
- Simulates v1 payment gateway on port 5001
- Configurable response delays, status codes, and payloads
- Exposed `/mock/config` endpoint for test configuration
- Logs all incoming requests

### Project B - v2 Integration with Fallback

**Service**: `src/service_post.py`
- Flask-based settlement service on port 5011
- Calls `POST /api/v2/payments/authorize` endpoint (primary)
- Fallback to v1 on errors/timeouts (when configured)
- Handles async webhooks for confirmation
- Richer response: `{transactionId, fraudScore, requiresAuth, status}`
- In-memory settlement storage + webhook state tracking

**Adapter Layer**: `src/adapter.py`
- `PaymentAdapter`: Request/response transformation
- `IdempotencyManager`: Duplicate request detection
- `WebhookVerifier`: Transaction state tracking and webhook validation

**Mock v2 API**: `mocks/mock_v2.py`
- Simulates v2 payment gateway on port 5002
- Supports both sync and async (webhook) responses
- Configurable webhook delivery with delays
- Thread-based async webhook delivery

## Request/Response Transformation

### v1 Request Building
```python
def build_v1_request(order_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "orderId": order_data.get("orderId"),
        "amount": order_data.get("amount"),
        "paymentMethod": order_data.get("paymentMethod")
    }
```

### v2 Request Building
```python
def build_v2_request(order_data: Dict[str, Any]) -> Dict[str, Any]:
    # v2 requires additional fields - raises ValueError if missing
    v2_payload = {
        "orderId": order_data.get("orderId"),
        "amount": order_data.get("amount"),
        "currency": order_data.get("currency", "USD"),  # NEW: required
        "countryCode": order_data.get("countryCode", "US"),  # NEW: required
        "paymentMethod": order_data.get("paymentMethod"),
        "3DS_token": order_data.get("3DS_token")  # NEW: for strong auth
    }
    
    # Validates all required v2 fields present
    required_fields = ["orderId", "amount", "currency", "countryCode", "paymentMethod"]
    missing_fields = [f for f in required_fields if not v2_payload.get(f)]
    
    if missing_fields:
        raise ValueError(f"Missing required v2 fields: {missing_fields}")
    
    return v2_payload
```

## Response Mapping

### v1 Response to Normalized Format
```python
def map_v1_response(v1_response: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "authorized" if v1_response.get("success") else "declined",
        "transactionId": None,        # v1 doesn't provide this
        "fraudScore": None,            # v1 doesn't provide this
        "requiresAuth": False,         # v1 doesn't support 3DS
        "v1_raw": v1_response
    }
```

### v2 Response to Normalized Format
```python
def map_v2_response(v2_response: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": v2_response.get("status", "unknown"),  # authorized/declined/pending_auth/pending_confirmation
        "transactionId": v2_response.get("transactionId"),  # NEW: unique ID
        "fraudScore": v2_response.get("fraudScore"),        # NEW: 0-100 score
        "requiresAuth": v2_response.get("requiresAuth", False),  # NEW: 3DS required?
        "declineReason": v2_response.get("declineReason"),  # NEW: why declined
        "authUrl": v2_response.get("authUrl"),              # NEW: 3DS URL
        "v2_raw": v2_response
    }
```

## Fallback Logic

```python
# In Project B service
if FEATURE_FLAG_USE_V2:
    try:
        v2_result = call_v2_authorize(data, settlement_record)
        # Process v2 response (includes webhook registration if needed)
    except Exception as e:
        if ALLOW_FALLBACK:
            # Fallback to v1
            v1_result = call_v1_charge(data, settlement_record)
            # Return v1 result with "fallback_success" status
        else:
            # Return error
            return error_response(e)
else:
    # Feature flag disabled - use v1 only
    v1_result = call_v1_charge(data, settlement_record)
```

**Fallback Triggers**:
- HTTP 5xx errors from v2
- Connection timeouts
- Network errors
- Feature flag disabled

## Idempotency Implementation

```python
class IdempotencyManager:
    def __init__(self):
        self.processed_keys = {}  # key -> result
    
    def is_duplicate(self, idempotency_key: str) -> bool:
        return idempotency_key in self.processed_keys
    
    def get_cached_result(self, idempotency_key: str):
        return self.processed_keys.get(idempotency_key)
    
    def cache_result(self, idempotency_key: str, result: Dict):
        self.processed_keys[idempotency_key] = result

# Usage in service
if idempotency_manager.is_duplicate(idempotency_key):
    return idempotency_manager.get_cached_result(idempotency_key)

# ... process request ...

idempotency_manager.cache_result(idempotency_key, response)
return response
```

## Webhook Handling

### Async Flow
1. Client calls `POST /api/settle`
2. Service calls v2 with v2 request
3. v2 returns (within 200-500ms):
   - For sync: `{status: "authorized", transactionId: "TXN123"}`
   - For async: `{status: "pending_auth", transactionId: "TXN456"}`
4. If async, service registers with `WebhookVerifier`:
   ```python
   webhook_verifier.register_pending(transaction_id, order_id)
   ```
5. Service returns to client immediately with status
6. v2 sends webhook (after configured delay):
   ```
   POST /webhook/payments
   {
     "transactionId": "TXN456",
     "status": "authorized",
     "fraudScore": 8,
     "event": "payment.authorized",
     "timestamp": "2025-11-13T10:30:00Z"
   }
   ```
7. Service webhook handler updates settlement:
   ```python
   @app.route("/webhook/payments", methods=["POST"])
   def webhook_payment():
       data = request.get_json()
       transaction_id = data.get("transactionId")
       
       # Find settlement by transactionId
       settlement = find_by_transaction_id(transaction_id)
       
       # Idempotency check
       if settlement.get("webhook_received"):
           return {"status": "ok"}, 200
       
       # Update settlement
       settlement["webhook_received"] = True
       settlement["final_status"] = data["status"]
       settlement["final_fraudScore"] = data["fraudScore"]
       settlement["webhook_data"] = data
       
       return {"status": "ok"}, 200
   ```

### Webhook Idempotency
- Check if `webhook_received` flag already set
- Return 200 immediately if duplicate
- Prevents duplicate settlement updates

## Test Coverage

### Unit Tests (test_pre_unit.py, test_post_unit.py)

**Project A**:
- Settlement request structure validation
- v1 request/response contract compliance
- Field mapping and transformation

**Project B**:
- v1 and v2 request building (including validation)
- v1 and v2 response mapping
- Webhook event mapping
- Adapter field transformation
- Idempotency detection and caching
- WebhookVerifier transaction state management
- Webhook confirmation flow

### E2E Tests (test_pre_e2e.py, test_post_e2e.py)

**Project A E2E** (requires manual service startup):
- Sync authorization success
- Error handling for v1 errors

**Project B E2E** (requires manual service startup):
- Sync authorization (immediate success)
- 3DS required with webhook (pending_auth → authorized)
- Async pending with webhook (pending_confirmation → authorized)
- v2 error with v1 fallback
- Fraud score decline

## Logging & Observability

### Log Levels
- `INFO`: Request/response payloads, status changes
- `WARNING`: Duplicate webhooks, unknown transactions
- `ERROR`: API errors, exception details

### Structured Logging
```python
logger.info(f"[SETTLE] Received settlement request: {json.dumps(data)}")
logger.info(f"[SETTLE] Calling v2 API with payload: {json.dumps(v2_payload)}")
logger.info(f"[SETTLE] v2 response: {json.dumps(v2_response)}")
logger.info(f"[SETTLE] Stored settlement record: {json.dumps(settlement_record)}")
```

### Sensitive Data Handling
- Never log full 3DS tokens
- Never log full card numbers
- Never log full payment method details
- Use hashing for idempotency checks on sensitive data

## Test Data Structure

Five canonical test cases in `test_data.json`:

1. **TEST_001_SYNC_AUTH**: Normal sync → authorized
2. **TEST_002_3DS_REQUIRED**: Pending auth → webhook → authorized
3. **TEST_003_ASYNC_PENDING**: Pending confirmation → webhook → authorized
4. **TEST_004_V2_ERROR_FALLBACK**: v2 error → fallback to v1 → success
5. **TEST_005_FRAUD_DECLINE**: High fraud score → declined

Each includes:
- Input request data
- Mock v1 configuration
- Mock v2 configuration
- Expected outcomes for both projects

## Running the Test Suite

### Quick Test (Unit Tests Only)
```bash
cd Project_A_PreChange
python quick_test.py

cd ../Project_B_PostChange
python quick_test.py
```

### Full Test (Unit + E2E)
```bash
python run_all.py
```

This will:
1. Run Project A unit tests
2. Run Project B unit tests
3. Generate comparison report
4. Save results to `results/` directory

## Results Output

### results_pre.json (Project A)
```json
{
  "project": "Project_A_PreChange",
  "start_time": "2025-11-13T10:00:00.000000",
  "tests": {
    "unit": {"passed": true, "timestamp": "..."},
    "e2e": {"passed": false, "timestamp": "..."}
  },
  "end_time": "2025-11-13T10:01:00.000000"
}
```

### results_post.json (Project B)
```json
{
  "project": "Project_B_PostChange",
  "start_time": "2025-11-13T10:01:00.000000",
  "tests": {
    "unit": {"passed": true, "timestamp": "..."},
    "e2e": {"passed": true, "timestamp": "..."}
  },
  "end_time": "2025-11-13T10:02:00.000000"
}
```

### aggregated_metrics.json
```json
{
  "project_a": {"success": true},
  "project_b": {"success": true},
  "test_data_version": "1.0",
  "test_cases_count": 5,
  "start_time": "2025-11-13T10:00:00.000000",
  "end_time": "2025-11-13T10:02:30.000000",
  "duration_seconds": 150.5
}
```

## Potential Improvements for Production

1. **Database Persistence**: Replace in-memory storage with PostgreSQL
2. **Message Queue**: Use Kafka for webhook delivery and retries
3. **Feature Flag Service**: Integrate LaunchDarkly or Unleash
4. **Observability**: Add OpenTelemetry tracing and metrics
5. **Circuit Breaker**: Implement hystrix.js or similar
6. **Webhook Retry**: Add exponential backoff for failed webhooks
7. **Encryption**: Store sensitive data encrypted at rest
8. **Rate Limiting**: Implement per-merchant rate limits
9. **Audit Logging**: Immutable audit trail with PCI compliance
10. **Monitoring**: Prometheus metrics and Grafana dashboards

## Security Checklist

- [ ] 3DS tokens never logged in plaintext
- [ ] Webhook signatures verified (HMAC-SHA256)
- [ ] Idempotency keys use cryptographic randomness
- [ ] Rate limiting on settlement endpoints
- [ ] Circuit breaker on v2 calls
- [ ] Database encryption for PCI data
- [ ] Audit logging for all state changes
- [ ] Sensitive field masking in logs
- [ ] TLS/HTTPS for all API calls
- [ ] Webhook signature verification headers

---

**Last Updated**: 2025-11-13  
**Framework Version**: 1.0
