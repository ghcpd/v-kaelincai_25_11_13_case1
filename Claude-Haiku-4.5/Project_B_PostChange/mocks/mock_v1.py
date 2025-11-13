"""
Mock v1 Payment API Server
Used by both Project A and Project B for v1 compatibility testing
"""

import os
import json
import logging
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

# Logging
LOG_FILE = os.getenv("LOG_FILE_MOCK_V1", "logs/mock_v1.log")
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
    "response": {"success": True},
    "enabled": True
}


@app.route("/api/v1/charge", methods=["POST"])
def charge():
    """Mock v1 charge endpoint"""
    data = request.get_json()
    
    logger.info(f"[V1] Received charge request: {json.dumps(data)}")
    
    if not MOCK_CONFIG["enabled"]:
        logger.info("[V1] Mock disabled")
        return jsonify({"error": "Service unavailable"}), 503
    
    # Apply delay
    if MOCK_CONFIG["delay_ms"] > 0:
        logger.info(f"[V1] Applying delay: {MOCK_CONFIG['delay_ms']}ms")
        time.sleep(MOCK_CONFIG["delay_ms"] / 1000.0)
    
    response_data = MOCK_CONFIG["response"].copy()
    status_code = MOCK_CONFIG["status_code"]
    
    logger.info(f"[V1] Returning status {status_code}: {json.dumps(response_data)}")
    
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
    logger.info(f"[V1] Config updated: {json.dumps(MOCK_CONFIG)}")
    return jsonify(MOCK_CONFIG), 200


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    app.run(host="0.0.0.0", port=5001, debug=False)
