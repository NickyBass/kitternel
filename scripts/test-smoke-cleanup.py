#!/usr/bin/env python3
"""Verify smoke cleanup failure reporting without contacting Docker."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("backup_smoke", Path(__file__).with_name("sqlite-backup-smoke.py"))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
base = backup.base


class DockerCleanupTests(unittest.TestCase):
    def run_cleanup(self, outcomes, nested=False):
        fixture = base.DockerSmoke()
        fixture.containers = ["first", "second"]
        fixture.volume = "data"
        fixture.addCleanup(fixture.cleanup)
        outer = unittest.FunctionTestCase(lambda: None)
        if nested:
            wrapper = backup.SQLiteBackupSmoke()
            wrapper.fixture = fixture
            wrapper.volumes = ["backups", "restored"]
            outer.addCleanup(wrapper.cleanup)
        else:
            # Exercise the real TestCase lifecycle, including cleanup failures.
            outer.addCleanup(fixture.cleanup)
        result = unittest.TestResult()
        with mock.patch.object(base, "docker", side_effect=outcomes) as remove:
            outer.run(result)
        expected = [mock.call("rm", "--force", name, check=False) for name in ("second", "first")]
        expected.append(mock.call("volume", "rm", "data", check=False))
        if nested:
            expected += [mock.call("volume", "rm", name, check=False) for name in ("backups", "restored")]
        self.assertEqual(remove.call_args_list, expected)
        return result

    def test_successful_removals_pass(self):
        self.assertTrue(self.run_cleanup([success()] * 3).wasSuccessful())

    def test_container_and_volume_exit_codes_fail_and_all_removals_are_attempted(self):
        for index in (0, 2):
            with self.subTest(failing_removal=index):
                outcomes = [success()] * 3
                outcomes[index] = subprocess.CompletedProcess([], 1, "", "sensitive diagnostic")
                result = self.run_cleanup(outcomes)
                self.assertFalse(result.wasSuccessful())
                self.assertEqual(len(result.failures), 1)
                self.assertIn("removal exited with code 1", result.failures[0][1])
                self.assertNotIn("sensitive diagnostic", result.failures[0][1])

    def test_exceptions_do_not_skip_remaining_resources(self):
        for error in (subprocess.TimeoutExpired("docker", 90), OSError("unavailable")):
            with self.subTest(error=type(error).__name__):
                result = self.run_cleanup([error, success(), success()])
                self.assertFalse(result.wasSuccessful())
                self.assertIn(type(error).__name__, result.failures[0][1])

    def test_multiple_failures_are_reported_together(self):
        failed = subprocess.CompletedProcess([], 2, "", "")
        result = self.run_cleanup([failed, success(), failed])
        self.assertFalse(result.wasSuccessful())
        self.assertIn("container second", result.failures[0][1])
        self.assertIn("volume data", result.failures[0][1])

    def test_nested_failure_fails_outer_test_and_cleans_extra_volumes(self):
        result = self.run_cleanup([subprocess.CompletedProcess([], 1, "", "")] + [success()] * 4, nested=True)
        self.assertFalse(result.wasSuccessful())
        self.assertIn("Primary Docker fixture cleanup failed", result.failures[0][1])


def success():
    return subprocess.CompletedProcess([], 0, "", "")


if __name__ == "__main__":
    unittest.main()
