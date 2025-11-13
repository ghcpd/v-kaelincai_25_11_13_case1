import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from service_pre import build_v1_payload  # noqa: E402


def test_build_v1_payload_matches_contract():
    payload = {"orderId": "O-UNIT", "amount": 5000, "paymentMethod": "card"}
    expected = {
        "orderId": "O-UNIT",
        "amount": 5000,
        "paymentMethod": "card",
    }
    assert build_v1_payload(payload) == expected


@pytest.mark.parametrize("missing_field", ["orderId", "amount", "paymentMethod"])
def test_settle_requires_fields(missing_field):
    payload = {"orderId": "O-UNIT", "amount": 5000, "paymentMethod": "card"}
    payload.pop(missing_field)
    with pytest.raises(KeyError):
        build_v1_payload(payload)
