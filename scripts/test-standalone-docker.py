#!/usr/bin/env python3
"""Regress standalone validation isolation and failure cleanup without Docker."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("standalone", Path(__file__).with_name("standalone-docker-smoke.py"))
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
spec = importlib.util.spec_from_file_location("docker_smoke", Path(__file__).with_name("docker-smoke.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class StandaloneTests(unittest.TestCase):
    def test_clean_build_command_has_only_generated_context_and_optional_ca_secret(self):
        plain = validation.build_command("example:validation")
        self.assertIn("--no-cache", plain)
        self.assertEqual(plain[-1], ".")
        self.assertNotIn(str(validation.ROOT), " ".join(plain))
        self.assertEqual(validation.build_command("example:validation", Path("/trusted/ca.pem"))[-3:],
                         ["--secret", "id=proxy_ca,src=/trusted/ca.pem", "."])

    def test_only_this_run_resources_are_selected_including_unnamed_helpers(self):
        output = [
            ["own\texample-smoke-123-app", "other\texample-smokeother-app", "unrelated\tproduction"],
            ["helper"],
            ["example-smoke-123-data", "example-smokeother-data", "production-data"],
            ["network\texample-smoke-123_default", "othernet\tproduction_default"],
        ]
        with mock.patch.object(validation, "docker_output", side_effect=output) as docker:
            self.assertEqual(validation.resources("example"), ({"own", "helper"}, {"example-smoke-123-data"}, {"network"}))
            self.assertIn(f"label={validation.LABEL}=example", docker.call_args_list[1].args)

    def test_leftovers_fail_even_after_fallback_cleanup_and_all_removals_are_attempted(self):
        with mock.patch.object(validation, "resources", side_effect=[({"container"}, {"volume"}, {"network"}), (set(), set(), set())]), mock.patch.object(validation, "docker_output", side_effect=[subprocess.CalledProcessError(1, "docker"), [], [], ["image"], []]) as docker:
            with self.assertRaisesRegex(RuntimeError, "Cannot remove container"):
                validation.cleanup("example", "example:validation")
            self.assertEqual(docker.call_args_list[1].args, ("volume", "rm", "volume"))
            self.assertEqual(docker.call_args_list[2].args, ("network", "rm", "network"))
            self.assertEqual(docker.call_args_list[-1].args, ("image", "rm", "example:validation"))

    def test_successful_cleanup_checks_inventory_twice_and_removes_image(self):
        with mock.patch.object(validation, "resources", return_value=(set(), set(), set())) as inventory, mock.patch.object(validation, "docker_output", side_effect=[["image"], []]) as docker:
            validation.cleanup("example", "example:validation")
            self.assertEqual(inventory.call_count, 2)
            self.assertEqual(docker.call_args_list[-1].args, ("image", "rm", "example:validation"))

    def test_failure_attempts_cleanup_and_removes_temporary_project(self):
        with mock.patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "production", "HOST_PORT": "8080"}), mock.patch.object(validation, "run", side_effect=RuntimeError("forced preflight failure")) as run, mock.patch.object(validation, "cleanup") as cleanup:
            with self.assertRaisesRegex(RuntimeError, "forced preflight failure"):
                validation.validate()
            project = run.call_args.args[2]
            environment = run.call_args.args[3]
            self.assertNotIn("COMPOSE_PROJECT_NAME", environment)
            self.assertNotIn("HOST_PORT", environment)
            self.assertTrue(environment["SMOKE_RUN_ID"].startswith("light-e2e-"))
            self.assertFalse(project.exists())
            cleanup.assert_called_once()
            self.assertTrue(cleanup.call_args.args[0].startswith("light-e2e-"))
            self.assertFalse(project.is_relative_to(validation.ROOT))

    def test_original_failure_is_not_hidden_by_cleanup_failure(self):
        with mock.patch.object(validation, "run", side_effect=RuntimeError("build failed")), mock.patch.object(validation, "cleanup", side_effect=RuntimeError("cleanup failed")):
            with self.assertRaisesRegex(RuntimeError, "build failed; cleanup also failed: cleanup failed"):
                validation.validate()

    def test_no_source_artifacts_or_symlinks_are_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "Dockerfile").write_text("FROM example")
            with self.assertRaisesRegex(RuntimeError, "missing"):
                validation.validate_files(project)
            # Generate a complete clean project using the same trusted source generator.
            spec = importlib.util.spec_from_file_location("creator", validation.ROOT / "scripts/create-light.py")
            creator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(creator)
            project = creator.generate("standalone-test", Path(temporary) / "app")
            validation.validate_files(project)
            for filename in ("private.db", "private.sqlite-wal", ".env.local"):
                artifact = project / filename
                artifact.touch()
                with self.assertRaisesRegex(RuntimeError, "existing artifact"):
                    validation.validate_files(project)
                artifact.unlink()
            artifact = project / "frontend/node_modules"
            artifact.mkdir()
            with self.assertRaisesRegex(RuntimeError, "existing artifact"):
                validation.validate_files(project)
            artifact.rmdir()
            artifact.symlink_to(validation.ROOT, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                validation.validate_files(project)
            artifact.unlink()
            (project / "README.md").write_text(str(validation.ROOT))
            with self.assertRaisesRegex(RuntimeError, "source layout"):
                validation.validate_files(project)

    def test_unnamed_containers_are_labelled_without_changing_normal_commands(self):
        with mock.patch.object(smoke.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as docker:
            smoke.docker("run", "--rm", "example", environment={"SMOKE_RUN_ID": "example"})
            self.assertEqual(docker.call_args.args[0][:4], ["docker", "run", "--label", "io.starter.smoke-run=example"])
            smoke.docker("run", "--rm", "example", environment={})
            self.assertEqual(docker.call_args.args[0], ["docker", "run", "--rm", "example"])
            with self.assertRaises(ValueError):
                smoke.docker("run", "example", environment={"SMOKE_RUN_ID": "unsafe value"})

    def test_command_timeout_is_actionable_and_reaps_child(self):
        process = mock.Mock(pid=123)
        process.wait.side_effect = [subprocess.TimeoutExpired("suite", 1), 0]
        with mock.patch.object(validation.subprocess, "Popen", return_value=process), mock.patch.object(validation.os, "killpg", create=True) as kill:
            with self.assertRaisesRegex(RuntimeError, "probe failed.*TimeoutExpired"):
                validation.run("probe", [sys.executable], Path.cwd(), os.environ.copy(), timeout=1)
            self.assertEqual(process.wait.call_count, 2)
            if os.name == "posix":
                kill.assert_called_once_with(123, validation.signal.SIGKILL)
            else:
                process.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
