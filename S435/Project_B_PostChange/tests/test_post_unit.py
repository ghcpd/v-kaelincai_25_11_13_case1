import json
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src import service_post as sp


def test_config_flags():
    # Validate defaults
    assert isinstance(sp.FEATURE_USE_V2, bool)


def test_persist_and_lookup(tmp_path):
    order_id = 'UT-1'
    rec = {'status': 'pending', 'transactionId': 'TT-1', 'fraudScore': 10}
    sp.persist_record(order_id, rec)
    found = sp.get_record_by_transaction('TT-1')
    assert found is not None
    assert found[0] == order_id


def test_fallback_to_v1(monkeypatch):
    # Simulate v1 success
    class DummyResp:
        def __init__(self, status, json_data):
            self.status_code = status
            self._json = json_data
        def json(self):
            return self._json
    def fake_post(url, json=None, timeout=None):
        return DummyResp(200, {'success': True, 'transactionId': 'V1-T-123'})
    monkeypatch.setattr(sp, 'requests', sp.requests)
    monkeypatch.setattr(sp.requests, 'post', fake_post)
    res = sp.fallback_to_v1('UT-2', 100, 'card')
    # Ensure fallback records created
    rec = sp.get_record_by_transaction('V1-T-123')
    assert rec is not None


def test_webhook_idempotency(monkeypatch):
    # Create initial record
    order_id = 'UT-3'
    sp.persist_record(order_id, {'status': 'pending', 'transactionId': 'TT-100', 'fraudScore': 10})
    # Send first webhook
    from src.service_post import app
    client = app.test_client()
    headers = {'X-Webhook-Signature': sp.WEBHOOK_SECRET}
    payload = {'transactionId': 'TT-100', 'status': 'authorized', 'fraudScore': 3}
    resp = client.post('/webhook/payments', json=payload, headers=headers)
    assert resp.status_code == 200
    # Send duplicate webhook
    resp2 = client.post('/webhook/payments', json=payload, headers=headers)
    assert resp2.status_code == 200
    # Ensure record is authorized
    rec = sp.get_record_by_transaction('TT-100')
    assert rec is not None
    assert rec[1]['status'] == 'authorized'
