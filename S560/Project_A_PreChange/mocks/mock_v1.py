from fastapi import FastAPI
from fastapi import Body
from pydantic import BaseModel
from typing import Optional
import uvicorn
import json
import time
import threading

class ChargeReq(BaseModel):
    orderId: str
    amount: int
    paymentMethod: str

app = FastAPI()

# Simple operation modes to be set via /configure for tests
MODE = {'behavior': 'sync_authorized'}

@app.post('/api/v1/charge')
def charge(req: ChargeReq):
    if MODE['behavior'] == 'sync_authorized':
        return {'success': True}
    elif MODE['behavior'] == 'sync_decline':
        return {'success': False}
    elif MODE['behavior'] == 'error_500':
        return {}, 500
    else:
        return {'success': True}

@app.post('/configure')
def configure(payload: dict = Body(...)):
    MODE['behavior'] = payload.get('behavior', 'sync_authorized')
    return {'configured': MODE}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8001)
