"""
Project B - Migrated Settlement Service
Calls POST /api/v2/payments/authorize with fallback to v1
Handles async webhooks and richer responses
"""

import os
import json
import logging
import uuid
import threading
from datetime import datetime
from typing import Dict, Any
import requests
from flask import Flask, request, jsonify
from adapter import PaymentAdapter, IdempotencyManager, WebhookVerifier

app = Flask(__name__)

# Configuration
API_BASE_URL = os.getenv("PAYMENT_API_BASE_URL", "http://localhost:5002")
FEATURE_FLAG_USE_V2 = os.getenv("FEATURE_FLAG_USE_V2", "true").lower() == "true"
ALLOW_FALLBACK = os.getenv("ALLOW_FALLBACK", "true").lower() == "true"
TIMEOUT = int(os.getenv("TIMEOUT", "10"))
LOG_FILE = os.getenv("LOG_FILE", "logs/log_post.txt")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "test-secret")

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

# Adapters and managers
adapter = PaymentAdapter(use_v2=FEATURE_FLAG_USE_V2, allow_fallback=ALLOW_FALLBACK)
idempotency_manager = IdempotencyManager()
webhook_verifier = WebhookVerifier(webhook_secret=WEBHOOK_SECRET)

# In-memory settlement records
settlements = {}


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/settle", methods=["POST"])
def settle():
    """
    Migrated settlement endpoint - calls v2 or falls back to v1
    Request: {"orderId": "...", "amount": ..., "paymentMethod": "...", "currency": "...", "countryCode": "..."}
    Response: {"settlementId": "...", "status": "...", "transactionId": "...", ...}
    """
    data = request.get_json()
    settlement_id = str(uuid.uuid4())
    
    # Idempotency check
    idempotency_key = data.get("idempotencyKey", settlement_id)
    if idempotency_manager.is_duplicate(idempotency_key):
        logger.info(f"[SETTLE] Duplicate request detected: {idempotency_key}")
        return jsonify(idempotency_manager.get_cached_result(idempotency_key)), 200
    
    logger.info(f"[SETTLE] Received settlement request: {json.dumps(data)}")
    
    settlement_record = {
        "settlementId": settlement_id,
        "orderId": data.get("orderId"),
        "amount": data.get("amount"),
        "timestamp": datetime.utcnow().isoformat(),
        "idempotencyKey": idempotency_key
    }
    
    if FEATURE_FLAG_USE_V2:
        # Try v2 first
        try:
            v2_result = call_v2_authorize(data, settlement_record)
            settlements[settlement_id] = v2_result["settlement_record"]
            
            # If requires webhook, register pending
            if v2_result["mapped_response"].get("requiresAuth") or v2_result["mapped_response"].get("status") in ["pending_auth", "pending_confirmation"]:
                webhook_verifier.register_pending(
                    v2_result["mapped_response"]["transactionId"],
                    data.get("orderId")
                )
                logger.info(f"[SETTLE] Transaction {v2_result['mapped_response']['transactionId']} registered for webhook")
            
            response = {
                "settlementId": settlement_id,
                "status": v2_result["mapped_response"]["status"],
                "transactionId": v2_result["mapped_response"]["transactionId"],
                "fraudScore": v2_result["mapped_response"]["fraudScore"],
                "requiresAuth": v2_result["mapped_response"]["requiresAuth"],
                "orderId": data.get("orderId")
            }
            
            idempotency_manager.cache_result(idempotency_key, response)
            return jsonify(response), 200
            
        except Exception as e:
            logger.error(f"[SETTLE] v2 call failed: {str(e)}")
            
            # Check if should fallback
            if ALLOW_FALLBACK:
                logger.info("[SETTLE] Falling back to v1...")
                try:
                    v1_result = call_v1_charge(data, settlement_record)
                    settlements[settlement_id] = v1_result["settlement_record"]
                    
                    response = {
                        "settlementId": settlement_id,
                        "status": "fallback_success",
                        "transactionId": None,
                        "fallback_reason": "v2_error",
                        "orderId": data.get("orderId"),
                        "v1_response": v1_result["v1_response"]
                    }
                    
                    idempotency_manager.cache_result(idempotency_key, response)
                    return jsonify(response), 200
                    
                except Exception as fallback_error:
                    logger.error(f"[SETTLE] v1 fallback also failed: {str(fallback_error)}")
                    settlement_record["status"] = "error"
                    settlement_record["error"] = str(fallback_error)
                    settlements[settlement_id] = settlement_record
                    
                    response = {
                        "settlementId": settlement_id,
                        "status": "error",
                        "error": str(fallback_error)
                    }
                    return jsonify(response), 500
            else:
                logger.error("[SETTLE] Fallback disabled, returning error")
                settlement_record["status"] = "error"
                settlement_record["error"] = str(e)
                settlements[settlement_id] = settlement_record
                
                return jsonify({
                    "settlementId": settlement_id,
                    "status": "error",
                    "error": str(e)
                }), 500
    else:
        # Use v1 only
        logger.info("[SETTLE] v2 feature flag disabled, using v1")
        try:
            v1_result = call_v1_charge(data, settlement_record)
            settlements[settlement_id] = v1_result["settlement_record"]
            
            response = {
                "settlementId": settlement_id,
                "status": "success" if v1_result["v1_response"].get("success") else "failed",
                "transactionId": None,
                "orderId": data.get("orderId")
            }
            
            idempotency_manager.cache_result(idempotency_key, response)
            return jsonify(response), 200
            
        except Exception as e:
            logger.error(f"[SETTLE] v1 call failed: {str(e)}")
            settlement_record["status"] = "error"
            settlement_record["error"] = str(e)
            settlements[settlement_id] = settlement_record
            
            return jsonify({
                "settlementId": settlement_id,
                "status": "error",
                "error": str(e)
            }), 500


