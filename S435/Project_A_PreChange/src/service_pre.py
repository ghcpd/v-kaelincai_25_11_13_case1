import os
import json
import time
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

STORE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'store_pre.json')
UPSTREAM_BASE = os.environ.get('PAYMENT_API_BASE_URL', 'http://localhost:5001')
FEATURE_USE_V2 = os.environ.get('FEATURE_FLAG_USE_V2', 'false').lower() == 'true'

# Simple persistence
if not os.path.exists(os.path.dirname(STORE_PATH)):
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
if not os.path.exists(STORE_PATH):
    with open(STORE_PATH, 'w') as f:
        json.dump({}, f)


def persist_record(order_id, record):
    try:
        with open(STORE_PATH, 'r') as f:
            store = json.load(f)
    except Exception:
        store = {}
    store[order_id] = record
    with open(STORE_PATH, 'w') as f:
        json.dump(store, f)


@app.route('/settlement', methods=['POST'])
def settlement():
    payload = request.get_json()
    order_id = payload.get('orderId')
    amount = payload.get('amount')
    payment_method = payload.get('paymentMethod')
    # Pre-change: call v1 endpoint
    url = f"{UPSTREAM_BASE}/api/v1/charge"
    upstream_payload = {'orderId': order_id, 'amount': amount, 'paymentMethod': payment_method}
    try:
        resp = requests.post(url, json=upstream_payload, timeout=5)
    except Exception as e:
        record = {'status': 'error', 'error': str(e), 'attempted': True}
        persist_record(order_id, record)
        return jsonify({'success': False, 'error': str(e)}), 500
    if resp.status_code == 200:
        data = resp.json()
        if data.get('success'):
            record = {'status': 'authorized', 'transactionId': None}
            persist_record(order_id, record)
            return jsonify({'success': True}), 200
        else:
            record = {'status': 'declined', 'transactionId': None}
            persist_record(order_id, record)
            return jsonify({'success': False, 'reason': 'declined'}), 200
    else:
        record = {'status': 'error', 'http_status': resp.status_code}
        persist_record(order_id, record)
        return jsonify({'success': False, 'http_status': resp.status_code}), 502


@app.route('/records/<order_id>', methods=['GET'])
def get_record(order_id):
    try:
        with open(STORE_PATH, 'r') as f:
            store = json.load(f)
    except Exception:
        return jsonify({}), 404
    if order_id in store:
        return jsonify(store[order_id])
    return jsonify({}), 404


if __name__ == '__main__':
    port = int(os.environ.get('SERVICE_PORT', 5000))
    app.run(port=port)
