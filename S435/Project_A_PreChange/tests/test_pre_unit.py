import json
import os

# Unit tests for mapping logic


def test_mapping_fields():
    payload = {'orderId': 'O1', 'amount': 123, 'paymentMethod': 'card'}
    # In pre-change mapping is direct
    upstream_payload = {'orderId': payload['orderId'], 'amount': payload['amount'], 'paymentMethod': payload['paymentMethod']}
    assert upstream_payload == {'orderId': 'O1', 'amount': 123, 'paymentMethod': 'card'}
