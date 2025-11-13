from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Optional
import uvicorn
import json
import threading
import time
import requests

class V2Req(BaseModel):
    orderId: str
    amount: int
    currency: str
    countryCode: str
    paymentMethod: str
    _3DS_token: Optional[str] = None

app = FastAPI()

MODE = {'behavior': 'sync_authorized', 'delay_webhook_seconds': 1, 'delay_response_seconds': 0, 'webhook_url': 'http://localhost:9003/webhook/payments'}

@app.post('/api/v2/payments/authorize')
def authorize(req: V2Req):
    time.sleep(MODE.get('delay_response_seconds', 0))
    b = MODE['behavior']
    if b == 'sync_authorized':
        return {'transactionId': f'TX-{req.orderId}', 'fraudScore': 12, 'requiresAuth': False, 'status': 'authorized'}
    if b == 'requires_3ds':
        tx = f'TX-{req.orderId}'
        # schedule webhook
        threading.Thread(target=delayed_webhook, args=(tx, req.orderId, 'authorized', MODE['delay_webhook_seconds'])).start()
        return {'transactionId': tx, 'requiresAuth': True, 'status': 'pending_auth'}
    if b == 'pending_then_webhook':
        tx = f'TX-{req.orderId}'
        threading.Thread(target=delayed_webhook, args=(tx, req.orderId, 'authorized', MODE['delay_webhook_seconds'])).start()
        return {'transactionId': tx, 'requiresAuth': False, 'status': 'pending'}
    if b == 'error_500':
        return {}, 500
    if b == 'decline_fraud':
        return {'transactionId': f'TX-{req.orderId}', 'fraudScore': 98, 'requiresAuth': False, 'status': 'declined'}
    return {'transactionId': f'TX-{req.orderId}', 'fraudScore': 5, 'requiresAuth': False, 'status': 'authorized'}

@app.post('/configure')
def configure(payload: dict = Body(...)):
    MODE['behavior'] = payload.get('behavior', MODE['behavior'])
    MODE['delay_webhook_seconds'] = payload.get('delay_webhook_seconds', MODE['delay_webhook_seconds'])
    MODE['webhook_url'] = payload.get('webhook_url', MODE['webhook_url'])
    return {'configured': MODE}


def delayed_webhook(transactionId, orderId, status, delay):
    time.sleep(delay)
    body = {'transactionId': transactionId, 'orderId': orderId, 'status': status, 'fraudScore': 5}
    try:
        requests.post(MODE['webhook_url'], json=body, headers={'X-WEBHOOK-SIGNATURE': 's3cr3t'}, timeout=5)
    except Exception as e:
        print('webhook failed', e)

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=9001)
