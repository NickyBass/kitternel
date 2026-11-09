#!/usr/bin/env python3
"""Run browser tests against an isolated real backend and compiled frontend."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "templates/light/backend"
FRONTEND = ROOT / "templates/light/frontend"


def main():
    with tempfile.TemporaryDirectory(prefix="kitternel-browser-") as temporary:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        environment = os.environ.copy()
        environment.update(PORT=str(port), SQLITE_PATH=str(Path(temporary) / "test.db"),
                           FRONTEND_DIR=str(FRONTEND / "dist"), SHUTDOWN_TIMEOUT_SECS="2")
        with open(Path(temporary) / "backend.log", "w+") as log:
            process = subprocess.Popen([str(BACKEND / "target/debug/kitternel-light")],
                                       env=environment, stdout=log, stderr=log)
            try:
                base_url = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 15
                # Keep the internal request local regardless of any inherited HTTP proxy.
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                while True:
                    try:
                        with opener.open(f"{base_url}/health/ready", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            raise RuntimeError(f"Backend did not become ready:\n{log.read()}")
                        time.sleep(0.05)
                test_environment = os.environ.copy()
                test_environment["BASE_URL"] = base_url
                result = subprocess.run(["npm", "run", "test:e2e"], cwd=FRONTEND,
                                        env=test_environment, check=False)
                if result.returncode:
                    raise SystemExit(result.returncode)
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
