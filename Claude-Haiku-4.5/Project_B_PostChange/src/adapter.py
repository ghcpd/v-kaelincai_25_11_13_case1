"""
Adapter layer for v1 and v2 payment APIs
Handles request/response transformation and fallback logic
"""

import logging
from typing import Dict, Any, Optional, Tuple
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class PaymentAdapter:
    """
    Adapter that handles both v1 and v2 payment APIs
    Provides transparent fallback and request/response mapping
    """
    
    def __init__(self, use_v2: bool = True, allow_fallback: bool = True):
        self.use_v2 = use_v2
        self.allow_fallback = allow_fallback
    
    def build_v1_request(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform order data to v1 request format"""
        return {
            "orderId": order_data.get("orderId"),
            "amount": order_data.get("amount"),
            "paymentMethod": order_data.get("paymentMethod")
        }
    
    def build_v2_request(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform order data to v2 request format"""
        # v2 requires additional fields
        v2_payload = {
            "orderId": order_data.get("orderId"),
            "amount": order_data.get("amount"),
            "currency": order_data.get("currency", "USD"),
            "countryCode": order_data.get("countryCode", "US"),
            "paymentMethod": order_data.get("paymentMethod"),
            "3DS_token": order_data.get("3DS_token")
        }
        
        # Validate required v2 fields
        required_fields = ["orderId", "amount", "currency", "countryCode", "paymentMethod"]
        missing_fields = [f for f in required_fields if not v2_payload.get(f)]
        
        if missing_fields:
            raise ValueError(f"Missing required v2 fields: {missing_fields}")
        
        return v2_payload
    
    def map_v1_response(self, v1_response: Dict[str, Any]) -> Dict[str, Any]:
        """Map v1 response to normalized format"""
        return {
            "status": "authorized" if v1_response.get("success") else "declined",
            "transactionId": None,  # v1 doesn't return transactionId
            "fraudScore": None,
            "requiresAuth": False,
            "v1_raw": v1_response
        }
    
    def map_v2_response(self, v2_response: Dict[str, Any]) -> Dict[str, Any]:
        """Map v2 response to normalized format"""
        return {
            "status": v2_response.get("status", "unknown"),
            "transactionId": v2_response.get("transactionId"),
            "fraudScore": v2_response.get("fraudScore"),
            "requiresAuth": v2_response.get("requiresAuth", False),
            "declineReason": v2_response.get("declineReason"),
            "authUrl": v2_response.get("authUrl"),
            "v2_raw": v2_response
        }
    
    def map_webhook_response(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map v2 webhook event to settlement update"""
        return {
            "transactionId": webhook_data.get("transactionId"),
            "status": webhook_data.get("status"),
            "fraudScore": webhook_data.get("fraudScore"),
            "timestamp": webhook_data.get("timestamp"),
            "webhook_event": webhook_data.get("event")
        }
    
    def validate_idempotency_key(self, idempotency_key: str) -> bool:
        """Validate idempotency key format"""
        try:
            uuid.UUID(idempotency_key)
            return True
        except (ValueError, TypeError):
            return False
    
    def should_fallback(self, error: Exception, reason: str) -> bool:
        """Determine if fallback to v1 should occur"""
        if not self.allow_fallback:
            return False
        
        # Fallback on specific errors
        fallback_reasons = ["v2_error_500", "v2_timeout", "v2_unavailable"]
        return reason in fallback_reasons


class IdempotencyManager:
    """Manages idempotent payment requests"""
    
    def __init__(self):
        self.processed_keys = {}  # key -> result
    
    def is_duplicate(self, idempotency_key: str) -> bool:
        """Check if request was already processed"""
        return idempotency_key in self.processed_keys
    
    def get_cached_result(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached result for duplicate request"""
        return self.processed_keys.get(idempotency_key)
    
    def cache_result(self, idempotency_key: str, result: Dict[str, Any]):
        """Cache result for idempotency"""
        self.processed_keys[idempotency_key] = result
    
    def clear(self):
        """Clear cache (for testing)"""
        self.processed_keys.clear()


class WebhookVerifier:
    """Verifies webhook authenticity and handles concurrent webhook events"""
    
    def __init__(self, webhook_secret: str = "test-secret"):
        self.webhook_secret = webhook_secret
        self.pending_transactions = {}  # transactionId -> pending_state
    
    def verify_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature (simplified for testing)"""
        # In production, use HMAC-SHA256
        return True
    
    def register_pending(self, transaction_id: str, order_id: str):
        """Register transaction pending webhook confirmation"""
        self.pending_transactions[transaction_id] = {
            "orderId": order_id,
            "registeredAt": datetime.utcnow().isoformat(),
            "status": "pending"
        }
    
    def confirm_webhook(self, transaction_id: str, webhook_event: Dict[str, Any]) -> bool:
        """Confirm transaction via webhook"""
        if transaction_id not in self.pending_transactions:
            logger.warning(f"Webhook for unknown transaction: {transaction_id}")
            return False
        
        self.pending_transactions[transaction_id].update({
            "status": "confirmed",
            "confirmedAt": datetime.utcnow().isoformat(),
            "webhookData": webhook_event
        })
        return True
    
    def get_pending_state(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Get pending transaction state"""
        return self.pending_transactions.get(transaction_id)
