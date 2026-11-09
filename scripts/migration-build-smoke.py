#!/usr/bin/env python3
"""Check that adding only a migration invalidates an incremental Rust build."""
import http.client
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time

BACKEND = Path(__file__).resolve().parents[1] / "templates/light/backend"


def main():
    with tempfile.TemporaryDirectory(prefix="kitternel-migration-build-") as temporary:
        directory = Path(temporary)
        backend = directory / "backend"
        backend.mkdir()
        for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "build.rs"):
            if (BACKEND / name).exists():
                shutil.copy2(BACKEND / name, backend / name)
        for name in ("src", "migrations"):
            shutil.copytree(BACKEND / name, backend / name)
        environment = os.environ.copy()
        environment["CARGO_TARGET_DIR"] = str(directory / "target")
        # All dependencies/toolchains must already be installed by the normal build.
        with open(directory / "build.log", "w+") as log:
            for adding_migration in (False, True):
                if adding_migration:
                    version = max(int(path.name.split("_", 1)[0]) for path in (backend / "migrations").glob("*.sql")) + 1
                    (backend / "migrations" / f"{version:04}_build_probe.sql").write_text(
                        "CREATE TABLE incremental_build_probe (id INTEGER PRIMARY KEY);\n")
                result = subprocess.run(["cargo", "build", "--locked", "--offline", "--jobs", "4"],
                                        cwd=backend, env=environment, stdout=log, stderr=log, timeout=180)
                if result.returncode:
                    log.seek(0)
                    raise RuntimeError(f"Migration build failed:\n{log.read()}")
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            public = directory / "public"
            public.mkdir()
            (public / "index.html").write_text("<!doctype html><title>Migration test</title>")
            database = directory / "test.db"
            environment.update(PORT=str(port), SQLITE_PATH=str(database), FRONTEND_DIR=str(public),
                               MAX_CONNECTIONS="4", HTTP_HEADER_TIMEOUT_SECS="2", SHUTDOWN_TIMEOUT_SECS="2")
            process = subprocess.Popen([str(directory / "target/debug/kitternel-light")],
                                       env=environment, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                        connection.request("GET", "/health/ready")
                        response = connection.getresponse()
                        status = response.status
                        response.read()
                        connection.close()
                        if status == 200:
                            break
                    except OSError:
                        pass
                    if process.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        raise RuntimeError(f"Migration test backend did not become ready:\n{log.read()}")
                    time.sleep(0.05)
                with sqlite3.connect(database) as connection:
                    table = connection.execute("SELECT name FROM sqlite_master WHERE name = ?", ("incremental_build_probe",)).fetchone()
                    migration = connection.execute("SELECT success FROM _sqlx_migrations WHERE version = ?", (version,)).fetchone()
                    if table is None or migration != (1,):
                        raise AssertionError("Adding only a SQL file did not update the embedded migrations")
                print("Incremental migration build: new SQL file was embedded and applied.")
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
