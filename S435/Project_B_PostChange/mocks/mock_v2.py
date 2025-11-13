import os
import json
import time
import threading
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

CONFIG = {'mode': 'sync', 'status': 'authorized', 'delay': 0}
CALL_LOG = []

@app.route('/configure', methods=['POST'])
def configure():
    global CONFIG
    CONFIG.update(request.get_json() or {})
    return jsonify({'configured': True, 'config': CONFIG})

@app.route('/api/v2/payments/authorize', methods=['POST'])
def authorize():
    payload = request.get_json()
    CALL_LOG.append({'path': '/api/v2/payments/authorize', 'payload': payload})
    mode = CONFIG.get('mode')
    delay = float(CONFIG.get('delay', 0))
    if CONFIG.get('timeout'):
        time.sleep(6)
    if mode == 'sync':
        transaction_id = CONFIG.get('transactionId', 'T567')
        status = CONFIG.get('status', 'authorized')
        return jsonify({'transactionId': transaction_id, 'fraudScore': CONFIG.get('fraudScore', 12), 'requiresAuth': False, 'status': status}), 200
    elif mode == 'requiresAuth':
        transaction_id = CONFIG.get('transactionId', 'T890')
        # return requiresAuth then schedule webhook
        def send_webhook():
            time.sleep(CONFIG.get('webhook_delay', 1))
            webhook_url = CONFIG.get('webhook_url')
            if webhook_url:
                requests.post(webhook_url, json={'transactionId': transaction_id, 'status': CONFIG.get('final_status','authorized'), 'fraudScore': CONFIG.get('fraudScore',8)}, headers={'X-Webhook-Signature': CONFIG.get('webhook_secret','secret')})
        threading.Thread(target=send_webhook).start()
        return jsonify({'transactionId': transaction_id, 'fraudScore': CONFIG.get('fraudScore', 50), 'requiresAuth': True, 'status': 'pending_auth'}), 200
    elif mode == 'async_pending':
        transaction_id = CONFIG.get('transactionId', 'T901')
        def send_webhook():
            time.sleep(CONFIG.get('webhook_delay', 1))
            webhook_url = CONFIG.get('webhook_url')
            if webhook_url:
                requests.post(webhook_url, json={'transactionId': transaction_id, 'status': CONFIG.get('final_status','authorized'), 'fraudScore': CONFIG.get('fraudScore',4)}, headers={'X-Webhook-Signature': CONFIG.get('webhook_secret','secret')})
        threading.Thread(target=send_webhook).start()
        return jsonify({'transactionId': transaction_id, 'fraudScore': CONFIG.get('fraudScore', 40), 'requiresAuth': False, 'status': 'pending'}), 200
    elif mode == 'error':
        return jsonify({'error': 'internal server error'}), 500
    else:
        return jsonify({'transactionId': 'UNKNOWN', 'fraudScore': 0, 'requiresAuth': False, 'status': 'declined'}), 200

@app.route('/calls', methods=['GET'])
def calls():
    return jsonify(CALL_LOG)

if __name__ == '__main__':
    port = int(os.environ.get('MOCK_V2_PORT', 6001))
    app.run(port=port)
