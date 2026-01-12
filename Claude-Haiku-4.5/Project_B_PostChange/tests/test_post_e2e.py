"""
E2E tests for Project B (v2 integration with fallback)
Tests payment flow with mock v2 API and webhook support
"""

import pytest
import json
import requests
import time
import subprocess
import os
import signal
import sys
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
MOCK_V1_PORT = 5001
MOCK_V2_PORT = 5002
SERVICE_POST_PORT = 5011
MOCK_V1_URL = f"http://localhost:{MOCK_V1_PORT}"
MOCK_V2_URL = f"http://localhost:{MOCK_V2_PORT}"
SERVICE_URL = f"http://localhost:{SERVICE_POST_PORT}"


def wait_for_service(url, timeout=10):
    """Wait for service to be ready"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{url}/health", timeout=1)
            if response.status_code == 200:
                return True
        except:
            time.sleep(0.5)
    return False


class TestProjectBE2E:
    """End-to-end tests for Project B"""
    
    @classmethod
    def setup_class(cls):
        """Start mocks and service"""
        # Start mock v1
        cls.mock_v1_process = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "mocks" / "mock_v1.py")],
            env={**os.environ, "LOG_FILE_MOCK_V1": str(PROJECT_ROOT / "logs" / "mock_v1.log")},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Start mock v2
        cls.mock_v2_process = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "mocks" / "mock_v2.py")],
            env={**os.environ, "LOG_FILE_MOCK_V2": str(PROJECT_ROOT / "logs" / "mock_v2.log")},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Start service (with v2 enabled)
        cls.service_process = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "src" / "service_post.py")],
            env={**os.environ, 
                 "PAYMENT_API_BASE_URL": MOCK_V2_URL,
                 "FEATURE_FLAG_USE_V2": "true",
                 "ALLOW_FALLBACK": "true",
                 "LOG_FILE": str(PROJECT_ROOT / "logs" / "log_post.txt")},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for services
        assert wait_for_service(MOCK_V1_URL), "Mock v1 failed to start"
        assert wait_for_service(MOCK_V2_URL), "Mock v2 failed to start"
        assert wait_for_service(SERVICE_URL), "Service post failed to start"
        
        time.sleep(1)
    
    @classmethod
    def teardown_class(cls):
        """Stop mocks and service"""
        for proc in [cls.mock_v1_process, cls.mock_v2_process, cls.service_process]:
            if proc:
                os.kill(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except:
                    pass
    
    def test_001_sync_authorization(self):
        """TEST_001_SYNC_AUTH"""
        # Configure mock v2 to return sync authorized
        config_response = requests.post(
            f"{MOCK_V2_URL}/mock/config",
            json={
                "delay_ms": 150,
                "status_code": 200,
                "response": {
                    "transactionId": "TXN_001_SYNC",
                    "fraudScore": 5,
                    "requiresAuth": False,
                    "status": "authorized"
                },
                "webhook": None,
                "enabled": True
            }
        )
        assert config_response.status_code == 200
        
        # Send settlement request
        response = requests.post(
            f"{SERVICE_URL}/api/settle",
            json={
                "orderId": "O001",
                "amount": 10000,
                "paymentMethod": "card",
                "currency": "USD",
                "countryCode": "US"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "authorized"
        assert data["transactionId"] == "TXN_001_SYNC"
        assert data["fraudScore"] == 5
        assert data["requiresAuth"] == False
        
        # Verify stored record
        settlement_id = data["settlementId"]
        record_response = requests.get(f"{SERVICE_URL}/api/settlements/{settlement_id}")
        assert record_response.status_code == 200
        record = record_response.json()
        assert record["status"] == "authorized"
        assert record["transactionId"] == "TXN_001_SYNC"
    
    def test_002_3ds_required_with_webhook(self):
        """TEST_002_3DS_REQUIRED"""
        # Configure mock v2 to return 3DS required + webhook
        config_response = requests.post(
            f"{MOCK_V2_URL}/mock/config",
            json={
                "delay_ms": 100,
                "status_code": 200,
                "response": {
                    "transactionId": "TXN_002_3DS",
                    "fraudScore": 15,
                    "requiresAuth": True,
                    "status": "pending_auth",
                    "authUrl": "https://payment-gateway.example.com/3ds/TXN_002_3DS"
                },
                "webhook": {
                    "delay_ms": 2000,
                    "event": "payment.authorized",
                    "data": {
                        "event": "payment.authorized",
                        "status": "authorized",
                        "fraudScore": 12
                    }
                },
                "enabled": True
            }
        )
        assert config_response.status_code == 200
        
        # Set webhook callback URL
        callback_response = requests.post(
            f"{MOCK_V2_URL}/mock/webhook-callback",
            json={"callbackUrl": f"{SERVICE_URL}/webhook/payments"}
        )
        assert callback_response.status_code == 200
        
        # Send settlement request
        response = requests.post(
            f"{SERVICE_URL}/api/settle",
            json={
                "orderId": "O002",
                "amount": 50000,
                "paymentMethod": "card",
                "currency": "USD",
                "countryCode": "GB"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending_auth"
        assert data["requiresAuth"] == True
        assert data["transactionId"] == "TXN_002_3DS"
        
        # Wait for webhook
        time.sleep(3)
        
        # Verify settlement updated via webhook
        settlement_id = data["settlementId"]
        record_response = requests.get(f"{SERVICE_URL}/api/settlements/{settlement_id}")
        assert record_response.status_code == 200
        record = record_response.json()
        assert record.get("webhook_received") == True
        assert record.get("final_status") == "authorized"
    
    def test_003_async_pending(self):
        """TEST_003_ASYNC_PENDING"""
        # Configure mock v2 to return async pending + webhook
        config_response = requests.post(
            f"{MOCK_V2_URL}/mock/config",
            json={
                "delay_ms": 200,
                "status_code": 202,
                "response": {
                    "transactionId": "TXN_003_ASYNC",
                    "fraudScore": 8,
                    "requiresAuth": False,
                    "status": "pending_confirmation"
                },
                "webhook": {
                    "delay_ms": 3000,
                    "event": "payment.confirmed",
                    "data": {
                        "event": "payment.confirmed",
                        "status": "authorized",
                        "fraudScore": 8
                    }
                },
                "enabled": True
            }
        )
        assert config_response.status_code == 200
        
        # Send settlement request
        response = requests.post(
            f"{SERVICE_URL}/api/settle",
            json={
                "orderId": "O003",
                "amount": 25000,
                "paymentMethod": "card",
                "currency": "EUR",
                "countryCode": "DE"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending_confirmation"
        
        # Wait for webhook
        time.sleep(4)
        
        # Verify settlement updated
        settlement_id = data["settlementId"]
        record_response = requests.get(f"{SERVICE_URL}/api/settlements/{settlement_id}")
        record = record_response.json()
        assert record.get("webhook_received") == True
    
    def test_004_v2_error_fallback(self):
        """TEST_004_V2_ERROR_FALLBACK"""
        # Configure v2 to return error
        requests.post(
            f"{MOCK_V2_URL}/mock/config",
            json={
                "status_code": 500,
                "response": {"error": "Internal server error"},
                "enabled": True
            }
        )
        
        # Configure v1 to return success
        requests.post(
            f"{MOCK_V1_URL}/mock/config",
            json={
                "status_code": 200,
                "response": {"success": True},
                "enabled": True
            }
        )
        
        # Send settlement request
        response = requests.post(
            f"{SERVICE_URL}/api/settle",
            json={
                "orderId": "O004",
                "amount": 15000,
                "paymentMethod": "card",
                "currency": "USD",
                "countryCode": "US"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fallback_success"
        assert data["fallback_reason"] == "v2_error"
    
    def test_005_fraud_decline(self):
        """TEST_005_FRAUD_DECLINE"""
        # Configure v2 to return fraud decline
        config_response = requests.post(
            f"{MOCK_V2_URL}/mock/config",
            json={
                "delay_ms": 100,
                "status_code": 200,
                "response": {
                    "transactionId": "TXN_005_FRAUD",
                    "fraudScore": 92,
                    "requiresAuth": False,
                    "status": "declined",
                    "declineReason": "high_fraud_risk"
                },
                "webhook": None,
                "enabled": True
            }
        )
        assert config_response.status_code == 200
        
        # Send settlement request
        response = requests.post(
            f"{SERVICE_URL}/api/settle",
            json={
                "orderId": "O005",
                "amount": 100000,
                "paymentMethod": "card",
                "currency": "USD",
                "countryCode": "RU"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "declined"
        assert data["transactionId"] == "TXN_005_FRAUD"
        assert data["fraudScore"] == 92
