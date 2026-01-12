"""
E2E tests for Project A (Legacy v1 integration)
Tests payment flow with mock v1 API
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
SERVICE_PRE_PORT = 5010
MOCK_V1_URL = f"http://localhost:{MOCK_V1_PORT}"
SERVICE_URL = f"http://localhost:{SERVICE_PRE_PORT}"

# Test data
TEST_DATA_PATH = Path(__file__).parent.parent.parent / "test_data.json"


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


class TestProjectAE2E:
    """End-to-end tests for Project A"""
    
    @classmethod
    def setup_class(cls):
        """Start mock and service"""
        # Start mock v1
        cls.mock_v1_process = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "mocks" / "mock_v1.py")],
            env={**os.environ, "LOG_FILE_MOCK_V1": str(PROJECT_ROOT / "logs" / "mock_v1.log")},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Start service
        cls.service_process = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "src" / "service_pre.py")],
            env={**os.environ, 
                 "PAYMENT_API_BASE_URL": MOCK_V1_URL,
                 "LOG_FILE": str(PROJECT_ROOT / "logs" / "log_pre.txt")},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for services
        assert wait_for_service(MOCK_V1_URL), "Mock v1 failed to start"
        assert wait_for_service(SERVICE_URL), "Service pre failed to start"
        
        time.sleep(1)  # Extra wait
    
    @classmethod
    def teardown_class(cls):
        """Stop mock and service"""
        for proc in [cls.mock_v1_process, cls.service_process]:
            if proc:
                os.kill(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
    
    def test_sync_authorization(self):
        """TEST_001_SYNC_AUTH"""
        # Configure mock to return success
        config_response = requests.post(
            f"{MOCK_V1_URL}/mock/config",
            json={
                "delay_ms": 100,
                "status_code": 200,
                "response": {"success": True},
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
                "paymentMethod": "card"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "settlementId" in data
        
        # Verify stored record
        settlement_id = data["settlementId"]
        record_response = requests.get(f"{SERVICE_URL}/api/settlements/{settlement_id}")
        assert record_response.status_code == 200
        record = record_response.json()
        assert record["status"] == "success"
        assert record["orderId"] == "O001"
    
    def test_v1_error_handling(self):
        """Test error handling when v1 returns error"""
        # Configure mock to return error
        requests.post(
            f"{MOCK_V1_URL}/mock/config",
            json={
                "delay_ms": 50,
                "status_code": 500,
                "response": {"error": "Internal server error"},
                "enabled": True
            }
        )
        
        # Send settlement request
        response = requests.post(
            f"{SERVICE_URL}/api/settle",
            json={
                "orderId": "O002",
                "amount": 5000,
                "paymentMethod": "card"
            }
        )
        
        # Should return 500
        assert response.status_code == 500
        data = response.json()
        assert data["success"] == False
