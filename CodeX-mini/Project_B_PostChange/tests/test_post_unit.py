import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from adapter import build_v2_payload, map_v1_response, map_v2_response  # noqa: E402


def test_build_v2_payload_requires_fields():
    payload = {
        "orderId": "X",
        "amount": 100,
        "currency": "USD",
        "countryCode": "US",
        "paymentMethod": "card",
        "3DS_token": "token",
    }
    built = build_v2_payload(payload)
    assert built["orderId"] == "X"
    assert built["currency"] == "USD"
    assert built["3DS_token"] == "token"


@pytest.mark.parametrize("missing_field", ["orderId", "amount", "currency"])
def test_build_v2_payload_missing_fields_raises(missing_field):
    payload = {
        "orderId": "X",
        "amount": 100,
        "currency": "USD",
        "countryCode": "US",
        "paymentMethod": "card",
    }
    payload.pop(missing_field)
    with pytest.raises(KeyError):
        build_v2_payload(payload)


def test_map_v2_response_extracts_values():
    response = {
        "transactionId": "T123",
        "fraudScore": 5,
        "requiresAuth": True,
        "status": "pending",
    }
    mapped = map_v2_response(response)
    assert mapped["transactionId"] == "T123"
    assert mapped["requiresAuth"] is True


def test_map_v1_response_handles_success_and_failure():
    assert map_v1_response({"success": True})["success"] is True
    assert map_v1_response({"success": False})["success"] is False
