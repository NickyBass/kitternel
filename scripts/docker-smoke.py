#!/usr/bin/env python3
"""Validate a built Light image using only uniquely named disposable resources."""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "kitternel-light:local"


def docker(*arguments, check=True, environment=None):
    namespace = (os.environ if environment is None else environment).get("SMOKE_RUN_ID")
    if namespace and arguments and arguments[0] in ("run", "create"):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", namespace):
            raise ValueError("SMOKE_RUN_ID must be a lowercase resource identifier of at most 64 characters")
        # Label even unnamed one-off helpers so an interrupted suite can be cleaned up.
        arguments = (arguments[0], "--label", f"io.starter.smoke-run={namespace}", *arguments[1:])
    return subprocess.run(["docker", *arguments], text=True, capture_output=True,
                          check=check, env=environment, timeout=90)


def inspect(name):
    return json.loads(docker("inspect", name).stdout)[0]


def http_request(port, path, accept="application/json"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path, headers={"Accept": accept})
        response = connection.getresponse()
        return response.status, response.read(), response.headers
    finally:
        connection.close()


class DockerSmoke(unittest.TestCase):
    def setUp(self):
        self.prefix = f"kitternel-smoke-{uuid.uuid4().hex[:12]}"
        self.containers = []
        self.volume = f"{self.prefix}-data"
        docker("volume", "create", self.volume)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        failures = []
        resources = [("container", name) for name in reversed(self.containers)]
        resources.append(("volume", self.volume))
        for kind, name in resources:
            arguments = ("rm", "--force", name) if kind == "container" else ("volume", "rm", name)
            try:
                result = docker(*arguments, check=False)
                if result.returncode:
                    failures.append(f"{kind} {name}: removal exited with code {result.returncode}")
            except (OSError, subprocess.SubprocessError) as error:
                failures.append(f"{kind} {name}: removal raised {type(error).__name__}")
        self.assertFalse(failures, "Docker fixture cleanup failed:\n" + "\n".join(failures))

    def start(self, suffix, port=8080, mounted=True, readonly_volume=False):
        name = f"{self.prefix}-{suffix}"
        self.containers.append(name)
        command = ["run", "--detach", "--name", name, "--read-only",
                   "--tmpfs", "/tmp:size=32m,mode=1777", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges:true", "--stop-timeout", "15",
                   "--health-interval", "1s", "--health-start-period", "1s",
                   "--publish", f"127.0.0.1::{port}", "--env", f"PORT={port}"]
        if mounted:
            mount = f"source={self.volume},target=/data"
            command += ["--mount", mount + (",readonly" if readonly_volume else "")]
        docker(*command, IMAGE)
        return name

    def wait_ready(self, name, port=8080):
        binding = docker("port", name, f"{port}/tcp").stdout.strip()
        host_port = int(binding.rsplit(":", 1)[1])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = inspect(name)["State"]
            if not state["Running"]:
                self.fail(f"Container exited: {docker('logs', name).stdout}")
            try:
                if http_request(host_port, "/health/ready")[0] == 200 and state.get("Health", {}).get("Status") == "healthy":
                    return host_port
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(0.2)
        self.fail(f"Container did not become ready: {docker('logs', name).stdout}")

    def stop_cleanly(self, name):
        docker("stop", "--time", "15", name)
        self.assertEqual(inspect(name)["State"]["ExitCode"], 0)
        logs = docker("logs", name).stdout
        self.assertIn('"message":"shutdown requested"', logs)
        self.assertIn('"message":"server stopped"', logs)

    def test_image_serves_frontend_api_and_health_as_non_root_on_custom_port(self):
        name = self.start("http", port=9090)
        port = self.wait_ready(name, port=9090)
        self.assertEqual(docker("exec", name, "id", "-u").stdout.strip(), "10001")
        self.assertEqual(docker("exec", name, "cat", "/proc/1/comm").stdout.strip(), "kitternel-light")
        self.assertEqual(inspect(name)["Config"]["User"], "10001:10001")
        self.assertNotEqual(docker("exec", name, "touch", "/app/should-not-exist", check=False).returncode, 0)
        self.assertNotEqual(docker("exec", name, "sh", "-c", "command -v node", check=False).returncode, 0)
        for path, expected in [("/health/live", {"status": "ok"}), ("/health/ready", {"status": "ready"}),
                               ("/api/hello", {"message": "Hello from Kitternel Light."})]:
            status, body, _ = http_request(port, path)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), expected)
        for path in ("/", "/example/client-route"):
            status, body, headers = http_request(port, path, "text/html")
            self.assertEqual(status, 200)
            self.assertIn(b'<div id="root">', body)
            self.assertIn("text/html", headers["Content-Type"])
            if path == "/":
                assets = re.findall(rb'(?:src|href)="(/assets/[^" ]+)"', body)
                self.assertGreaterEqual(len(assets), 2, "entrypoint must reference built JS and CSS")
                for asset in assets:
                    asset_status, content, asset_headers = http_request(port, asset.decode(), "*/*")
                    self.assertEqual(asset_status, 200)
                    self.assertTrue(content)
                    self.assertEqual(asset_headers["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(http_request(port, "/api/missing", "text/html")[0], 404)
        self.assertEqual(http_request(port, "/assets/missing.js", "text/html")[0], 404)
        self.stop_cleanly(name)

    def test_data_survives_container_recreation(self):
        first = self.start("first")
        self.wait_ready(first)
        docker("exec", first, "sqlite3", "/data/kitternel.db",
               "UPDATE greetings SET message = 'Persisted across container recreation' WHERE id = 1;")
        self.stop_cleanly(first)
        docker("rm", first)
        self.containers.remove(first)
        second = self.start("second")
        port = self.wait_ready(second)
        status, body, _ = http_request(port, "/api/hello")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"message": "Persisted across container recreation"})
        self.stop_cleanly(second)

    def test_missing_or_readonly_storage_fails_clearly(self):
        for suffix, mounted, readonly in [("missing", False, False), ("readonly", True, True)]:
            with self.subTest(storage=suffix):
                name = self.start(suffix, mounted=mounted, readonly_volume=readonly)
                code = docker("wait", name).stdout.strip()
                self.assertNotEqual(code, "0")
                logs = docker("logs", name)
                self.assertIn("database initialization failed", logs.stdout + logs.stderr)

    def test_volume_with_incompatible_permissions_fails_without_repairing_it(self):
        docker("run", "--rm", "--user", "0:0", "--entrypoint", "sh",
               "--mount", f"source={self.volume},target=/data", IMAGE,
               "-c", "touch /data/.permissions-fixture && chown 0:0 /data && chmod 0700 /data")
        name = self.start("permissions")
        self.assertNotEqual(docker("wait", name).stdout.strip(), "0")
        logs = docker("logs", name)
        self.assertIn("database initialization failed", logs.stdout + logs.stderr)

    def test_compose_configuration_starts_with_persistent_writable_volume(self):
        # Override only the image and host port, preserving the actual Compose hardening.
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        environment = os.environ.copy()
        environment["HOST_PORT"] = str(port)
        with tempfile.TemporaryDirectory(prefix="kitternel-compose-") as directory:
            override = Path(directory) / "override.json"
            override.write_text(json.dumps({"services": {"app": {"image": IMAGE}}}))
            command = ["compose", "--project-name", self.prefix,
                       "--file", str(ROOT / "templates/light/compose.yaml"), "--file", str(override)]
            try:
                docker(*command, "config", "--quiet", environment=environment)
                docker(*command, "up", "--detach", "--no-build", environment=environment)
                name = docker(*command, "ps", "--quiet", "app", environment=environment).stdout.strip()
                self.assertTrue(name)
                self.wait_ready(name)
                config = inspect(name)
                self.assertTrue(config["HostConfig"]["ReadonlyRootfs"])
                self.assertEqual(config["HostConfig"]["CapDrop"], ["ALL"])
                self.assertEqual(http_request(port, "/health/ready")[0], 200)
                self.assertEqual(docker("exec", name, "sqlite3", "/data/kitternel.db",
                                        "SELECT version, success FROM _sqlx_migrations;").stdout.strip(), "1|1")
                docker("exec", name, "sqlite3", "/data/kitternel.db",
                       "UPDATE greetings SET message = 'Compose retained data' WHERE id = 1;")
                original_id = config["Id"]
                self.stop_cleanly(name)
                docker(*command, "up", "--detach", "--no-build", "--force-recreate", environment=environment)
                replacement = docker(*command, "ps", "--quiet", "app", environment=environment).stdout.strip()
                self.assertNotEqual(inspect(replacement)["Id"], original_id)
                self.wait_ready(replacement)
                self.assertEqual(json.loads(http_request(port, "/api/hello")[1]),
                                 {"message": "Compose retained data"})
                self.stop_cleanly(replacement)
            finally:
                # This project name is unique to this test; never delete deployment volumes.
                result = docker(*command, "down", "--volumes", environment=environment, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=IMAGE)
    arguments, remaining = parser.parse_known_args()
    IMAGE = arguments.image
    docker("image", "inspect", IMAGE)
    unittest.main(argv=[__file__, *remaining])
