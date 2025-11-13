from typing import Any, Dict


REQUIRED_FIELDS = ["orderId", "amount", "currency", "countryCode", "paymentMethod"]


def build_v2_payload(request_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = {}
    for field in REQUIRED_FIELDS:
        if field not in request_data:
            raise KeyError(f"missing required field {field}")
        payload[field] = request_data[field]
    payload["3DS_token"] = request_data.get("3DS_token")
    return payload


def map_v2_response(response: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "transactionId": response.get("transactionId"),
        "fraudScore": response.get("fraudScore"),
        "requiresAuth": response.get("requiresAuth", False),
        "status": response.get("status"),
    }


def map_v1_response(response: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": response.get("success", False),
        "transactionId": response.get("transactionId"),
    }
