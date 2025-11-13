import json
import os
import threading
import time
from typing import Any, Dict, Optional

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
behavior = {
    "status_code": 200,
    "response": {
        "transactionId": "T-default",
        "fraudScore": 10,
        "requiresAuth": False,
        "status": "authorized",
    },
    "delay": 0,
}
calls = []
lock = threading.Lock()

WEBHOOK_ENDPOINT = os.getenv(
    "WEBHOOK_ENDPOINT", "http://localhost:6002/webhook/payments"
)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret-token")


def dispatch_webhook(event: Dict[str, Any], delay: float, requires_auth: bool):
    def _send():
        if delay:
            time.sleep(delay)
        headers = {"X-Webhook-Secret": WEBHOOK_SECRET}
        try:
            requests.post(WEBHOOK_ENDPOINT, json=event, headers=headers, timeout=5)
        except requests.RequestException:
            pass

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


@app.route("/api/v2/payments/authorize", methods=["POST"])
def authorize():
    payload = request.get_json(force=True)
    with lock:
        cfg = behavior.copy()
        delay = cfg.get("delay", 0)
        webhook_cfg = cfg.get("webhook")
        calls.append({"timestamp": time.time(), "payload": payload})
    if delay > 0:
        time.sleep(delay)
    if webhook_cfg:
        dispatch_webhook(
            webhook_cfg["event"],
            webhook_cfg.get("delay", 0),
            webhook_cfg.get("requiresAuth", False),
        )
    return jsonify(cfg["response"]), cfg["status_code"]


@app.route("/configure", methods=["POST"])
def configure():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "expected payload"}), 400
    with lock:
        for key, value in data.items():
            if value is None:
                behavior.pop(key, None)
            else:
                behavior[key] = value
        calls.clear()
    return jsonify({"status": "configured"})


@app.route("/calls", methods=["GET"])
def get_calls():
    with lock:
        return jsonify(calls)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "mock": "v2"})


def main():
    app.run(host="0.0.0.0", port=6101, threaded=True)


if __name__ == "__main__":
    main()
