from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import httpx
import json
from datetime import datetime

class SettleRequest(BaseModel):
    orderId: str
    amount: int
    paymentMethod: str

app = FastAPI()

PAYMENT_API_BASE = os.environ.get('PAYMENT_API_BASE_URL', 'http://localhost:8001')
LOG_FILE = os.environ.get('LOG_FILE', 'logs/log_pre.txt')
RESULTS_FILE = os.environ.get('RESULTS_FILE', 'results/storage_pre.json')

# Simple file-based persistence for tests
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)

def append_log(text):
    with open(LOG_FILE, 'a') as f:
        f.write(text + '\n')

storage = {}

@app.post('/settle')
async def settle(req: SettleRequest):
    payload = req.dict()
    # call v1 upstream
    url = f"{PAYMENT_API_BASE}/api/v1/charge"
    append_log(f"OUTGOING_CALL {datetime.utcnow().isoformat()} {url} {json.dumps(payload)}")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            body = resp.json()
    except Exception as e:
        append_log(f"ERROR calling upstream v1: {e}")
        raise HTTPException(status_code=502, detail='Upstream failure')
    append_log(f"UPSTREAM_RESPONSE {body}")
    # v1 returns minimal success boolean
    success = body.get('success')
    status = 'authorized' if success else 'declined'

    record = {
        'orderId': req.orderId,
        'amount': req.amount,
        'status': status,
        'transaction_id': None,
        'updated_at': datetime.utcnow().isoformat()
    }
    storage[req.orderId] = record
    append_log(f"STORE {json.dumps(record)}")
    # write results file for tests
    with open(RESULTS_FILE, 'w') as f:
        json.dump(list(storage.values()), f, indent=2)
    return {'status': status}
