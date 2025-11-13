"""
Project A - Legacy Settlement Service
Calls POST /api/v1/charge with minimal field mapping
Returns simple success boolean
"""

import os
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuration
API_BASE_URL = os.getenv("PAYMENT_API_BASE_URL", "http://localhost:5001")
TIMEOUT = int(os.getenv("TIMEOUT", "10"))
LOG_FILE = os.getenv("LOG_FILE", "logs/log_pre.txt")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# In-memory settlement records
settlements = {}


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/settle", methods=["POST"])
def settle():
    """
    Legacy settlement endpoint - accepts order info and calls v1/charge
    Request: {"orderId": "...", "amount": ..., "paymentMethod": "..."}
    Response: {"success": true/false, "settlementId": "..."}
    """
    data = request.get_json()
    settlement_id = str(uuid.uuid4())
    
    logger.info(f"[SETTLE] Received settlement request: {json.dumps(data)}")
    
    # Build v1 request - minimal fields
    v1_payload = {
        "orderId": data.get("orderId"),
        "amount": data.get("amount"),
        "paymentMethod": data.get("paymentMethod")
    }
    
    logger.info(f"[SETTLE] Calling v1 API with payload: {json.dumps(v1_payload)}")
    
    try:
        v1_url = f"{API_BASE_URL}/api/v1/charge"
        response = requests.post(
            v1_url,
            json=v1_payload,
            timeout=TIMEOUT
        )
        response.raise_for_status()
        v1_response = response.json()
        
        logger.info(f"[SETTLE] v1 response: {json.dumps(v1_response)}")
        
        # Store settlement record
        success = v1_response.get("success", False)
        settlement_record = {
            "settlementId": settlement_id,
            "orderId": data.get("orderId"),
            "amount": data.get("amount"),
            "status": "success" if success else "failed",
            "success": success,
            "timestamp": datetime.utcnow().isoformat(),
            "v1_response": v1_response
        }
        settlements[settlement_id] = settlement_record
        logger.info(f"[SETTLE] Stored settlement record: {json.dumps(settlement_record)}")
        
        return jsonify({
            "settlementId": settlement_id,
            "success": success,
            "orderId": data.get("orderId")
        }), 200
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[SETTLE] Error calling v1 API: {str(e)}")
        settlement_record = {
            "settlementId": settlement_id,
            "orderId": data.get("orderId"),
            "amount": data.get("amount"),
            "status": "error",
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
        settlements[settlement_id] = settlement_record
        return jsonify({
            "settlementId": settlement_id,
            "success": False,
            "error": str(e)
        }), 500
    except Exception as e:
        logger.error(f"[SETTLE] Unexpected error: {str(e)}")
        return jsonify({
            "settlementId": settlement_id,
            "success": False,
            "error": "Internal server error"
        }), 500


@app.route("/api/settlements/<settlement_id>", methods=["GET"])
def get_settlement(settlement_id):
    """Retrieve stored settlement record"""
    if settlement_id in settlements:
        return jsonify(settlements[settlement_id]), 200
    return jsonify({"error": "Settlement not found"}), 404


@app.route("/api/settlements", methods=["GET"])
def list_settlements():
    """List all settlement records"""
    return jsonify({"settlements": list(settlements.values())}), 200


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    app.run(host="0.0.0.0", port=5010, debug=False)
