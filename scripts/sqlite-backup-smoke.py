#!/usr/bin/env python3
"""Exercise the documented backup/restore helpers on isolated Docker volumes."""
import argparse
import importlib.util
import json
import sqlite3
import tempfile
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("docker_smoke", Path(__file__).with_name("docker-smoke.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class SQLiteBackupSmoke(unittest.TestCase):
    def setUp(self):
        self.fixture = base.DockerSmoke()
        self.volumes = []
        self.addCleanup(self.cleanup)
        self.fixture.setUp()
        self.backups = self.fixture.prefix + "-backups"
        self.restored = self.fixture.prefix + "-restored"
        for volume in (self.backups, self.restored):
            base.docker("volume", "create", volume)
            self.volumes.append(volume)

    def cleanup(self):
        self.fixture.doCleanups()
        for volume in self.volumes:
            result = base.docker("volume", "rm", volume, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def helper(self, command, snapshot, volume, check=True):
        return base.docker("run", "--rm", "--read-only", "--no-healthcheck", "--network", "none", "--cap-drop", "ALL",
                           "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:size=32m,mode=1777",
                           "--mount", f"source={volume},target=/data",
                           "--mount", f"source={self.backups},target=/backups" + (",readonly" if command == "sqlite-restore" else ""),
                           "--entrypoint", f"/app/{command}", base.IMAGE, snapshot, check=check)

    def snapshot_query(self, sql):
        return base.docker("run", "--rm", "--read-only", "--network", "none",
                           "--mount", f"source={self.backups},target=/backups,readonly",
                           "--entrypoint", "sqlite3", base.IMAGE,
                           "-readonly", "/backups/verified.sqlite", sql).stdout.strip()

    def test_online_snapshot_restores_to_separate_volume_and_preserves_source(self):
        name = self.fixture.start("live")
        live_port = self.fixture.wait_ready(name)
        base.docker("exec", name, "sqlite3", "/data/kitternel.db",
                    "UPDATE greetings SET message = 'Backed up greeting' WHERE id = 1;")
        base.docker("exec", name, "test", "-f", "/data/kitternel.db-wal")
        self.helper("sqlite-backup", "verified.sqlite", self.fixture.volume)
        self.assertEqual(self.snapshot_query("PRAGMA integrity_check;"), "ok")
        self.assertEqual(self.snapshot_query("PRAGMA foreign_key_check;"), "")
        self.assertEqual(self.snapshot_query("PRAGMA journal_mode;"), "delete")
        self.assertEqual(self.snapshot_query("SELECT message FROM greetings WHERE id = 1;"), "Backed up greeting")
        self.assertEqual(self.snapshot_query("SELECT COUNT(*) FROM _sqlx_migrations WHERE success = 1;"), "1")
        # Export the finalized snapshot as documented, then open it independently.
        export_name = self.fixture.prefix + "-export"
        self.fixture.containers.append(export_name)
        base.docker("create", "--name", export_name, "--read-only", "--network", "none",
                    "--mount", f"source={self.backups},target=/backups,readonly",
                    "--entrypoint", "/bin/true", base.IMAGE)
        with tempfile.TemporaryDirectory(prefix="kitternel-snapshot-export-") as exported:
            target = Path(exported) / "verified.sqlite"
            base.docker("cp", f"{export_name}:/backups/verified.sqlite", str(target))
            with sqlite3.connect(target.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                self.assertEqual(connection.execute("SELECT message FROM greetings WHERE id = 1").fetchone(), ("Backed up greeting",))
        duplicate = self.helper("sqlite-backup", "verified.sqlite", self.fixture.volume, check=False)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("refusing to overwrite", duplicate.stderr)
        base.docker("exec", name, "sqlite3", "/data/kitternel.db",
                    "UPDATE greetings SET message = 'Changed after snapshot' WHERE id = 1;")
        self.helper("sqlite-restore", "verified.sqlite", self.restored)
        original_volume = self.fixture.volume
        try:
            self.fixture.volume = self.restored
            restored_name = self.fixture.start("restored")
        finally:
            self.fixture.volume = original_volume
        port = self.fixture.wait_ready(restored_name)
        self.assertEqual(json.loads(base.http_request(port, "/api/hello")[1]), {"message": "Backed up greeting"})
        self.assertEqual(json.loads(base.http_request(live_port, "/api/hello")[1]), {"message": "Changed after snapshot"})
        rejected = self.helper("sqlite-restore", "verified.sqlite", self.restored, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("Target database or sidecar exists", rejected.stderr)
        self.assertEqual(json.loads(base.http_request(port, "/api/hello")[1]), {"message": "Backed up greeting"})
        self.fixture.stop_cleanly(restored_name)
        self.fixture.stop_cleanly(name)

    def test_missing_corrupt_or_unsafe_inputs_fail_without_creating_a_database(self):
        missing = self.helper("sqlite-backup", "missing.sqlite", self.fixture.volume, check=False)
        self.assertNotEqual(missing.returncode, 0)
        for snapshot in ("../escape.sqlite", "_invalid.sqlite", "quote'file.sqlite", "line\nbreak.sqlite"):
            unsafe = self.helper("sqlite-backup", snapshot, self.fixture.volume, check=False)
            self.assertNotEqual(unsafe.returncode, 0)
        base.docker("run", "--rm", "--network", "none", "--entrypoint", "sh",
                    "--mount", f"source={self.backups},target=/backups", base.IMAGE,
                    "-c", "printf 'not a SQLite database' > /backups/corrupt.sqlite")
        corrupt = self.helper("sqlite-restore", "corrupt.sqlite", self.restored, check=False)
        self.assertNotEqual(corrupt.returncode, 0)
        base.docker("run", "--rm", "--read-only", "--network", "none",
                    "--mount", f"source={self.restored},target=/data", "--entrypoint", "test", base.IMAGE,
                    "!", "-e", "/data/kitternel.db")
        base.docker("run", "--rm", "--network", "none", "--entrypoint", "sqlite3",
                    "--mount", f"source={self.backups},target=/backups", base.IMAGE,
                    "/backups/foreign-key.sqlite",
                    "CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(parent_id INTEGER REFERENCES parent(id)); INSERT INTO child VALUES (999);")
        invalid_fk = self.helper("sqlite-restore", "foreign-key.sqlite", self.restored, check=False)
        self.assertNotEqual(invalid_fk.returncode, 0)
        self.assertIn("foreign key check failed", invalid_fk.stderr)
        base.docker("run", "--rm", "--network", "none", "--entrypoint", "touch",
                    "--mount", f"source={self.restored},target=/data", base.IMAGE, "/data/kitternel.db-wal")
        orphan = self.helper("sqlite-restore", "corrupt.sqlite", self.restored, check=False)
        self.assertNotEqual(orphan.returncode, 0)
        self.assertIn("Target database or sidecar exists", orphan.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=base.IMAGE)
    arguments, remaining = parser.parse_known_args()
    base.IMAGE = arguments.image
    base.docker("image", "inspect", base.IMAGE)
    unittest.main(argv=[__file__, *remaining])