def call_v2_authorize(order_data: Dict[str, Any], settlement_record: Dict[str, Any]) -> Dict[str, Any]:
    """Call v2 authorize endpoint"""
    v2_payload = adapter.build_v2_request(order_data)
    
    logger.info(f"[SETTLE] Calling v2 API with payload: {json.dumps(v2_payload)}")
    
    v2_url = f"{API_BASE_URL}/api/v2/payments/authorize"
    response = requests.post(
        v2_url,
        json=v2_payload,
        timeout=TIMEOUT,
        headers={"X-Idempotency-Key": settlement_record["idempotencyKey"]}
    )
    response.raise_for_status()
    v2_response = response.json()
    
    logger.info(f"[SETTLE] v2 response: {json.dumps(v2_response)}")
    
    mapped = adapter.map_v2_response(v2_response)
    
    settlement_record["status"] = mapped["status"]
    settlement_record["transactionId"] = mapped["transactionId"]
    settlement_record["fraudScore"] = mapped["fraudScore"]
    settlement_record["requiresAuth"] = mapped["requiresAuth"]
    settlement_record["v2_response"] = v2_response
    
    logger.info(f"[SETTLE] Stored settlement record: {json.dumps(settlement_record)}")
    
    return {
        "settlement_record": settlement_record,
        "mapped_response": mapped,
        "v2_response": v2_response
    }


def call_v1_charge(order_data: Dict[str, Any], settlement_record: Dict[str, Any]) -> Dict[str, Any]:
    """Call v1 charge endpoint (fallback)"""
    v1_payload = adapter.build_v1_request(order_data)
    
    logger.info(f"[SETTLE] Calling v1 API (fallback) with payload: {json.dumps(v1_payload)}")
    
    v1_url = "http://localhost:5001/api/v1/charge"
    response = requests.post(
        v1_url,
        json=v1_payload,
        timeout=TIMEOUT
    )
    response.raise_for_status()
    v1_response = response.json()
    
    logger.info(f"[SETTLE] v1 response: {json.dumps(v1_response)}")
    
    settlement_record["status"] = "success" if v1_response.get("success") else "failed"
    settlement_record["v1_response"] = v1_response
    settlement_record["fallback_used"] = True
    
    logger.info(f"[SETTLE] Stored settlement record (fallback): {json.dumps(settlement_record)}")
    
    return {
        "settlement_record": settlement_record,
        "v1_response": v1_response
    }


@app.route("/webhook/payments", methods=["POST"])
def webhook_payment():
    """
    Webhook endpoint for async payment confirmations
    Receives final status updates from v2 API
    """
    data = request.get_json()
    
    logger.info(f"[WEBHOOK] Received payment webhook: {json.dumps(data)}")
    
    transaction_id = data.get("transactionId")
    
    # Verify webhook signature (simplified)
    signature = request.headers.get("X-Webhook-Signature", "")
    if not webhook_verifier.verify_signature(json.dumps(data), signature):
        logger.warning("[WEBHOOK] Signature verification failed")
        return jsonify({"error": "Invalid signature"}), 401
    
    # Find settlement record with this transaction ID
    settlement_found = None
    for settlement_id, settlement in settlements.items():
        if settlement.get("transactionId") == transaction_id:
            settlement_found = settlement_id
            break
    
    if not settlement_found:
        logger.warning(f"[WEBHOOK] No settlement found for transaction: {transaction_id}")
        return jsonify({"error": "Transaction not found"}), 404
    
    # Update settlement record
    settlement = settlements[settlement_found]
    
    # Check for duplicate webhook (idempotency)
    if settlement.get("webhook_received"):
        logger.warning(f"[WEBHOOK] Duplicate webhook for transaction: {transaction_id}")
        return jsonify({"status": "ok"}), 200
    
    # Update status
    settlement["webhook_received"] = True
    settlement["webhook_received_at"] = datetime.utcnow().isoformat()
    settlement["final_status"] = data.get("status")
    settlement["final_fraudScore"] = data.get("fraudScore")
    settlement["webhook_data"] = data
    
    logger.info(f"[WEBHOOK] Updated settlement {settlement_found}: status={data.get('status')}")
    
    # Confirm in webhook verifier
    webhook_verifier.confirm_webhook(transaction_id, data)
    
    return jsonify({"status": "ok"}), 200


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


@app.route("/debug/idempotency", methods=["GET"])
def debug_idempotency():
    """Debug endpoint to view idempotency cache"""
    return jsonify({
        "cached_keys": list(idempotency_manager.processed_keys.keys()),
        "count": len(idempotency_manager.processed_keys)
    }), 200


if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    app.run(host="0.0.0.0", port=5011, debug=False)
