from fastapi import FastAPI, Body
from pydantic import BaseModel
import uvicorn

class ChargeReq(BaseModel):
    orderId: str
    amount: int
    paymentMethod: str

app = FastAPI()
MODE = {'behavior': 'sync_authorized'}

@app.post('/api/v1/charge')
def charge(req: ChargeReq):
    if MODE['behavior'] == 'sync_authorized':
        return {'success': True}
    if MODE['behavior'] == 'sync_decline':
        return {'success': False}
    if MODE['behavior'] == 'error_500':
        return {}, 500
    return {'success': True}

@app.post('/configure')
def configure(payload: dict = Body(...)):
    MODE['behavior'] = payload.get('behavior', MODE['behavior'])
    return {'configured': MODE}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=9002)
