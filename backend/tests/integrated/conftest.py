import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


@pytest.fixture(scope="session")
def live_api(tmp_path_factory):
    if os.environ.get("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to use real AWS resources")
    environment = os.environ.get("ENVIRONMENT")
    if environment not in {"dev", "prod"}:
        pytest.fail("Integrated tests require an explicit dev or prod environment")
    if environment == "prod":
        url = os.environ["INTEGRATION_API_URL"]
        if not url.startswith("https://"):
            pytest.fail("Production tests require the deployed HTTPS API URL")
        with httpx.Client(base_url=url.rstrip("/"), timeout=60) as client:
            yield client
        return

    # A separate process prevents mock-suite dependency overrides from leaking into this API.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    log_path = tmp_path_factory.mktemp("live-api") / "uvicorn.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=Path(__file__).resolve().parents[2],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60) as client:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        pytest.fail(f"API exited during startup; see {log_path}")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.5)
                else:
                    pytest.fail(f"API did not start; see {log_path}")
                yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
