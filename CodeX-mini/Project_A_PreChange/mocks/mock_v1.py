import json
import threading
import time
from flask import Flask, jsonify, request

app = Flask(__name__)
behavior = {
    "status_code": 200,
    "response": {"success": True},
    "delay": 0,
}
calls = []
lock = threading.Lock()


@app.route("/api/v1/charge", methods=["POST"])
def charge():
    payload = request.get_json(force=True)
    with lock:
        calls.append(
            {
                "timestamp": time.time(),
                "payload": payload,
            }
        )
        cfg = behavior.copy()
    delay = cfg.get("delay") or 0
    if delay > 0:
        time.sleep(delay)
    return jsonify(cfg["response"]), cfg["status_code"]


@app.route("/configure", methods=["POST"])
def configure():
    data = request.get_json(force=True)
    with lock:
        behavior.update(data)
        calls.clear()
    return jsonify({"status": "configured"})


@app.route("/calls", methods=["GET"])
def get_calls():
    with lock:
        return jsonify(calls)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "mock": "v1"})


def main():
    app.run(port=5001, host="0.0.0.0", threaded=True)


if __name__ == "__main__":
    main()
