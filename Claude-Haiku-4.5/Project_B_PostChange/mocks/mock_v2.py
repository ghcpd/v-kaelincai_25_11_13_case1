"""
Mock v2 Payment API Server
Simulates POST /api/v2/payments/authorize endpoint
Supports async webhooks and richer responses
"""

import os
import json
import logging
import time
import threading
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Logging
LOG_FILE = os.getenv("LOG_FILE_MOCK_V2", "logs/mock_v2.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Mock behavior config
MOCK_CONFIG = {
    "delay_ms": 0,
    "status_code": 200,
    "response": {
        "transactionId": "TXN_DEFAULT",
        "fraudScore": 10,
        "requiresAuth": False,
        "status": "authorized"
    },
    "webhook": None,
    "enabled": True
}

# Webhook callback URL (set dynamically)
WEBHOOK_CALLBACK_URL = None


@app.route("/api/v2/payments/authorize", methods=["POST"])
def authorize():
    """Mock v2 authorize endpoint"""
    data = request.get_json()
    idempotency_key = request.headers.get("X-Idempotency-Key", "")
    
    logger.info(f"[V2] Received authorize request: {json.dumps(data)}")
    logger.info(f"[V2] Idempotency-Key: {idempotency_key}")
    
    if not MOCK_CONFIG["enabled"]:
        logger.info("[V2] Mock disabled")
        return jsonify({"error": "Service unavailable"}), 503
    
    # Apply delay
    if MOCK_CONFIG["delay_ms"] > 0:
        logger.info(f"[V2] Applying delay: {MOCK_CONFIG['delay_ms']}ms")
        time.sleep(MOCK_CONFIG["delay_ms"] / 1000.0)
    
    response_data = MOCK_CONFIG["response"].copy()
    status_code = MOCK_CONFIG["status_code"]
    
    logger.info(f"[V2] Returning status {status_code}: {json.dumps(response_data)}")
    
    # If webhook is configured, schedule async callback
    if MOCK_CONFIG["webhook"] and WEBHOOK_CALLBACK_URL:
        webhook_config = MOCK_CONFIG["webhook"]
        transaction_id = response_data.get("transactionId")
        
        def send_webhook():
            time.sleep(webhook_config["delay_ms"] / 1000.0)
            
            webhook_payload = webhook_config["data"].copy()
            webhook_payload["transactionId"] = transaction_id
            
            logger.info(f"[V2] Sending webhook callback: {json.dumps(webhook_payload)}")
            
            try:
                webhook_response = requests.post(
                    WEBHOOK_CALLBACK_URL,
                    json=webhook_payload,
                    timeout=10,
                    headers={"X-Webhook-Signature": "test-signature"}
                )
                logger.info(f"[V2] Webhook response status: {webhook_response.status_code}")
            except Exception as e:
                logger.error(f"[V2] Webhook delivery failed: {str(e)}")
        
        # Send webhook asynchronously
        thread = threading.Thread(target=send_webhook, daemon=True)
        thread.start()
    
    return jsonify(response_data), status_code


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/mock/config", methods=["GET"])
def get_config():
    """Get current mock config"""
    return jsonify(MOCK_CONFIG), 200


@app.route("/mock/config", methods=["POST"])
def set_config():
    """Update mock config for testing"""
    global MOCK_CONFIG
    config_updates = request.get_json()
    MOCK_CONFIG.update(config_updates)
    logger.info(f"[V2] Config updated: {json.dumps(MOCK_CONFIG)}")
    return jsonify(MOCK_CONFIG), 200


@app.route("/mock/webhook-callback", methods=["POST"])
def set_webhook_callback():
    """Set webhook callback URL"""
    global WEBHOOK_CALLBACK_URL
    data = request.get_json()
    WEBHOOK_CALLBACK_URL = data.get("callbackUrl")
    logger.info(f"[V2] Webhook callback URL set to: {WEBHOOK_CALLBACK_URL}")
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    app.run(host="0.0.0.0", port=5002, debug=False)
