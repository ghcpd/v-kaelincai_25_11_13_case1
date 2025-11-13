from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import os
import json
import httpx
import uuid
from datetime import datetime

class SettleRequest(BaseModel):
    orderId: str
    amount: int
    paymentMethod: str
    currency: Optional[str] = 'USD'
    countryCode: Optional[str] = 'US'
    threeDS: Optional[str] = None

class V2Response(BaseModel):
    transactionId: Optional[str]
    fraudScore: Optional[int]
    requiresAuth: Optional[bool]
    status: Optional[str]

app = FastAPI()

PAYMENT_API_BASE = os.environ.get('PAYMENT_API_BASE_URL', 'http://localhost:9001')
PAYMENT_API_V1 = os.environ.get('PAYMENT_API_V1_BASE_URL', PAYMENT_API_BASE)
USE_V2 = os.environ.get('FEATURE_FLAG_USE_V2', 'true').lower() == 'true'
LOG_FILE = os.environ.get('LOG_FILE', 'logs/log_post.txt')
RESULTS_FILE = os.environ.get('RESULTS_FILE', 'results/storage_post.json')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 's3cr3t')

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)

storage = {}  # keyed by orderId
webhook_processed_tx = set()


def append_log(text):
    with open(LOG_FILE, 'a') as f:
        f.write(text + '\n')

# mapping from our internal to v2 API
async def call_v2(payload: dict, client: httpx.AsyncClient):
    url = f"{PAYMENT_API_BASE}/api/v2/payments/authorize"
    append_log(f"OUTGOING_CALL_V2 {url} {json.dumps(payload)}")
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    body = resp.json()
    append_log(f"V2_RESPONSE {body}")
    return body

async def call_v1(payload: dict, client: httpx.AsyncClient):
    url = f"{PAYMENT_API_V1}/api/v1/charge"
    append_log(f"OUTGOING_CALL_V1 {url} {json.dumps(payload)}")
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    body = resp.json()
    append_log(f"V1_RESPONSE {body}")
    return body

@app.post('/settle')
async def settle(req: SettleRequest, background_tasks: BackgroundTasks):
    payload = req.dict()
    order_id = req.orderId
    payload_v2 = {
        'orderId': req.orderId,
        'amount': req.amount,
        'currency': req.currency or 'USD',
        'countryCode': req.countryCode or 'US',
        'paymentMethod': req.paymentMethod,
        '3DS_token': req.threeDS
    }

    record = {
        'orderId': order_id,
        'amount': req.amount,
        'status': 'pending',
        'transaction_id': None,
        'fraudScore': None,
        'updated_at': datetime.utcnow().isoformat()
    }
    storage[order_id] = record

    async with httpx.AsyncClient(timeout=5.0) as client:
        if USE_V2:
            try:
                v2_resp = await call_v2(payload_v2, client)
            except Exception as e:
                append_log(f"V2 call failed: {e}")
                # fallback to v1
                try:
                    v1_resp = await call_v1({'orderId': req.orderId, 'amount': req.amount, 'paymentMethod': req.paymentMethod}, client)
                    status = 'authorized' if v1_resp.get('success') else 'declined'
                    storage[order_id].update({'status': status, 'transaction_id': None, 'updated_at': datetime.utcnow().isoformat()})
                    # persist
                    with open(RESULTS_FILE, 'w') as f:
                        json.dump(list(storage.values()), f, indent=2)
                    return {'status': status, 'fallbackToV1': True}
                except Exception as e2:
                    append_log(f"V1 fallback failed: {e2}")
                    raise HTTPException(status_code=502, detail='Both v2 and v1 failed')
            # handle v2 response structure
            tx = v2_resp.get('transactionId')
            status = v2_resp.get('status') or ('authorized' if not v2_resp.get('requiresAuth') else 'pending_auth')
            storage[order_id].update({'status': status, 'transaction_id': tx, 'fraudScore': v2_resp.get('fraudScore'), 'updated_at': datetime.utcnow().isoformat()})
            with open(RESULTS_FILE, 'w') as f:
                json.dump(list(storage.values()), f, indent=2)
            # if requiresAuth, return instructions to client
            if v2_resp.get('requiresAuth'):
                return {'status': 'requiresAuth', 'transactionId': tx}
            # synchronous success
            return {'status': status, 'transactionId': tx}
        else:
            # legacy v1 behavior
            v1_resp = await call_v1({'orderId': req.orderId, 'amount': req.amount, 'paymentMethod': req.paymentMethod}, client)
            status = 'authorized' if v1_resp.get('success') else 'declined'
            storage[order_id].update({'status': status, 'transaction_id': None, 'updated_at': datetime.utcnow().isoformat()})
            with open(RESULTS_FILE, 'w') as f:
                json.dump(list(storage.values()), f, indent=2)
            return {'status': status, 'fallbackToV1': not USE_V2}

@app.post('/webhook/payments')
async def webhook(request: Request):
    # verify webhook secret header
    headers = request.headers
    signature = headers.get('X-WEBHOOK-SIGNATURE')
    if signature != WEBHOOK_SECRET:
        append_log('Webhook signature invalid')
        raise HTTPException(status_code=401, detail='Invalid signature')
    payload = await request.json()
    tx = payload.get('transactionId')
    order_id = payload.get('orderId')
    status = payload.get('status')
    fraudScore = payload.get('fraudScore')
    # idempotent handling
    key = tx or order_id
    if key in webhook_processed_tx:
        append_log(f'Webhook duplicate {key} ignored')
        return {'processed': False}
    webhook_processed_tx.add(key)
    # update storage
    rec = storage.get(order_id)
    if not rec:
        append_log(f'Webhook unknown order {order_id}')
        storage[order_id] = {'orderId': order_id, 'amount': 0, 'status': status, 'transaction_id': tx, 'fraudScore': fraudScore, 'updated_at': datetime.utcnow().isoformat()}
    else:
        rec.update({'status': status, 'transaction_id': tx, 'fraudScore': fraudScore, 'updated_at': datetime.utcnow().isoformat()})
    # persist
    with open(RESULTS_FILE, 'w') as f:
        json.dump(list(storage.values()), f, indent=2)
    append_log(f'WEBHOOK_PROCESSED {payload}')
    return {'processed': True}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=9003)
