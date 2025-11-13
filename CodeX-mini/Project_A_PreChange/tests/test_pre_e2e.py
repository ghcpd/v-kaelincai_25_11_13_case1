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


def load_test_cases():
    with open(DATA_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def wait_for_http(url, timeout=10):
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


@pytest.fixture(scope="session")
def mock_v1_server():
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "mocks" / "mock_v1.py")],
        env=env,
    )
    wait_for_http("http://localhost:5001/health")
    yield {"base_url": "http://localhost:5001"}
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def settlement_service(mock_v1_server):
    env = os.environ.copy()
    env["PAYMENT_API_BASE_URL"] = mock_v1_server["base_url"]
    env["SETTLEMENT_PORT"] = "5002"
    env["PAYMENT_TIMEOUT"] = "2"
    env["PAYMENT_RETRY_COUNT"] = "2"
    env["LOG_FILE"] = str(ROOT / "logs" / "log_pre.txt")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "src" / "service_pre.py")],
        env=env,
    )
    wait_for_http("http://localhost:5002/health")
    yield {"url": "http://localhost:5002"}
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def results_writer():
    results = []

    yield results

    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tests": results,
    }
    with open(results_dir / "results_pre.json", "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)


def configure_mock_v1(case):
    config = case.get("mock_v1", {})
    requests.post(
        "http://localhost:5001/configure",
        json=config,
        timeout=3,
    )


def capture_upstream_calls():
    resp = requests.get("http://localhost:5001/calls", timeout=3)
    return resp.json()


@pytest.mark.parametrize("case", load_test_cases())
def test_pre_e2e_case(case, settlement_service, mock_v1_server, results_writer):
    configure_mock_v1(case)
    url = settlement_service["url"] + "/settle"
    payload = case["input"]
    start_ts = time.time()
    resp = requests.post(url, json=payload, timeout=5)
    duration = time.time() - start_ts
    assert resp.status_code in (200, 502)
    record_resp = requests.get(
        settlement_service["url"] + f"/records/{payload['orderId']}", timeout=3
    )
    assert record_resp.status_code == 200
    record = record_resp.json()
    expected = case.get("expected_pre", {})
    if expected:
        assert record["status"] == expected["status"]
        if expected.get("transaction_id"):
            assert record["transactionId"] == expected["transaction_id"]
    result = {
        "test_id": case["test_id"],
        "duration": duration,
        "input": payload,
        "calls_to_upstream": capture_upstream_calls(),
        "retries": record.get("attempts", 0),
        "webhook_received": False,
        "final_status": record["status"],
        "transaction_id": record.get("transactionId"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    results_writer.append(result)
