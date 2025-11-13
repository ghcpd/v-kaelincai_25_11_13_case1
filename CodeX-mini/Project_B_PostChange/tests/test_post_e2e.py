import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "test_data.json"

sys.path.append(str(ROOT / "src"))


def wait_for_http(url: str, timeout: float = 10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=1)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {url}")


def load_test_cases():
    with open(DATA_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def mock_v1_server():
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "mocks" / "mock_v1.py")],
        env=os.environ.copy(),
    )
    wait_for_http("http://localhost:5101/health")
    yield {"base_url": "http://localhost:5101"}
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def mock_v2_server():
    env = os.environ.copy()
    env["WEBHOOK_ENDPOINT"] = "http://localhost:6102/webhook/payments"
    env["WEBHOOK_SECRET"] = "test-secret"
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "mocks" / "mock_v2.py")],
        env=env,
    )
    wait_for_http("http://localhost:6101/health")
    yield {"base_url": "http://localhost:6101", "secret": env["WEBHOOK_SECRET"]}
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def settlement_service(mock_v1_server, mock_v2_server):
    env = os.environ.copy()
    env["PAYMENT_API_BASE_URL"] = mock_v2_server["base_url"]
    env["LEGACY_PAYMENT_API_BASE_URL"] = mock_v1_server["base_url"]
    env["SETTLEMENT_PORT"] = "6102"
    env["FEATURE_FLAG_USE_V2"] = "true"
    env["FALLBACK_ENABLED"] = "true"
    env["WEBHOOK_SECRET"] = mock_v2_server["secret"]
    env["PAYMENT_TIMEOUT"] = "2"
    env["PAYMENT_RETRY_COUNT"] = "2"
    env["LOG_FILE"] = str(ROOT / "logs" / "log_post.txt")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "src" / "service_post.py")],
        env=env,
    )
    wait_for_http("http://localhost:6102/health")
    yield {"url": "http://localhost:6102", "webhook_secret": env["WEBHOOK_SECRET"]}
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def results_writer(settlement_service):
    results = []
    yield results
    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tests": results,
    }
    with open(results_dir / "results_post.json", "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)
    events_resp = requests.get(settlement_service["url"] + "/events", timeout=5)
    with open(results_dir / "webhook_event_log.json", "w", encoding="utf-8") as fh:
        json.dump(events_resp.json(), fh, indent=2)


def configure_mock(server_url: str, config: dict):
    requests.post(f"{server_url}/configure", json=config, timeout=3)


def capture_calls(server_url: str):
    resp = requests.get(f"{server_url}/calls", timeout=3)
    return resp.json()


def poll_record(url: str, order_id: str, expected_status: str, timeout: float = 8):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = requests.get(f"{url}/records/{order_id}", timeout=3)
        if resp.status_code == 200:
            record = resp.json()
            last = record
            if record["status"] == expected_status:
                return record
            if expected_status == "authorized" and record["status"] in ("authorized", "declined"):
                return record
        time.sleep(0.2)
    if last:
        return last
    raise RuntimeError("record polling failed")


@pytest.mark.parametrize("case", load_test_cases())
def test_post_e2e_case(
    case, settlement_service, mock_v1_server, mock_v2_server, results_writer
):
    v1_config = case.get("mock_v1", {})
    configure_mock(mock_v1_server["base_url"], v1_config)
    v2_config = dict(case.get("mock_v2", {}))
    if "webhook" not in v2_config:
        v2_config["webhook"] = None
    configure_mock(mock_v2_server["base_url"], v2_config)

    start = time.time()
    resp = requests.post(
        settlement_service["url"] + "/settle", json=case["input"], timeout=5
    )
    duration = time.time() - start
    assert resp.status_code == 200

    expected_status = case["expected_post"]["status"]
    record = poll_record(settlement_service["url"], case["input"]["orderId"], expected_status)

    expected = case["expected_post"]
    if expected.get("transaction_id") is not None:
        assert record["transactionId"] == expected["transaction_id"]
    assert record["status"] == expected["status"]

    result = {
        "test_id": case["test_id"],
        "duration": duration,
        "input": case["input"],
        "calls_to_v2": capture_calls(mock_v2_server["base_url"]),
        "calls_to_v1": capture_calls(mock_v1_server["base_url"]),
        "retries": record.get("attempts", 0),
        "webhook_received": record.get("webhook_received", False),
        "final_status": record["status"],
        "transaction_id": record.get("transactionId"),
        "fraud_score": record.get("fraudScore"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    results_writer.append(result)
