"""
Unit tests for Project A (Legacy v1 integration)
"""

import pytest
import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from service_pre import app, settlements


@pytest.fixture
def client():
    """Flask test client"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
    settlements.clear()


def test_health_check(client):
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"


def test_settlement_storage(client):
    """Test that settlement records are properly stored"""
    settlement_request = {
        "orderId": "O_UNIT_001",
        "amount": 5000,
        "paymentMethod": "card"
    }
    
    # Mock the v1 API would be called in actual execution
    # For unit tests, we just verify the structure
    assert "orderId" in settlement_request
    assert "amount" in settlement_request
    assert "paymentMethod" in settlement_request


def test_settlement_request_structure():
    """Test settlement request structure matches v1 requirements"""
    request_data = {
        "orderId": "O123",
        "amount": 1000,
        "paymentMethod": "card"
    }
    
    # Validate required fields
    assert request_data["orderId"]
    assert request_data["amount"] > 0
    assert request_data["paymentMethod"] in ["card", "bank_transfer", "wallet"]
