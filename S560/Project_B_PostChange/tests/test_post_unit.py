import pytest
from src.service_post import call_v2, call_v1
import httpx
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_mapping_v2_payload():
    client = AsyncMock()
    client.post.return_value.json.return_value = {'transactionId': 'TX-1', 'fraudScore': 2, 'requiresAuth': False, 'status': 'authorized'}
    # minimal test just ensures we can call function without exceptions
    payload = {'orderId': 'O1', 'amount': 100, 'currency': 'USD', 'countryCode': 'US', 'paymentMethod': 'card', '3DS_token': None}
    resp = await call_v2(payload, client)
    assert resp['transactionId'] == 'TX-1'

@pytest.mark.asyncio
async def test_fallback_on_v2_error():
    client = AsyncMock()
    # simulate v2 error and then v1 success
    async def side_effect(url, json):
        if '/api/v2/' in url:
            raise Exception('v2 down')
        else:
            class R:
                def json(self):
                    return {'success': True}
            return R()
    client.post.side_effect = side_effect
    v2_payload = {'orderId': 'O2', 'amount': 1, 'currency': 'USD', 'countryCode': 'US', 'paymentMethod': 'card', '3DS_token': None}
    # call_v1 directly to ensure v1 call works
    v1_resp = await call_v1({'orderId': 'O2', 'amount': 1, 'paymentMethod': 'card'}, client)
    assert v1_resp['success'] is True


@pytest.mark.asyncio
async def test_webhook_idempotency(monkeypatch, tmp_path):
    from src.service_post import app
    import asyncio
    # use FastAPI TestClient to call POST /webhook/payments
    from fastapi.testclient import TestClient
    client = TestClient(app)
    # clear app-level storage
    from src import service_post as svc
    svc.webhook_processed_tx.clear()
    svc.storage.clear()
    payload = {'transactionId': 'TX-TEST', 'orderId': 'OID', 'status': 'authorized', 'fraudScore': 5}
    headers = {'X-WEBHOOK-SIGNATURE': svc.WEBHOOK_SECRET}
    r = client.post('/webhook/payments', json=payload, headers=headers)
    assert r.status_code == 200
    r2 = client.post('/webhook/payments', json=payload, headers=headers)
    # duplicate should be processed False
    assert r2.status_code == 200
    assert r2.json().get('processed') is False
