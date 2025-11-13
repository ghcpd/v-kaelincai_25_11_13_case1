# Project B - Post-Change (v2 Integration & Adapter)

This service calls /api/v2/payments/authorize, handles requiresAuth and async webhooks, and falls back to v1 when necessary.

Run tests:
- ./run_tests.sh

Configuration:
- Set PAYMENT_API_BASE_URL to mock v2.
- FEATURE_FLAG_USE_V2=true/false toggles v2 usage.
- WEBHOOK_SECRET sets expected webhook header.

Outputs:
- results/results_post.json
- logs/log_post.txt
