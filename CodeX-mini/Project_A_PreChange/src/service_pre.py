import json
import logging
import os
import threading
import time
from datetime import datetime

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
records = {}
lock = threading.Lock()

LOG_FILE = os.getenv(
    "LOG_FILE", os.path.join(os.path.dirname(__file__), "..", "logs", "log_pre.txt")
)
PAYMENT_API_BASE_URL = os.getenv("PAYMENT_API_BASE_URL", "http://localhost:5001")
TIMEOUT = float(os.getenv("PAYMENT_TIMEOUT", "4"))
RETRY_COUNT = int(os.getenv("PAYMENT_RETRY_COUNT", "1"))


def configure_logging():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    )
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(handler)


def build_v1_payload(payload):
    return {
        "orderId": payload["orderId"],
        "amount": payload["amount"],
        "paymentMethod": payload["paymentMethod"],
    }


def call_v1(payload):
    attempts = 0
    last_exception = None
    while attempts < RETRY_COUNT:
        attempts += 1
        try:
            response = requests.post(
                f"{PAYMENT_API_BASE_URL}/api/v1/charge",
                json=payload,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response.json(), attempts
        except requests.RequestException as exc:
            last_exception = exc
            app.logger.warning(
                "v1 attempt %s failed for %s: %s", attempts, payload["orderId"], exc
            )
            time.sleep(0.1)
    app.logger.error("v1 failed after %s attempts: %s", attempts, last_exception)
    raise last_exception or RuntimeError("v1 failed without exception")


def persist_record(order_id, payload, upstream, status, transaction_id=None, error=None):
    with lock:
        records[order_id] = {
            "orderId": order_id,
            "status": status,
            "transactionId": transaction_id,
            "upstream": upstream,
            "fraudScore": None,
            "error": error,
            "lastUpdated": datetime.utcnow().isoformat() + "Z",
            "attempts": payload.get("attempts", 1),
            "payload": payload,
        }


@app.route("/settle", methods=["POST"])
def settle():
    payload = request.get_json(force=True)
    for field in ("orderId", "amount", "paymentMethod"):
        if field not in payload:
            return jsonify({"error": f"missing {field}"}), 400

    order_id = payload["orderId"]
    v1_payload = build_v1_payload(payload)
    try:
        response, attempts = call_v1(v1_payload)
        status = "authorized" if response.get("success") else "declined"
        transaction_id = response.get("transactionId")
        persist_record(
            order_id,
            {"payload": v1_payload, "attempts": attempts},
            "v1",
            status,
            transaction_id=transaction_id,
        )
        app.logger.info(
            "settlement %s status=%s attempts=%s", order_id, status, attempts
        )
        return jsonify({"orderId": order_id, "status": status}), 200
    except Exception as exc:
        persist_record(
            order_id,
            {"payload": v1_payload, "attempts": RETRY_COUNT},
            "v1",
            "error",
            error=str(exc),
        )
        return (
            jsonify({"orderId": order_id, "status": "error", "reason": str(exc)}),
            502,
        )


@app.route("/records", methods=["GET"])
def list_records():
    with lock:
        return jsonify(list(records.values()))


@app.route("/records/<order_id>", methods=["GET"])
def get_record(order_id):
    record = records.get(order_id)
    if not record:
        return jsonify({"error": "not found"}), 404
    return jsonify(record)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "mode": "pre-change"})


def main():
    configure_logging()
    port = int(os.getenv("SETTLEMENT_PORT", "5002"))
    app.logger.info(
        "Starting pre-change settlement service on port %s pointing to %s",
        port,
        PAYMENT_API_BASE_URL,
    )
    app.run(port=port, host="0.0.0.0", threaded=True)


if __name__ == "__main__":
    main()
