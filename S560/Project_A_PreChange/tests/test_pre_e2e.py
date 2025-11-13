import pytest
import subprocess
import time
import os
import httpx
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DATA_PATH = Path(__file__).resolve().parent.parent.parent / 'shared' / 'test_data.json'
TEST_DATA = json.loads(TEST_DATA_PATH.read_text()) if TEST_DATA_PATH.exists() else []

MOCK_V1_PORT = 8001
SERVICE_PORT = 8003

@pytest.fixture(scope='session')
def start_mock_v1():
    proc = subprocess.Popen(['python', 'mocks/mock_v1.py'], cwd=str(ROOT))
    time.sleep(0.5)
    yield proc
    proc.kill()

@pytest.fixture(scope='session')
def start_service():
    env = os.environ.copy()
    env['PAYMENT_API_BASE_URL'] = f'http://localhost:{MOCK_V1_PORT}'
    env['LOG_FILE'] = str(ROOT / 'logs' / 'log_pre.txt')
    env['RESULTS_FILE'] = str(ROOT / 'results' / 'results_pre.json')
    os.makedirs(ROOT / 'logs', exist_ok=True)
    os.makedirs(ROOT / 'results', exist_ok=True)
    proc = subprocess.Popen(['uvicorn', 'src.service_pre:app', '--host', '127.0.0.1', '--port', str(SERVICE_PORT)], cwd=str(ROOT), env=env)
    time.sleep(0.5)
    yield proc
    proc.kill()

@pytest.mark.parametrize('case', TEST_DATA)
def test_pre_e2e(start_mock_v1, start_service, case):
    # configure mock v1 with desired behavior
    behavior = case.get('mock_behavior', {}).get('v1_mode', 'sync_authorized')
    with httpx.Client(timeout=5.0) as c:
        c.post(f'http://127.0.0.1:{MOCK_V1_PORT}/configure', json={'behavior': behavior})
    # call settlement service
    input_payload = case['input']
    with httpx.Client(timeout=5.0) as c:
        r = c.post(f'http://127.0.0.1:{SERVICE_PORT}/settle', json=input_payload)
        assert r.status_code == 200
        res = r.json()
    # Wait short while for internal processing
    time.sleep(0.2)
    # read results
    results_file = PATH_RESULTS = ROOT / 'results' / 'results_pre.json'
    assert results_file.exists()
    results = json.loads(results_file.read_text())
    # assert final state
    # find matching record by orderId
    rec = [r for r in results if r['orderId'] == input_payload['orderId']]
    assert len(rec) == 1
    rec = rec[0]
    expected_status = case['expected_final'].get('status')
    assert rec['status'] == expected_status
    # produce machine-readable row for this test
    # parse logs to count outbound calls for that order
    log_file = ROOT / 'logs' / 'log_pre.txt'
    calls = 0
    if log_file.exists():
        lines = log_file.read_text().splitlines()
        calls = len([l for l in lines if ('OUTGOING_CALL' in l and input_payload['orderId'] in l)])
    row = {
        'test_id': case['test_id'],
        'input': input_payload,
        'calls_to_upstream': calls,
        'final_status': rec['status'],
        'transaction_id': rec.get('transaction_id')
    }
    aggregated = []
    aggregated_file = ROOT / 'results' / 'results_pre.json'
    if aggregated_file.exists():
        try:
            aggregated = json.loads(aggregated_file.read_text())
        except Exception:
            aggregated = []
    aggregated.append(row)
    aggregated_file.write_text(json.dumps(aggregated, indent=2))

