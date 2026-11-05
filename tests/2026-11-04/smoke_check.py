"""Smoke check run by ``make smoke`` (not collected by pytest).

Starts the real app with uvicorn on 127.0.0.1 and simulated instruments,
runs a short sweep over HTTP, checks the returned data and the saved file,
then stops the server.
"""

import json
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

from app.api import create_app
from app.config import PROJECT_ROOT, AppConfig, resolve_data_dir

HOST = "127.0.0.1"


def request(base: str, path: str, payload: dict | None = None) -> tuple[int, bytes]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        base + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, response.read()


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    data_dir = resolve_data_dir(f".cache/smoke-data/{stamp}")
    env_config = AppConfig.from_env()
    config = AppConfig(**{**env_config.__dict__, "data_dir": data_dir})
    app = create_app(config)
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            print("smoke: server did not start")
            return 1
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://{HOST}:{port}"
    try:
        status, page = request(base, "/")
        assert status == 200 and b"FMR acquisition" in page, "page not served"
        status, plotly = request(base, "/vendor/plotly.min.js")
        assert status == 200 and len(plotly) > 100_000, "Plotly not served"

        settings = {
            "frequencies_ghz": [10.0],
            "aux_begin_v": -2.7,
            "aux_end_v": -2.9,
            "aux_step_v": 0.004,
            "step_wait_ms": 0,
            "ramp_wait_ms": 0,
            "saturate_wait_ms": 0,
            "zero_wait_ms": 0,
            "file_prefix": "smoke",
        }
        status, body = request(base, "/api/runs", settings)
        assert status == 201, f"run not created: {status}"
        run_id = json.loads(body)["run_id"]
        deadline = time.monotonic() + 30
        while True:
            _, body = request(base, f"/api/runs/{run_id}")
            run = json.loads(body)
            if run["state"] != "running":
                break
            if time.monotonic() > deadline:
                print("smoke: run did not finish")
                return 1
            time.sleep(0.1)
        assert run["state"] == "finished", f"run ended {run['state']}: {run['error']}"
        assert run["next_index"] == 51, f"expected 51 points, got {run['next_index']}"
        signal = [p["signal_x_v"] for p in run["points"]]
        assert max(signal) > 0 > min(signal), "no resonance in simulated data"
        saved = Path(data_dir) / run["sweeps"][0]["file_name"]
        rows = saved.read_text().splitlines()
        assert len(rows) == 51, "saved file has the wrong number of rows"
    except AssertionError as exc:
        print(f"smoke: FAILED: {exc}")
        return 1
    finally:
        server.should_exit = True
        thread.join(10)
    where = saved.relative_to(PROJECT_ROOT)
    print(f"smoke: passed ({len(rows)} points saved to {where})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
