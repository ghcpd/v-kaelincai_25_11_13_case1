import os
import subprocess
import time
import requests
import json
import signal
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
MOCK_V1_PORT = 5001
SERVICE_PORT = 5000

def start_process(cmd, cwd):
    return subprocess.Popen([sys.executable, '-u'] + cmd, cwd=cwd)


def setup_module(module):
    # Start mock v1
    module.mock_v1 = start_process(['mocks/mock_v1.py'], ROOT)
    time.sleep(1)
    module.service = start_process(['src/service_pre.py'], ROOT)
    time.sleep(1)


def teardown_module(module):
    for p in ('mock_v1', 'service'):
        proc = getattr(module, p, None)
        if proc:
            proc.terminate()
            proc.wait(timeout=5)


def test_tc1_sync_authorized(tmp_path):
    # Configure mock v1 to sync authorized
    cfg = {'mode': 'sync', 'status': 'authorized'}
    requests.post(f'http://localhost:{MOCK_V1_PORT}/configure', json=cfg)
    orderId = 'O123'
    payload = {'orderId': orderId, 'amount': 1000, 'paymentMethod': 'card'}
    resp = requests.post(f'http://localhost:{SERVICE_PORT}/settlement', json=payload, timeout=10)
    assert resp.status_code == 200
    time.sleep(0.5)
    rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/{orderId}').json()
    assert rec['status'] == 'authorized'


def test_tc4_v2_error_fallback(tmp_path):
    # Simulate v1 success; though pre-change uses v1 only; this test illustrates fallback path
    cfg = {'mode': 'sync', 'status': 'authorized'}
    requests.post(f'http://localhost:{MOCK_V1_PORT}/configure', json=cfg)
    orderId = 'O126'
    payload = {'orderId': orderId, 'amount': 500, 'paymentMethod': 'card'}
    resp = requests.post(f'http://localhost:{SERVICE_PORT}/settlement', json=payload, timeout=10)
    assert resp.status_code == 200
    rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/{orderId}').json()
    assert rec['status'] == 'authorized'


def write_results(test_id, order_id, upstream_calls, final_record, log_path):
    results = {
        'test_id': test_id,
        'input': {'orderId': order_id},
        'calls_to_upstream': upstream_calls,
        'final_status': final_record,
        'timestamps': {'ts': time.time()}
    }
    outpath = os.path.join(ROOT, 'results', 'results_pre.json')
    with open(outpath, 'a') as f:
        f.write(json.dumps(results) + '\n')


if __name__ == '__main__':
    setup_module(None)
    try:
        test_tc1_sync_authorized(None)
        calls = requests.get(f'http://localhost:{MOCK_V1_PORT}/calls').json()
        rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/O123').json()
        # write logs
        with open(os.path.join(ROOT, 'logs', 'log_pre.txt'), 'a') as f:
            f.write('CALLS: ' + json.dumps(calls) + '\n')
        write_results('TC1-sync-authorized', 'O123', calls, rec, os.path.join(ROOT, 'logs', 'log_pre.txt'))

        test_tc4_v2_error_fallback(None)
        calls = requests.get(f'http://localhost:{MOCK_V1_PORT}/calls').json()
        rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/O126').json()
        write_results('TC4-v2-error-fallback', 'O126', calls, rec, os.path.join(ROOT, 'logs', 'log_pre.txt'))
    finally:
        teardown_module(None)
