import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from flask import Flask, jsonify, request

from adapter import build_v2_payload, map_v1_response, map_v2_response

app = Flask(__name__)
records: Dict[str, Dict[str, Any]] = {}
txn_to_order: Dict[str, str] = {}
webhook_events = []
lock = threading.Lock()

LOG_FILE = os.getenv(
    "LOG_FILE", os.path.join(os.path.dirname(__file__), "..", "logs", "log_post.txt")
)
V2_BASE_URL = os.getenv("PAYMENT_API_BASE_URL", "http://localhost:6001")
LEGACY_BASE_URL = os.getenv("LEGACY_PAYMENT_API_BASE_URL", "http://localhost:5001")
FEATURE_FLAG_USE_V2 = os.getenv("FEATURE_FLAG_USE_V2", "true").lower() == "true"
FALLBACK_ENABLED = os.getenv("FALLBACK_ENABLED", "true").lower() == "true"
TIMEOUT = float(os.getenv("PAYMENT_TIMEOUT", "3"))
RETRY_COUNT = int(os.getenv("PAYMENT_RETRY_COUNT", "2"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret-token")


def configure_logging():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    )
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(handler)


def persist_record(order_id: str, record: Dict[str, Any]):
    with lock:
        records[order_id] = record
        txn_id = record.get("transactionId")
        if txn_id:
            txn_to_order[txn_id] = order_id


def find_record_by_txn(transaction_id: str) -> Optional[Dict[str, Any]]:
    order_id = txn_to_order.get(transaction_id)
    if not order_id:
        return None
    return records.get(order_id)


def call_v2(payload: Dict[str, Any]) -> Dict[str, Any]:
    attempts = 0
    last_exc = None
    while attempts < RETRY_COUNT:
        attempts += 1
        try:
            response = requests.post(
                f"{V2_BASE_URL}/api/v2/payments/authorize",
                json=payload,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response.json(), attempts
        except requests.RequestException as exc:
            last_exc = exc
            app.logger.warning("v2 attempt %s failed: %s", attempts, exc)
            time.sleep(0.1)
    app.logger.error("v2 failed after %s attempts: %s", attempts, last_exc)
    raise last_exc or RuntimeError("v2 failure without exception")


def call_v1(payload: Dict[str, Any]) -> Dict[str, Any]:
    attempts = 0
    last_exc = None
    while attempts < RETRY_COUNT:
        attempts += 1
        try:
            response = requests.post(
                f"{LEGACY_BASE_URL}/api/v1/charge",
                json=payload,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response.json(), attempts
        except requests.RequestException as exc:
            last_exc = exc
            app.logger.warning("v1 fallback attempt %s failed: %s", attempts, exc)
            time.sleep(0.1)
    app.logger.error("v1 fallback failed after %s attempts: %s", attempts, last_exc)
    raise last_exc or RuntimeError("v1 fallback failure")


def record_from_v2(
    order_id: str, payload: Dict[str, Any], response: Dict[str, Any], attempts: int
) -> Dict[str, Any]:
    mapped = map_v2_response(response)
    status = mapped.get("status") or "pending"
    record = {
        "orderId": order_id,
        "status": status,
        "transactionId": mapped.get("transactionId"),
        "fraudScore": mapped.get("fraudScore"),
        "requiresAuth": mapped.get("requiresAuth", False),
        "upstream": "v2",
        "payload": payload,
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "webhook_received": False,
        "attempts": attempts,
    }
    if status not in ("authorized", "declined") or mapped.get("requiresAuth"):
        record["status"] = "pending"
    return record


def record_from_v1(
    order_id: str, payload: Dict[str, Any], response: Dict[str, Any], attempts: int
):
    mapped = map_v1_response(response)
    record = {
        "orderId": order_id,
        "status": "authorized" if mapped.get("success") else "declined",
        "transactionId": mapped.get("transactionId"),
        "fraudScore": None,
        "requiresAuth": False,
        "upstream": "v1",
        "payload": payload,
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "webhook_received": False,
        "attempts": attempts,
    }
    return record


@app.route("/settle", methods=["POST"])
def settle():
    payload = request.get_json(force=True)
    try:
        v2_payload = build_v2_payload(payload)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 400

    order_id = payload["orderId"]
    start_time = time.time()
    try:
        if not FEATURE_FLAG_USE_V2:
            raise RuntimeError("v2 feature flag disabled")
        response, attempts = call_v2(v2_payload)
        record = record_from_v2(order_id, v2_payload, response, attempts)
        persist_record(order_id, record)
        app.logger.info(
            "v2 settled %s upstream=%s requiresAuth=%s",
            order_id,
            record["upstream"],
            record["requiresAuth"],
        )
        body = {
            "orderId": order_id,
            "status": record["status"],
            "transactionId": record.get("transactionId"),
            "requiresAuth": record.get("requiresAuth"),
        }
        if record["status"] == "pending" and not record["requiresAuth"]:
            body["message"] = "awaiting async confirm"
        return jsonify(body), 200
    except Exception as exc:
        app.logger.warning(
            "primary v2 path failed for %s fallback=%s error=%s",
            order_id,
            FALLBACK_ENABLED,
            exc,
        )
        if FALLBACK_ENABLED:
            try:
                v1_payload = {
                    "orderId": payload["orderId"],
                    "amount": payload["amount"],
                    "paymentMethod": payload["paymentMethod"],
                }
                response, attempts = call_v1(v1_payload)
                record = record_from_v1(order_id, v1_payload, response, attempts)
                persist_record(order_id, record)
                body = {
                    "orderId": order_id,
                    "status": record["status"],
                    "transactionId": record.get("transactionId"),
                    "upstream": "v1",
                }
                return jsonify(body), 200
            except Exception as fallback_exc:
                app.logger.error("fallback v1 failed for %s: %s", order_id, fallback_exc)
                return (
                    jsonify(
                        {
                            "orderId": order_id,
                            "status": "error",
                            "reason": str(fallback_exc),
                        }
                    ),
                    502,
                )
        return jsonify({"orderId": order_id, "status": "error", "reason": str(exc)}), 502


@app.route("/webhook/payments", methods=["POST"])
def webhook_payments():
    signature = request.headers.get("X-Webhook-Secret")
    if signature != WEBHOOK_SECRET:
        return jsonify({"error": "invalid secret"}), 401
    event = request.get_json(force=True)
    transaction_id = event.get("transactionId")
    if not transaction_id:
        return jsonify({"error": "missing transactionId"}), 400
    record = find_record_by_txn(transaction_id)
    if not record:
        return jsonify({"error": "not found"}), 404
    with lock:
        if record.get("webhook_received") and record.get("status") == event.get("status"):
            return jsonify({"status": record["status"], "duplicate": True}), 200
        record["status"] = event.get("status", record["status"])
        record["fraudScore"] = event.get("fraudScore", record.get("fraudScore"))
        record["webhook_received"] = True
        record["lastUpdated"] = datetime.utcnow().isoformat() + "Z"
        webhook_events.append({"timestamp": datetime.utcnow().isoformat() + "Z", **event})
    app.logger.info("processed webhook for %s status=%s", transaction_id, record["status"])
    return jsonify({"status": record["status"]}), 200


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


@app.route("/events", methods=["GET"])
def get_events():
    return jsonify(webhook_events)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "mode": "post-change", "v2_base": V2_BASE_URL})


def main():
    configure_logging()
    port = int(os.getenv("SETTLEMENT_PORT", "6002"))
    app.logger.info("Starting post-change settlement service on port %s", port)
    app.run(port=port, host="0.0.0.0", threaded=True)


if __name__ == "__main__":
    main()
