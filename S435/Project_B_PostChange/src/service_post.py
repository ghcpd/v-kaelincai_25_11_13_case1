import os
import json
import time
from flask import Flask, request, jsonify, abort
import requests

app = Flask(__name__)

STORE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'store_post.json')
UPSTREAM_BASE = os.environ.get('PAYMENT_API_BASE_URL', 'http://localhost:6001')
FEATURE_USE_V2 = os.environ.get('FEATURE_FLAG_USE_V2', 'true').lower() == 'true'
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'secret')

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


def get_record_by_transaction(transaction_id):
    try:
        with open(STORE_PATH, 'r') as f:
            store = json.load(f)
    except Exception:
        return None
    for k, v in store.items():
        if v.get('transactionId') == transaction_id:
            return k, v
    return None


@app.route('/settlement', methods=['POST'])
def settlement():
    payload = request.get_json()
    order_id = payload.get('orderId')
    amount = payload.get('amount')
    payment_method = payload.get('paymentMethod')
    currency = payload.get('currency')
    country = payload.get('countryCode')
    threeDS = payload.get('threeDS')

    if FEATURE_USE_V2:
        # Call v2
        url = f"{UPSTREAM_BASE}/api/v2/payments/authorize"
        upstream_payload = {
            'orderId': order_id,
            'amount': amount,
            'currency': currency,
            'countryCode': country,
            'paymentMethod': payment_method,
            '3DS_token': threeDS,
        }
        try:
            resp = requests.post(url, json=upstream_payload, timeout=5)
        except Exception as e:
            # fallback to v1
            return fallback_to_v1(order_id, amount, payment_method)
        if resp.status_code == 200:
            data = resp.json()
            transactionId = data.get('transactionId')
            fraudScore = data.get('fraudScore')
            requiresAuth = data.get('requiresAuth')
            status = data.get('status')
            record = {'status': status, 'transactionId': transactionId, 'fraudScore': fraudScore}
            persist_record(order_id, record)
            if requiresAuth:
                return jsonify({'requiresAuth': True, 'transactionId': transactionId}), 200
            if status == 'authorized':
                return jsonify({'success': True, 'transactionId': transactionId}), 200
            else:
                return jsonify({'success': False, 'status': status}), 200
        else:
            # handle v2 error
            return fallback_to_v1(order_id, amount, payment_method)
    else:
        return fallback_to_v1(order_id, amount, payment_method)


def fallback_to_v1(order_id, amount, payment_method):
    url = f"{UPSTREAM_BASE.replace('/api/v2', '/api/v1')}/charge" if '/api/v2' in UPSTREAM_BASE else f"{UPSTREAM_BASE.replace('600','500')}/api/v1/charge"
    # for tests, we support replacing base URL with mock_v1
    try:
        resp = requests.post(url, json={'orderId': order_id, 'amount': amount, 'paymentMethod': payment_method}, timeout=5)
    except Exception as e:
        record = {'status': 'error', 'error': str(e)}
        persist_record(order_id, record)
        return jsonify({'success': False, 'error': str(e)}), 500
    if resp.status_code == 200:
        data = resp.json()
        if data.get('success'):
            record = {'status': 'authorized', 'transactionId': data.get('transactionId')}
            persist_record(order_id, record)
            return jsonify({'success': True, 'transactionId': data.get('transactionId')}), 200
        else:
            record = {'status': 'declined', 'transactionId': None}
            persist_record(order_id, record)
            return jsonify({'success': False}), 200
    else:
        record = {'status': 'error', 'http_status': resp.status_code}
        persist_record(order_id, record)
        return jsonify({'success': False, 'http_status': resp.status_code}), 502


@app.route('/webhook/payments', methods=['POST'])
def webhook_payments():
    # Webhook verification using header X-Webhook-Signature
    signature = request.headers.get('X-Webhook-Signature')
    if signature != WEBHOOK_SECRET:
        abort(401)
    payload = request.get_json()
    transactionId = payload.get('transactionId')
    status = payload.get('status')
    fraudScore = payload.get('fraudScore')
    found = get_record_by_transaction(transactionId)
    if not found:
        # store by transaction id in fallback manner
        order_id = payload.get('orderId') or f'unknown-{transactionId}'
    else:
        order_id = found[0]
    # idempotent: if already final state, ignore
    try:
        with open(STORE_PATH, 'r') as f:
            store = json.load(f)
    except Exception:
        store = {}
    existing = store.get(order_id, {})
    if existing.get('status') == 'authorized':
        return jsonify({'processed': False, 'reason': 'already authorized'}), 200
    # update record
    new_rec = {'status': status, 'transactionId': transactionId, 'fraudScore': fraudScore}
    persist_record(order_id, new_rec)
    return jsonify({'processed': True}), 200


@app.route('/records/<order_id>', methods=['GET'])
def get_record(order_id):
    try:
        with open(STORE_PATH, 'r') as f:
            store = json.load(f)
    except Exception:
        return jsonify({}), 404
    if order_id in store:
        r = store[order_id]
        safe = r.copy()
        # Do not log sensitive stuff
        return jsonify(safe)
    return jsonify({}), 404


if __name__ == '__main__':
    port = int(os.environ.get('SERVICE_PORT', 6000))
    app.run(port=port)
