#!/usr/bin/env python3
"""Regress Cargo artifact selection and both runner launch paths."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import smoke_paths


class SmokePathTests(unittest.TestCase):
    def test_metadata_controls_default_relative_and_absolute_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "backend"
            for configured in (None, "../external", str(root / "absolute")):
                with self.subTest(target=configured):
                    selected = backend / "target" if configured is None else (root / configured).resolve()
                    binary = selected / "debug" / ("kitternel-light.exe" if os.name == "nt" else "kitternel-light")
                    binary.parent.mkdir(parents=True, exist_ok=True)
                    binary.touch()
                    environment = {} if configured is None else {"CARGO_TARGET_DIR": configured}
                    metadata = subprocess.CompletedProcess([], 0, json.dumps({"target_directory": str(selected)}), "")
                    with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(smoke_paths.subprocess, "run", return_value=metadata) as cargo:
                        self.assertEqual(smoke_paths.backend_binary(backend), binary)
                        arguments = cargo.call_args
                        self.assertNotIn("cwd", arguments.kwargs)
                        self.assertNotIn("env", arguments.kwargs)
                        self.assertTrue(arguments.kwargs["check"])
                        self.assertIn("--offline", arguments.args[0])
                        self.assertEqual(arguments.args[0][-1], str(backend / "Cargo.toml"))

    def test_missing_selected_binary_never_falls_back_to_stale_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = root / "target/debug/kitternel-light"
            stale.parent.mkdir(parents=True)
            stale.touch()
            metadata = subprocess.CompletedProcess([], 0, json.dumps({"target_directory": str(root / "external")}), "")
            with mock.patch.object(smoke_paths.subprocess, "run", return_value=metadata):
                with self.assertRaises(FileNotFoundError):
                    smoke_paths.backend_binary(root)

    def test_cargo_failure_is_not_replaced_with_default_binary(self):
        with mock.patch.object(smoke_paths.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "cargo")):
            with self.assertRaises(subprocess.CalledProcessError):
                smoke_paths.backend_binary(Path("backend"))

    def test_windows_executable_suffix(self):
        metadata = subprocess.CompletedProcess([], 0, '{"target_directory":"/selected"}', "")
        with mock.patch.object(smoke_paths.subprocess, "run", return_value=metadata), mock.patch.object(smoke_paths, "os", SimpleNamespace(name="nt")), mock.patch.object(Path, "is_file", return_value=True):
            self.assertEqual(smoke_paths.backend_binary(Path('/backend')).name, "kitternel-light.exe")

    def test_both_runners_launch_resolved_binary(self):
        class LaunchObserved(Exception):
            pass
        for filename in ("backend-smoke.py", "browser-smoke.py"):
            with self.subTest(runner=filename):
                spec = importlib.util.spec_from_file_location("runner", Path(__file__).with_name(filename))
                runner = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(runner)
                with mock.patch.object(runner, "backend_binary", return_value=Path('/selected/debug/kitternel-light')) as resolve, mock.patch.object(runner.subprocess, "Popen", side_effect=LaunchObserved) as launch:
                    if filename == "backend-smoke.py":
                        fixture = runner.BackendSmoke()
                        fixture.setUp()
                        try:
                            with self.assertRaises(LaunchObserved):
                                fixture.start()
                        finally:
                            fixture.doCleanups()
                    else:
                        with self.assertRaises(LaunchObserved):
                            runner.main()
                    resolve.assert_called_once_with(runner.BACKEND)
                    self.assertEqual(launch.call_args.args[0], ['/selected/debug/kitternel-light'])


if __name__ == "__main__":
    unittest.main()
