"""
Unit tests for Project B adapter layer
"""

import pytest
from adapter import PaymentAdapter, IdempotencyManager, WebhookVerifier


class TestPaymentAdapter:
    """Test adapter request/response mapping"""
    
    def test_build_v2_request_with_all_fields(self):
        """Test v2 request building with all fields"""
        adapter = PaymentAdapter()
        
        order_data = {
            "orderId": "O123",
            "amount": 10000,
            "paymentMethod": "card",
            "currency": "USD",
            "countryCode": "US",
            "3DS_token": None
        }
        
        v2_req = adapter.build_v2_request(order_data)
        
        assert v2_req["orderId"] == "O123"
        assert v2_req["amount"] == 10000
        assert v2_req["currency"] == "USD"
        assert v2_req["countryCode"] == "US"
        assert v2_req["paymentMethod"] == "card"
    
    def test_build_v2_request_missing_required_field(self):
        """Test v2 request with missing required field"""
        adapter = PaymentAdapter()
        
        order_data = {
            "orderId": "O123",
            "amount": 10000,
            "paymentMethod": "card"
            # Missing currency and countryCode
        }
        
        with pytest.raises(ValueError, match="Missing required v2 fields"):
            adapter.build_v2_request(order_data)
    
    def test_build_v1_request(self):
        """Test v1 request building"""
        adapter = PaymentAdapter()
        
        order_data = {
            "orderId": "O123",
            "amount": 10000,
            "paymentMethod": "card",
            "currency": "USD"
        }
        
        v1_req = adapter.build_v1_request(order_data)
        
        assert v1_req["orderId"] == "O123"
        assert v1_req["amount"] == 10000
        assert v1_req["paymentMethod"] == "card"
        assert "currency" not in v1_req  # v1 doesn't include currency
    
    def test_map_v2_response_sync(self):
        """Test mapping v2 sync response"""
        adapter = PaymentAdapter()
        
        v2_response = {
            "transactionId": "TXN123",
            "fraudScore": 15,
            "requiresAuth": False,
            "status": "authorized"
        }
        
        mapped = adapter.map_v2_response(v2_response)
        
        assert mapped["status"] == "authorized"
        assert mapped["transactionId"] == "TXN123"
        assert mapped["fraudScore"] == 15
        assert mapped["requiresAuth"] == False
    
    def test_map_v2_response_async_pending(self):
        """Test mapping v2 async pending response"""
        adapter = PaymentAdapter()
        
        v2_response = {
            "transactionId": "TXN456",
            "fraudScore": 10,
            "requiresAuth": False,
            "status": "pending_confirmation"
        }
        
        mapped = adapter.map_v2_response(v2_response)
        
        assert mapped["status"] == "pending_confirmation"
        assert mapped["transactionId"] == "TXN456"
    
    def test_map_v2_response_3ds(self):
        """Test mapping v2 3DS response"""
        adapter = PaymentAdapter()
        
        v2_response = {
            "transactionId": "TXN789",
            "fraudScore": 20,
            "requiresAuth": True,
            "status": "pending_auth",
            "authUrl": "https://example.com/3ds/TXN789"
        }
        
        mapped = adapter.map_v2_response(v2_response)
        
        assert mapped["requiresAuth"] == True
        assert mapped["authUrl"] == "https://example.com/3ds/TXN789"
    
    def test_map_v1_response(self):
        """Test mapping v1 response"""
        adapter = PaymentAdapter()
        
        v1_response = {"success": True}
        mapped = adapter.map_v1_response(v1_response)
        
        assert mapped["status"] == "authorized"
        assert mapped["transactionId"] is None
        assert mapped["fraudScore"] is None
    
    def test_map_webhook_response(self):
        """Test mapping webhook event"""
        adapter = PaymentAdapter()
        
        webhook_data = {
            "event": "payment.authorized",
            "transactionId": "TXN123",
            "status": "authorized",
            "fraudScore": 12,
            "timestamp": "2025-11-13T10:30:00Z"
        }
        
        mapped = adapter.map_webhook_response(webhook_data)
        
        assert mapped["transactionId"] == "TXN123"
        assert mapped["status"] == "authorized"
        assert mapped["fraudScore"] == 12


class TestIdempotencyManager:
    """Test idempotency handling"""
    
    def test_duplicate_detection(self):
        """Test duplicate request detection"""
        manager = IdempotencyManager()
        
        key = "idem-key-123"
        result = {"status": "ok"}
        
        manager.cache_result(key, result)
        
        assert manager.is_duplicate(key) == True
        assert manager.get_cached_result(key) == result
    
    def test_unique_request(self):
        """Test unique request (not duplicate)"""
        manager = IdempotencyManager()
        
        key = "idem-key-456"
        assert manager.is_duplicate(key) == False
        assert manager.get_cached_result(key) is None
    
    def test_cache_clear(self):
        """Test clearing cache"""
        manager = IdempotencyManager()
        
        manager.cache_result("key1", {"status": "ok"})
        manager.cache_result("key2", {"status": "ok"})
        
        manager.clear()
        
        assert manager.is_duplicate("key1") == False
        assert manager.is_duplicate("key2") == False


class TestWebhookVerifier:
    """Test webhook verification and transaction state"""
    
    def test_register_pending_transaction(self):
        """Test registering pending transaction"""
        verifier = WebhookVerifier()
        
        verifier.register_pending("TXN123", "O001")
        
        pending = verifier.get_pending_state("TXN123")
        assert pending is not None
        assert pending["orderId"] == "O001"
        assert pending["status"] == "pending"
    
    def test_confirm_webhook(self):
        """Test webhook confirmation"""
        verifier = WebhookVerifier()
        
        verifier.register_pending("TXN456", "O002")
        
        webhook_event = {
            "status": "authorized",
            "fraudScore": 10,
            "timestamp": "2025-11-13T10:30:00Z"
        }
        
        result = verifier.confirm_webhook("TXN456", webhook_event)
        
        assert result == True
        
        pending = verifier.get_pending_state("TXN456")
        assert pending["status"] == "confirmed"
        assert pending["webhookData"] == webhook_event
    
    def test_confirm_unknown_webhook(self):
        """Test confirming webhook for unknown transaction"""
        verifier = WebhookVerifier()
        
        webhook_event = {"status": "authorized"}
        result = verifier.confirm_webhook("UNKNOWN", webhook_event)
        
        assert result == False
