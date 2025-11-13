import os
import json
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

CONFIG = {'mode': 'sync', 'status': 'authorized'}
CALL_LOG = []

@app.route('/configure', methods=['POST'])
def configure():
    global CONFIG
    CONFIG.update(request.get_json() or {})
    return jsonify({'configured': True, 'config': CONFIG})

@app.route('/api/v1/charge', methods=['POST'])
def charge():
    payload = request.get_json()
    CALL_LOG.append({'path': '/api/v1/charge', 'payload': payload})
    mode = CONFIG.get('mode')
    if CONFIG.get('timeout'):
        time.sleep(6)
    if mode == 'sync':
        status = CONFIG.get('status', 'authorized')
        if status == 'authorized':
            return jsonify({'success': True, 'transactionId': 'V1-T-123'}), 200
        else:
            return jsonify({'success': False}), 200
    elif mode == 'error':
        return jsonify({'error': 'internal server error'}), 500
    else:
        return jsonify({'success': False}), 200

@app.route('/calls', methods=['GET'])
def calls():
    return jsonify(CALL_LOG)

if __name__ == '__main__':
    port = int(os.environ.get('MOCK_V1_PORT', 5001))
    app.run(port=port)
