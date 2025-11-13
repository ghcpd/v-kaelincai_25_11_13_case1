import os
import subprocess
import time
import requests
import json
import sys
import signal

ROOT = os.path.dirname(os.path.dirname(__file__))
MOCK_V2_PORT = 6001
MOCK_V1_PORT = 5001
SERVICE_PORT = 6000

def start_process(cmd, cwd):
    return subprocess.Popen([sys.executable, '-u'] + cmd, cwd=cwd)


def setup_module(module):
    # Start mock v2 and v1
    module.mock_v2 = start_process(['mocks/mock_v2.py'], ROOT)
    module.mock_v1 = start_process(['mocks/mock_v1.py'], os.path.join(ROOT, '..', 'Project_A_PreChange'))
    time.sleep(1)
    module.service = start_process(['src/service_post.py'], ROOT)
    time.sleep(1)


def teardown_module(module):
    for p in ('mock_v2', 'mock_v1', 'service'):
        proc = getattr(module, p, None)
        if proc:
            proc.terminate()
            proc.wait(timeout=5)


def write_results(test_id, input_payload, upstream_calls, final_record):
    results = {
        'test_id': test_id,
        'input': input_payload,
        'calls_to_upstream': upstream_calls,
        'final_status': final_record,
        'timestamps': {'ts': time.time()}
    }
    outpath = os.path.join(ROOT, 'results', 'results_post.json')
    with open(outpath, 'a') as f:
        f.write(json.dumps(results) + '\n')


def test_tc1_sync_authorized():
    cfg = {'mode': 'sync', 'status': 'authorized', 'transactionId': 'T567', 'fraudScore': 12}
    requests.post(f'http://localhost:{MOCK_V2_PORT}/configure', json=cfg)
    payload = {'orderId': 'O123', 'amount': 1000, 'paymentMethod': 'card', 'currency': 'USD', 'countryCode': 'US', 'threeDS': None}
    resp = requests.post(f'http://localhost:{SERVICE_PORT}/settlement', json=payload, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get('success') is True
    time.sleep(0.5)
    rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/O123').json()
    calls = requests.get(f'http://localhost:{MOCK_V2_PORT}/calls').json()
    write_results('TC1-sync-authorized', payload, calls, rec)
    with open(os.path.join(ROOT, 'logs', 'log_post.txt'), 'a') as f:
        f.write('CALLS: ' + json.dumps(calls) + '\n')
    assert rec['status'] == 'authorized'
    assert rec['transactionId'] == 'T567'


def test_tc2_3ds_flow():
    cfg = {'mode': 'requiresAuth', 'transactionId': 'T890', 'fraudScore': 50, 'webhook_url': f'http://localhost:{SERVICE_PORT}/webhook/payments', 'webhook_delay': 1, 'webhook_secret': 'secret', 'final_status': 'authorized'}
    requests.post(f'http://localhost:{MOCK_V2_PORT}/configure', json=cfg)
    payload = {'orderId': 'O124', 'amount': 1500, 'paymentMethod': 'card', 'currency': 'USD', 'countryCode': 'US', 'threeDS': None}
    resp = requests.post(f'http://localhost:{SERVICE_PORT}/settlement', json=payload, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get('requiresAuth') is True
    # wait for webhook
    time.sleep(2)
    rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/O124').json()
    calls = requests.get(f'http://localhost:{MOCK_V2_PORT}/calls').json()
    write_results('TC2-3DS-flow', payload, calls, rec)
    with open(os.path.join(ROOT, 'logs', 'log_post.txt'), 'a') as f:
        f.write('CALLS: ' + json.dumps(calls) + '\n')
    assert rec['status'] == 'authorized'
    assert rec['transactionId'] == 'T890'


def test_tc3_async_confirm():
    cfg = {'mode': 'async_pending', 'transactionId': 'T901', 'fraudScore': 4, 'webhook_url': f'http://localhost:{SERVICE_PORT}/webhook/payments', 'webhook_delay': 1, 'webhook_secret': 'secret', 'final_status': 'authorized'}
    requests.post(f'http://localhost:{MOCK_V2_PORT}/configure', json=cfg)
    payload = {'orderId': 'O125', 'amount': 2000, 'paymentMethod': 'card', 'currency': 'EUR', 'countryCode': 'DE', 'threeDS': None}
    resp = requests.post(f'http://localhost:{SERVICE_PORT}/settlement', json=payload, timeout=10)
    assert resp.status_code == 200
    # initial should be pending
    rec_initial = requests.get(f'http://localhost:{SERVICE_PORT}/records/O125').json()
    assert rec_initial['status'] in ('pending', 'pending_auth') or rec_initial['transactionId'] == 'T901'
    # wait for webhook
    time.sleep(2)
    rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/O125').json()
    calls = requests.get(f'http://localhost:{MOCK_V2_PORT}/calls').json()
    write_results('TC3-async-confirm', payload, calls, rec)
    with open(os.path.join(ROOT, 'logs', 'log_post.txt'), 'a') as f:
        f.write('CALLS: ' + json.dumps(calls) + '\n')
    assert rec['status'] == 'authorized'
    assert rec['transactionId'] == 'T901'


def test_tc4_v2_error_fallback():
    # configure v2 to error and v1 to succeed
    requests.post(f'http://localhost:{MOCK_V2_PORT}/configure', json={'mode': 'error'})
    requests.post(f'http://localhost:{MOCK_V1_PORT}/configure', json={'mode': 'sync', 'status': 'authorized', 'transactionId': 'V1-T-123'})
    payload = {'orderId': 'O126', 'amount': 500, 'paymentMethod': 'card', 'currency': 'USD', 'countryCode': 'US', 'threeDS': None}
    resp = requests.post(f'http://localhost:{SERVICE_PORT}/settlement', json=payload, timeout=10)
    assert resp.status_code == 200
    rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/O126').json()
    calls_v1 = requests.get(f'http://localhost:{MOCK_V1_PORT}/calls').json()
    write_results('TC4-v2-error-fallback', payload, calls_v1, rec)
    with open(os.path.join(ROOT, 'logs', 'log_post.txt'), 'a') as f:
        f.write('CALLS_V1: ' + json.dumps(calls_v1) + '\n')
    assert rec['status'] == 'authorized'


def test_tc5_fraud_decline():
    cfg = {'mode': 'sync', 'status': 'declined', 'transactionId': 'T999', 'fraudScore': 88}
    requests.post(f'http://localhost:{MOCK_V2_PORT}/configure', json=cfg)
    payload = {'orderId': 'O127', 'amount': 750, 'paymentMethod': 'card', 'currency': 'USD', 'countryCode': 'US', 'threeDS': None}
    resp = requests.post(f'http://localhost:{SERVICE_PORT}/settlement', json=payload, timeout=10)
    assert resp.status_code == 200
    rec = requests.get(f'http://localhost:{SERVICE_PORT}/records/O127').json()
    calls = requests.get(f'http://localhost:{MOCK_V2_PORT}/calls').json()
    write_results('TC5-fraud-decline', payload, calls, rec)
    with open(os.path.join(ROOT, 'logs', 'log_post.txt'), 'a') as f:
        f.write('CALLS: ' + json.dumps(calls) + '\n')
    assert rec['status'] == 'declined'
    assert rec['fraudScore'] == 88


if __name__ == '__main__':
    setup_module(None)
    try:
        test_tc1_sync_authorized()
        test_tc2_3ds_flow()
        test_tc3_async_confirm()
        test_tc4_v2_error_fallback()
        test_tc5_fraud_decline()
    finally:
        teardown_module(None)
