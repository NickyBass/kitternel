#!/usr/bin/env python3
"""Exercise the documented backup/restore helpers on isolated Docker volumes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import importlib.util
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest import mock

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
        failures = []
        if not self.fixture.doCleanups():
            failures.append("Primary Docker fixture cleanup failed")
        # Attempt every extra volume even when an earlier cleanup failed.
        for volume in self.volumes:
            try:
                result = base.docker("volume", "rm", volume, check=False)
                if result.returncode:
                    failures.append(f"Volume cleanup failed for {volume}: {result.stderr}")
            except (OSError, subprocess.SubprocessError) as error:
                failures.append(f"Volume cleanup raised {type(error).__name__} for {volume}")
        self.assertFalse(failures, "\n".join(failures))

    def helper(self, command, snapshot, volume, check=True, database_path=None, utility_override=None, extra_options=()):
        options = list(extra_options)
        if utility_override:
            utility, replacement = utility_override
            options += ["--mount", f"type=bind,source={replacement},target=/usr/bin/gnu{utility},readonly"]
        options += [] if database_path is None else ["--env", f"SQLITE_PATH={database_path}"]
        return base.docker("run", "--rm", "--read-only", "--no-healthcheck", "--network", "none", "--cap-drop", "ALL",
                           "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:size=32m,mode=1777",
                           "--mount", f"source={volume},target=/data",
                           "--mount", f"source={self.backups},target=/backups" + (",readonly" if command == "sqlite-restore" else ""),
                           *options, "--entrypoint", f"/app/{command}", base.IMAGE, snapshot, check=check)

    def snapshot_query(self, sql):
        return base.docker("run", "--rm", "--read-only", "--network", "none",
                           "--mount", f"source={self.backups},target=/backups,readonly",
                           "--entrypoint", "sqlite3", base.IMAGE,
                           "-readonly", "/backups/verified.sqlite", sql).stdout.strip()

    def test_gnu_identity_missing_tools_and_failure_propagation(self):
        for utility in ("dirname", "realpath", "mktemp", "rm", "sync", "ln"):
            version = base.docker("run", "--rm", "--read-only", "--network", "none",
                                  "--entrypoint", f"/usr/bin/gnu{utility}", base.IMAGE, "--version")
            self.assertIn("(GNU coreutils)", version.stdout)
        name = self.fixture.start("gnu")
        self.fixture.wait_ready(name)
        with tempfile.TemporaryDirectory(prefix="gnu-recovery-") as temporary:
            replacement = Path(temporary) / "replacement"
            for command, volume in (("sqlite-backup", self.fixture.volume), ("sqlite-restore", self.restored)):
                for mode, content, message in (
                    (0o644, "", "missing or not executable"),
                    (0o755, "#!/bin/sh\nexit 74\n", "Could not verify GNU utility"),
                    (0o755, "#!/bin/sh\nprintf 'uutils coreutils\\n'\n", "not GNU coreutils"),
                ):
                    replacement.write_text(content)
                    replacement.chmod(mode)
                    result = self.helper(command, "absent.sqlite", volume, check=False,
                                         utility_override=("ln", replacement))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)
            # Fail sync before atomic publication; no artifact or temporary files may survive.
            replacement.write_text('#!/bin/sh\nif [ "$1" = --version ]; then printf "sync (GNU coreutils) test\\n"; else exit 73; fi\n')
            replacement.chmod(0o755)
            result = self.helper("sqlite-backup", "failed.sqlite", self.fixture.volume, check=False,
                                 utility_override=("sync", replacement))
            self.assertEqual(result.returncode, 73)
            listing = base.docker("run", "--rm", "--read-only", "--network", "none",
                                  "--mount", f"source={self.backups},target=/backups,readonly",
                                  "--entrypoint", "/bin/sh", base.IMAGE,
                                  "-c", 'set -- /backups/* /backups/.*; for path; do [ ! -f "$path" ] || exit 1; done')
            self.assertEqual(listing.returncode, 0)
            Path(temporary).chmod(0o755)
            # Poison ordinary utility names: explicit GNU operations must bypass PATH shadowing.
            for utility in ("dirname", "realpath", "mktemp", "rm", "sync", "ln"):
                poison = Path(temporary) / utility
                poison.write_text("#!/bin/sh\nexit 89\n")
                poison.chmod(0o755)
            self.helper("sqlite-backup", "verified.sqlite", self.fixture.volume,
                        extra_options=("--mount", f"type=bind,source={temporary},target=/poison,readonly",
                                       "--env", "PATH=/poison:/usr/bin:/bin"))
            failed_restore = self.helper("sqlite-restore", "verified.sqlite", self.restored, check=False,
                                         utility_override=("sync", replacement))
            self.assertEqual(failed_restore.returncode, 73)
            base.docker("run", "--rm", "--read-only", "--network", "none",
                        "--mount", f"source={self.restored},target=/data,readonly",
                        "--entrypoint", "/bin/sh", base.IMAGE,
                        "-c", 'for path in /data/* /data/.*; do [ ! -f "$path" ] || exit 1; done')
            self.helper("sqlite-restore", "verified.sqlite", self.restored,
                        database_path="/data/space $ unicode-è.db",
                        extra_options=("--mount", f"type=bind,source={temporary},target=/poison,readonly",
                                       "--env", "PATH=/poison:/usr/bin:/bin"))
        self.fixture.stop_cleanly(name)

    def test_concurrent_backups_publish_one_valid_snapshot(self):
        name = self.fixture.start("concurrent")
        self.fixture.wait_ready(name)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.helper, "sqlite-backup", "verified.sqlite",
                                       self.fixture.volume, check=False) for _ in range(2)]
            results = [future.result() for future in futures]
        self.assertEqual(sum(result.returncode == 0 for result in results), 1,
                         [(r.returncode, r.stderr) for r in results])
        self.assertEqual(self.snapshot_query("PRAGMA integrity_check;"), "ok")
        self.assertEqual(self.snapshot_query("SELECT message FROM greetings WHERE id=1;"),
                         "Hello from Kitternel Light.")
        listing = base.docker("run", "--rm", "--read-only", "--network", "none",
                              "--mount", f"source={self.backups},target=/backups,readonly",
                              "--entrypoint", "/bin/sh", base.IMAGE,
                              "-c", 'for path in /backups/.verified.sqlite.*; do [ ! -e "$path" ] || exit 1; done')
        self.assertEqual(listing.returncode, 0)
        self.fixture.stop_cleanly(name)

    def test_online_snapshot_restores_to_separate_volume_and_preserves_source(self):
        name = self.fixture.start("live")
        live_port = self.fixture.wait_ready(name)
        base.docker("exec", name, "sqlite3", "/data/kitternel.db",
                    "UPDATE greetings SET message = 'Backed up greeting' WHERE id = 1;")
        base.docker("exec", name, "test", "-f", "/data/kitternel.db-wal")
        metadata_sql = "SELECT version, hex(checksum), success FROM _sqlx_migrations ORDER BY version;"
        metadata = base.docker("exec", name, "sqlite3", "/data/kitternel.db", metadata_sql).stdout.strip()
        self.helper("sqlite-backup", "verified.sqlite", self.fixture.volume)
        self.assertEqual(self.snapshot_query(metadata_sql), metadata)
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
            with closing(sqlite3.connect(target.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
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
        self.assertEqual(base.docker("exec", restored_name, "sqlite3", "/data/kitternel.db", metadata_sql).stdout.strip(), metadata)
        self.assertEqual(json.loads(base.http_request(port, "/api/hello")[1]), {"message": "Backed up greeting"})
        self.assertEqual(json.loads(base.http_request(live_port, "/api/hello")[1]), {"message": "Changed after snapshot"})
        rejected = self.helper("sqlite-restore", "verified.sqlite", self.restored, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("Target database or sidecar exists", rejected.stderr)
        self.assertEqual(json.loads(base.http_request(port, "/api/hello")[1]), {"message": "Backed up greeting"})
        self.fixture.stop_cleanly(restored_name)
        self.fixture.stop_cleanly(name)

    def test_foreign_key_query_errors_abort_backup_and_restore(self):
        # Valid SQLite pages but an invalid FK definition: the check raises instead of returning a violation row.
        base.docker("run", "--rm", "--network", "none", "--entrypoint", "sqlite3",
                    "--mount", f"source={self.fixture.volume},target=/data", base.IMAGE,
                    "/data/kitternel.db", "CREATE TABLE parent(id INTEGER); CREATE TABLE child(parent_id INTEGER REFERENCES parent(id));")
        failed = self.helper("sqlite-backup", "rejected.sqlite", self.fixture.volume, check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("foreign key check could not be completed", failed.stderr)
        self.assertNotIn("Snapshot created", failed.stdout)
        base.docker("run", "--rm", "--read-only", "--network", "none", "--entrypoint", "test",
                    "--mount", f"source={self.backups},target=/backups", base.IMAGE,
                    "!", "-e", "/backups/rejected.sqlite")
        # Copy only a closed synthetic fixture to test restore rejection independently of the backup guard.
        base.docker("run", "--rm", "--read-only", "--network", "none", "--entrypoint", "cp",
                    "--mount", f"source={self.fixture.volume},target=/data,readonly",
                    "--mount", f"source={self.backups},target=/backups", base.IMAGE,
                    "/data/kitternel.db", "/backups/malformed.sqlite")
        failed = self.helper("sqlite-restore", "malformed.sqlite", self.restored, check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("foreign key check could not be completed", failed.stderr)
        self.assertNotIn("Database restored", failed.stdout)
        base.docker("run", "--rm", "--read-only", "--network", "none", "--entrypoint", "test",
                    "--mount", f"source={self.restored},target=/data", base.IMAGE,
                    "!", "-e", "/data/kitternel.db")

    def test_nested_paths_persist_and_symlinked_parents_are_rejected(self):
        base.docker("run", "--rm", "--network", "none", "--entrypoint", "sqlite3",
                    "--mount", f"source={self.backups},target=/backups", base.IMAGE,
                    "/backups/valid.sqlite", "CREATE TABLE recovery_probe(value TEXT); INSERT INTO recovery_probe VALUES ('persistent data');")
        base.docker("run", "--rm", "--network", "none", "--entrypoint", "sh",
                    "--mount", f"source={self.restored},target=/data", base.IMAGE,
                    "-c", "mkdir /data/real && ln -s /tmp /data/escape && ln -s /data/real /data/alias")
        for parent in ("escape", "alias"):
            failed = self.helper("sqlite-restore", "valid.sqlite", self.restored, check=False,
                                 database_path=f"/data/{parent}/restored.db")
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("Database parent", failed.stderr)
            self.assertNotIn("Database restored", failed.stdout)
        base.docker("run", "--rm", "--network", "none", "--entrypoint", "ln",
                    "--mount", f"source={self.fixture.volume},target=/data", base.IMAGE,
                    "-s", "/backups", "/data/source-alias")
        failed = self.helper("sqlite-backup", "rejected.sqlite", self.fixture.volume, check=False,
                             database_path="/data/source-alias/valid.sqlite")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("Database parent", failed.stderr)
        self.helper("sqlite-restore", "valid.sqlite", self.restored, database_path="/data/real/restored.db")
        value = base.docker("run", "--rm", "--read-only", "--network", "none", "--entrypoint", "sqlite3",
                            "--mount", f"source={self.restored},target=/data,readonly", base.IMAGE,
                            "-readonly", "/data/real/restored.db", "SELECT value FROM recovery_probe;")
        self.assertEqual(value.stdout.strip(), "persistent data")
        self.helper("sqlite-backup", "nested-copy.sqlite", self.restored, database_path="/data/real/restored.db")

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


class CleanupPropagationTests(unittest.TestCase):
    def test_nested_cleanup_failure_fails_outer_test_and_still_attempts_extra_volumes(self):
        wrapper = SQLiteBackupSmoke()
        wrapper.fixture = base.DockerSmoke()
        wrapper.volumes = ["first-extra", "second-extra"]
        def failed_cleanup():
            raise RuntimeError("simulated nested cleanup failure")
        wrapper.fixture.addCleanup(failed_cleanup)
        outer = unittest.FunctionTestCase(lambda: None)
        outer.addCleanup(wrapper.cleanup)
        result = unittest.TestResult()
        with mock.patch.object(base, "docker", return_value=subprocess.CompletedProcess([], 0, "", "")) as remove:
            outer.run(result)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.failures), 1)
        self.assertIn("Primary Docker fixture cleanup failed", result.failures[0][1])
        self.assertEqual(remove.call_count, 2)

    def test_volume_cleanup_exception_does_not_skip_remaining_volumes(self):
        wrapper = SQLiteBackupSmoke()
        wrapper.fixture = base.DockerSmoke()
        wrapper.volumes = ["first-extra", "second-extra"]
        outer = unittest.FunctionTestCase(lambda: None)
        outer.addCleanup(wrapper.cleanup)
        result = unittest.TestResult()
        with mock.patch.object(base, "docker", side_effect=[subprocess.TimeoutExpired("docker", 90), subprocess.CompletedProcess([], 0, "", "")]) as remove:
            outer.run(result)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.failures), 1)
        self.assertIn("TimeoutExpired", result.failures[0][1])
        self.assertEqual(remove.call_count, 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=base.IMAGE)
    arguments, remaining = parser.parse_known_args()
    base.IMAGE = arguments.image
    base.docker("image", "inspect", base.IMAGE)
    unittest.main(argv=[__file__, *remaining])
