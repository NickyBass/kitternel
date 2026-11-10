#!/usr/bin/env python3
"""Exercise the built backend over TCP and verify process lifecycle behavior."""
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import tempfile
import sqlite3
import unittest

from smoke_paths import backend_binary

BACKEND = Path(__file__).resolve().parents[1] / "templates/light/backend"


class BackendSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def start(self, **overrides):
        environment = os.environ.copy()
        environment.update(PORT="8080", LOG_LEVEL="info", SHUTDOWN_TIMEOUT_SECS="2", MAX_CONNECTIONS="128", HTTP_HEADER_TIMEOUT_SECS="1")
        environment.update(SQLITE_PATH=str(Path(self.directory.name) / "test.db"),
                           FRONTEND_DIR=str(BACKEND.parent / "frontend/dist"))
        environment.update(overrides)
        process = subprocess.Popen(
            [str(backend_binary(BACKEND))], env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(self.cleanup_process, process)
        return process

    @staticmethod
    def cleanup_process(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)

    def test_http_and_sigterm(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        process = self.start(PORT=str(port))
        deadline = time.monotonic() + 10
        while True:
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                connection.request("GET", "/health/live")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read()), {"status": "ok"})
                connection.close()
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail("backend did not become live")
                time.sleep(0.05)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("GET", "/api/hello")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read()), {"message": "Hello from Kitternel Light."})
        connection.close()
        with socket.create_connection(("127.0.0.1", port), timeout=3) as slow:
            slow.sendall(b"GET /health/live HTTP/1.1\r\nHost: localhost\r\n")
            reply = slow.recv(1024)
            self.assertTrue(not reply or reply.startswith(b"HTTP/1.1 408"))
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stderr)
        records = [json.loads(line) for line in stdout.splitlines()]
        messages = [record["fields"]["message"] for record in records]
        self.assertIn("server listening", messages)
        self.assertIn("shutdown requested", messages)
        self.assertIn("server stopped", messages)

    def test_invalid_configuration_does_not_leak_values(self):
        for name in ("PORT", "LOG_LEVEL", "SHUTDOWN_TIMEOUT_SECS", "MAX_CONNECTIONS", "HTTP_HEADER_TIMEOUT_SECS"):
            with self.subTest(variable=name):
                process = self.start(**{name: "private-secret-value"})
                stdout, stderr = process.communicate(timeout=5)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn(name, stderr)
                self.assertNotIn("private-secret-value", stdout + stderr)

    def test_sqlite_memory_uris_are_rejected_without_echoing_the_path(self):
        for path in (":memory:", "file::memory:?cache=shared", "file:private-secret?mode=memory&cache=shared"):
            with self.subTest(path=path):
                process = self.start(SQLITE_PATH=path)
                stdout, stderr = process.communicate(timeout=5)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn("SQLITE_PATH", stderr)
                self.assertNotIn(path, stdout + stderr)

    def test_migration_failures_log_safe_distinct_diagnostics(self):
        bad = Path(self.directory.name) / "private-schema.db"
        with sqlite3.connect(bad) as connection:
            connection.execute("CREATE TABLE greetings (private_column TEXT)")
        process = self.start(SQLITE_PATH=str(bad))
        stdout, stderr = process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        fields = next(json.loads(line)["fields"] for line in stdout.splitlines()
                      if json.loads(line)["fields"].get("stage") == "migration")
        self.assertEqual(fields["category"], "execution_failed")
        self.assertEqual(fields["migration_version"], 1)
        self.assertEqual(fields["sqlite_code"], "1")
        self.assertNotIn("private-schema", stdout + stderr)
        self.assertNotIn("private_column", stdout + stderr)
        # Seed an applied migration with an intentionally wrong checksum.
        checksum = Path(self.directory.name) / "private-checksum.db"
        with sqlite3.connect(checksum) as connection:
            connection.execute("CREATE TABLE _sqlx_migrations (version BIGINT PRIMARY KEY, description TEXT NOT NULL, installed_on TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, success BOOLEAN NOT NULL, checksum BLOB NOT NULL, execution_time BIGINT NOT NULL)")
            connection.execute("INSERT INTO _sqlx_migrations (version, description, success, checksum, execution_time) VALUES (1, 'private-description', 1, X'00', 0)")
        process = self.start(SQLITE_PATH=str(checksum))
        stdout, stderr = process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        fields = next(json.loads(line)["fields"] for line in stdout.splitlines()
                      if json.loads(line)["fields"].get("stage") == "migration")
        self.assertEqual(fields["category"], "checksum_mismatch")
        self.assertEqual(fields["migration_version"], 1)
        self.assertNotIn("private-checksum", stdout + stderr)
        self.assertNotIn("private-description", stdout + stderr)

    def test_missing_frontend_fails_before_database_is_created(self):
        process = self.start(FRONTEND_DIR=self.directory.name)
        _, stderr = process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("FRONTEND_DIR", stderr)
        self.assertFalse((Path(self.directory.name) / "test.db").exists())

    def test_unwritable_database_fails(self):
        process = self.start(SQLITE_PATH=str(Path(self.directory.name)))
        _, stderr = process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("database initialization failed", stderr)

    def test_occupied_port_fails(self):
        with socket.socket() as reservation:
            reservation.bind(("0.0.0.0", 0))
            reservation.listen()
            process = self.start(PORT=str(reservation.getsockname()[1]))
            _, stderr = process.communicate(timeout=5)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("kitternel-light:", stderr)


if __name__ == "__main__":
    unittest.main()
