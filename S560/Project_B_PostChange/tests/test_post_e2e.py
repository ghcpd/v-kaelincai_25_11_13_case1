import pytest
import subprocess
import time
import os
import httpx
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DATA_PATH = ROOT.parent / 'shared' / 'test_data.json'
TEST_DATA = json.loads(TEST_DATA_PATH.read_text()) if TEST_DATA_PATH.exists() else []

MOCK_V2_PORT = 9001
MOCK_V1_PORT = 9002
SERVICE_PORT = 9003

@pytest.fixture(scope='session')
def start_mock_v2():
    proc = subprocess.Popen(['python', 'mocks/mock_v2.py'], cwd=str(ROOT))
    time.sleep(0.5)
    yield proc
    proc.kill()

@pytest.fixture(scope='session')
def start_mock_v1():
    proc = subprocess.Popen(['python', 'mocks/mock_v1.py'], cwd=str(ROOT))
    time.sleep(0.5)
    yield proc
    proc.kill()

@pytest.fixture(scope='session')
def start_service():
    env = os.environ.copy()
    env['PAYMENT_API_BASE_URL'] = f'http://localhost:{MOCK_V2_PORT}'
    env['PAYMENT_API_V1_BASE_URL'] = f'http://localhost:{MOCK_V1_PORT}'
    env['FEATURE_FLAG_USE_V2'] = 'true'
    env['LOG_FILE'] = str(ROOT / 'logs' / 'log_post.txt')
    env['RESULTS_FILE'] = str(ROOT / 'results' / 'results_post.json')
    env['WEBHOOK_SECRET'] = 's3cr3t'
    os.makedirs(ROOT / 'logs', exist_ok=True)
    os.makedirs(ROOT / 'results', exist_ok=True)
    proc = subprocess.Popen(['uvicorn', 'src.service_post:app', '--host', '127.0.0.1', '--port', str(SERVICE_PORT)], cwd=str(ROOT), env=env)
    time.sleep(0.5)
    yield proc
    proc.kill()

@pytest.mark.parametrize('case', TEST_DATA)
def test_post_e2e(start_mock_v2, start_mock_v1, start_service, case):
    # configure mock v2
    v2_behavior = case.get('mock_behavior', {}).get('v2_mode', 'sync_authorized')
    delay = case.get('mock_behavior', {}).get('delay_webhook_seconds', 0)
    with httpx.Client(timeout=10.0) as c:
        c.post(f'http://127.0.0.1:{MOCK_V2_PORT}/configure', json={
            'behavior': v2_behavior,
            'delay_webhook_seconds': delay,
            'webhook_url': f'http://127.0.0.1:{SERVICE_PORT}/webhook/payments'
        })
    # configure mock v1 for fallback if necessary
    v1_behavior = case.get('mock_behavior', {}).get('v1_mode', 'sync_authorized')
    with httpx.Client(timeout=5.0) as c:
        c.post(f'http://127.0.0.1:{MOCK_V1_PORT}/configure', json={'behavior': v1_behavior})
    # call settlement service
    input_payload = case['input']
    with httpx.Client(timeout=10.0) as c:
        r = c.post(f'http://127.0.0.1:{SERVICE_PORT}/settle', json=input_payload)
        assert r.status_code == 200
        res = r.json()
    # if asynchronous, wait for webhook and final status
    expected = case['expected_final']
    wait_seconds = 3
    time.sleep(wait_seconds)
    # read the storage written by service
    storage_file = ROOT / 'results' / 'storage_post.json'
    assert storage_file.exists()
    storage = json.loads(storage_file.read_text())
    rec = [r for r in storage if r['orderId'] == input_payload['orderId']]
    assert len(rec) == 1
    rec = rec[0]
    # check expected statuses
    assert rec['status'] == expected['status']
    if expected.get('transactionId_found'):
        assert rec['transaction_id'] is not None
    # derive number of calls from logs
    log_file = ROOT / 'logs' / 'log_post.txt'
    calls_v2 = 0
    calls_v1 = 0
    if log_file.exists():
        lines = log_file.read_text().splitlines()
        calls_v2 = len([l for l in lines if 'OUTGOING_CALL_V2' in l and input_payload['orderId'] in l])
        calls_v1 = len([l for l in lines if 'OUTGOING_CALL_V1' in l and input_payload['orderId'] in l])
    row = {
        'test_id': case['test_id'],
        'input': input_payload,
        'calls_to_upstream': {'v2': calls_v2, 'v1': calls_v1},
        'final_status': rec['status'],
        'transaction_id': rec.get('transaction_id'),
        'webhook_received': rec['status'] != 'pending'
    }
    aggregated_file = ROOT / 'results' / 'results_post.json'
    aggregated = []
    if aggregated_file.exists():
        try:
            aggregated = json.loads(aggregated_file.read_text())
        except Exception:
            aggregated = []
    aggregated.append(row)
    aggregated_file.write_text(json.dumps(aggregated, indent=2))

