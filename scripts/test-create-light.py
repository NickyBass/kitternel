#!/usr/bin/env python3
"""Test standalone generation; opt into pinned Rust formatting with --rustfmt."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("create_light", Path(__file__).with_name("create-light.py"))
creator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(creator)


# Cover the 1..32 character naming boundary (generate rejects 33), the wrapping
# regression, multiple hyphens and imports before/between/after dependencies.
FORMAT_NAMES = ("a", "a-app", "dev-notes", "audit-notes-7a", "maintenance-notes",
                "maple-notes", "sunrise-notes", "zebra-notes", "one-two-three-four", "a" * 32)
RUN_RUSTFMT = "--rustfmt" in sys.argv
if RUN_RUSTFMT:
    sys.argv.remove("--rustfmt")


class GenerationTests(unittest.TestCase):
    def test_cli_generation_with_only_git_on_path(self):
        with tempfile.TemporaryDirectory(prefix="git-only-generation-") as temporary:
            root = Path(temporary)
            tools = root / "tools"
            tools.mkdir()
            (tools / "git").symlink_to(shutil.which("git"))
            environment = {**os.environ, "PATH": str(tools)}
            project = root / "application"
            result = subprocess.run([sys.executable, str(creator.ROOT / "scripts/create-light.py"),
                                     "maintenance-notes", str(project)], env=environment,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((project / "backend/src/config.rs").is_file())

    @unittest.skipUnless(shutil.which("bash"), "Browser CI uses Bash on Linux")
    def test_generated_browser_installation_retries_and_failure_propagation(self):
        with tempfile.TemporaryDirectory(prefix="browser-install-") as temporary:
            root = Path(temporary)
            project = creator.generate("ci-notes", root / "application")
            workflow = (project / ".github/workflows/ci.yml").read_text()
            step = workflow.split("      - name: Install browser\n", 1)[1].split("\n      - name:", 1)[0]
            command = textwrap.dedent(step.split("        run: |\n", 1)[1])
            tools = root / "tools"
            tools.mkdir()
            stub = tools / "stub"
            stub.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
                import json, os, pathlib, sys
                root = pathlib.Path(os.environ['FIXTURE'])
                name = pathlib.Path(sys.argv[0]).name
                with (root / 'calls').open('a') as log:
                    log.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
                if name == 'sudo':
                    assert sys.argv[1:] == ['tee', '/etc/apt/apt.conf.d/99ci-downloads']
                    if os.environ['CONFIG_FAIL'] == '1':
                        sys.exit(42)
                    (root / 'apt-config').write_text(sys.stdin.read())
                elif name == 'npx':
                    assert sys.argv[1:] == ['playwright', 'install', '--with-deps', 'chromium']
                    counter = root / 'attempts'
                    attempt = int(counter.read_text()) + 1 if counter.exists() else 1
                    counter.write_text(str(attempt))
                    sys.exit(37 if attempt <= int(os.environ['FAILURES']) else 0)
                else:
                    assert name == 'sleep' and sys.argv[1:] == ['10']
                '''))
            stub.chmod(0o755)
            for name in ("sudo", "npx", "sleep"):
                (tools / name).symlink_to(stub)
            for failures, config_fail, attempts, sleeps, success in (
                    (0, False, 1, 0, True), (2, False, 3, 2, True),
                    (3, False, 3, 2, False), (0, True, 0, 0, False)):
                with self.subTest(failures=failures, config_fail=config_fail):
                    fixture = root / f"case-{failures}-{config_fail}"
                    fixture.mkdir()
                    environment = {**os.environ, "PATH": str(tools), "FIXTURE": str(fixture),
                                   "FAILURES": str(failures), "CONFIG_FAIL": str(int(config_fail))}
                    result = subprocess.run([shutil.which("bash"), "-e", "-c", command],
                                            env=environment, text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
                    calls = [json.loads(line) for line in (fixture / "calls").read_text().splitlines()]
                    self.assertEqual(sum(call[0] == "npx" for call in calls), attempts)
                    self.assertEqual(sum(call[0] == "sleep" for call in calls), sleeps)
                    if not config_fail:
                        config = (fixture / "apt-config").read_text()
                        self.assertIn('Acquire::Retries "3";', config)
                        self.assertIn('APT::Update::Error-Mode "any";', config)
                    if failures == 3:
                        self.assertIn("::error::Browser installation failed after 3 attempts", result.stdout)

    @unittest.skipUnless(shutil.which("sh"), "Docker RUN uses a POSIX shell")
    def test_runtime_apt_failure_stops_later_package_and_user_operations(self):
        dockerfile = (creator.ROOT / "templates/light/Dockerfile").read_text()
        command = dockerfile.split(" AS runtime\nRUN ", 1)[1].split("\nWORKDIR", 1)[0].replace("\\\n", "")
        with tempfile.TemporaryDirectory(prefix="apt-failure-") as temporary:
            root = Path(temporary)
            stub = root / "stub"
            stub.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
                import json, os, pathlib, sys
                name = pathlib.Path(sys.argv[0]).name
                with open(os.environ['CALLS'], 'a') as log:
                    log.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
                if name == 'apt-get' and os.environ['FAIL_AT'] in sys.argv[1:]:
                    sys.exit(100)
                '''))
            stub.chmod(0o755)
            for name in ("apt-get", "rm", "groupadd", "useradd", "install"):
                (root / name).symlink_to(stub)
            for fail_at, count in (("update", 1), ("upgrade", 2), ("install", 3), ("none", 3)):
                with self.subTest(fail_at=fail_at):
                    log = root / f"calls-{fail_at}"
                    environment = {**os.environ, "PATH": str(root), "CALLS": str(log), "FAIL_AT": fail_at}
                    result = subprocess.run([shutil.which("sh"), "-c", command], env=environment,
                                            text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0 if fail_at == "none" else 100)
                    calls = [json.loads(line) for line in log.read_text().splitlines()]
                    apt = [call for call in calls if call[0] == "apt-get"]
                    self.assertEqual(len(apt), count)
                    for call in apt:
                        self.assertIn("Acquire::Retries=3", call)
                    self.assertIn("APT::Update::Error-Mode=any", apt[0])
                    if fail_at != "none":
                        self.assertEqual(len(calls), count, "Failed APT must stop cleanup and user creation")
                    else:
                        self.assertEqual([call[0] for call in calls[3:]], ["rm", "groupadd", "useradd", "install"])

    def test_complete_customized_project_and_no_source_layout_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            for name in ("garden-notes", "kitternel-light", "root", "a-very-long-application-name", *FORMAT_NAMES):
                with self.subTest(name=name):
                    destination = creator.generate(name, Path(temporary) / name)
                    for relative in ("backend/src/main.rs", "backend/Cargo.lock", "backend/build.rs",
                                     "backend/migrations/0001_greeting.sql", "frontend/package-lock.json",
                                     "frontend/.node-version", "Dockerfile", "compose.yaml", ".dockerignore",
                                     ".github/workflows/ci.yml", ".github/workflows/security.yml", "SECURITY-SCANNING.md", ".env.example", ".gitignore", ".gitattributes",
                                     "README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", "MAINTENANCE.md", "LICENSE",
                                     "scripts/sqlite-backup.sh", "scripts/sqlite-restore.sh",
                                     *(f"scripts/{runner}" for runner in creator.RUNNERS)):
                        self.assertTrue((destination / relative).is_file(), relative)
                    for helper in ("sqlite-backup.sh", "sqlite-restore.sh"):
                        text = (destination / "scripts" / helper).read_text()
                        for utility in ("dirname", "realpath", "mktemp", "rm", "sync", "ln"):
                            self.assertIn(f"/usr/bin/gnu{utility}", text)
                        self.assertIn('(GNU coreutils)', text)
                    # An application import must not share a rustfmt sorting group
                    # with dependencies whose order changes after customization.
                    crate = name.replace("-", "_")
                    config = (destination / "backend/src/config.rs").read_text()
                    self.assertIn(f'const DEFAULT_SQLITE_PATH: &str = "data/{name}.db";', config)
                    # Keep the expected path independent of the default constant.
                    self.assertIn(f'PathBuf::from("data/{name}.db")', config)
                    for path in (destination / "backend").rglob("*.rs"):
                        for group in path.read_text().split("\n\n"):
                            if f"use {crate}::" in group:
                                self.assertEqual(group.count("use "), 1, path)
                    manifest = tomllib.loads((destination / "backend/Cargo.toml").read_text())
                    self.assertEqual(manifest["package"]["name"], name)
                    lock = tomllib.loads((destination / "backend/Cargo.lock").read_text())
                    self.assertIn(name, [package["name"] for package in lock["package"]])
                    package = json.loads((destination / "frontend/package.json").read_text())
                    npm_lock = json.loads((destination / "frontend/package-lock.json").read_text())
                    self.assertEqual(package["name"], name + "-frontend")
                    self.assertEqual(npm_lock["packages"][""]["name"], package["name"])
                    original_npm = json.loads((creator.ROOT / "templates/light/frontend/package-lock.json").read_text())
                    self.assertEqual({key: value for key, value in npm_lock["packages"].items() if key},
                                     {key: value for key, value in original_npm["packages"].items() if key})
                    self.assertIn(f'use {name.replace("-", "_")}::', (destination / "backend/src/main.rs").read_text())
                    dockerfile = (destination / "Dockerfile").read_text()
                    self.assertIn(f'ENTRYPOINT ["/app/{name}"]', dockerfile)
                    self.assertIn(f'name: {name}\n', (destination / "compose.yaml").read_text())
                    self.assertIn(name.replace("-", " ").title(), (destination / "frontend/index.html").read_text())
                    self.assertIn(f'"{name[:15]}"', (destination / "scripts/docker-smoke.py").read_text())
                    for path in destination.rglob("*"):
                        if path.is_file():
                            text = path.read_text()
                            self.assertNotIn("templates/light", text, path)
                            self.assertNotIn("../../../scripts", text, path)
                            self.assertNotIn(str(creator.ROOT), text, path)
                            if path.suffix == ".md":
                                for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                                    if not link.startswith(("https://", "http://", "mailto:", "#")):
                                        target = link.split("#", 1)[0]
                                        self.assertTrue((path.parent / target).exists(), f"Broken generated link: {link}")
                                        if "#" in link:
                                            document = (path.parent / target) if target else path
                                            text_without_code = re.sub(r"```.*?```", "", document.read_text(), flags=re.S)
                                            headings = re.findall(r"^#{1,6} (.+)$", text_without_code, re.M)
                                            anchors = {re.sub(r"[^\w -]", "", h.lower()).replace(" ", "-") for h in headings}
                                            self.assertIn(link.split("#", 1)[1], anchors, f"Broken generated anchor: {link}")
                            if name != "kitternel-light" and path.name != "LICENSE":
                                self.assertNotIn("kitternel", text.lower(), path)
                    self.assertFalse((destination / ".git").exists())
                    self.assertFalse((destination / "backend/target").exists())
                    self.assertFalse((destination / "frontend/node_modules").exists())
                    self.assertEqual((destination / "LICENSE").read_bytes(), (creator.ROOT / "LICENSE").read_bytes())
                    self.assertEqual((destination / "backend/src/db.rs").read_bytes(), (creator.ROOT / "templates/light/backend/src/db.rs").read_bytes())
                    self.assertNotIn(b'\r', (destination / "scripts/sqlite-backup.sh").read_bytes())
                    self.assertEqual((destination / "scripts/sqlite-backup.sh").stat().st_mode & 0o777,
                                     (creator.ROOT / "templates/light/scripts/sqlite-backup.sh").stat().st_mode & 0o777)
                    workflow = (destination / ".github/workflows/ci.yml").read_text()
                    security = (destination / ".github/workflows/security.yml").read_text()
                    self.assertIn("scripts/security-scan.py", security)
                    self.assertIn("--project .", security)
                    self.assertIn("--image " + name + ":local", security)
                    self.assertIn("workflow_dispatch", security)
                    self.assertIn("ENABLE_CODE_SCANNING", security)
                    self.assertNotIn("continue-on-error", security)
                    self.assertIn('docker build -t ' + name + ':local .\n', security)
                    self.assertIn('working-directory: backend\n', workflow)
                    self.assertIn('python3 ../scripts/backend-smoke.py', workflow)

    def test_maintenance_guide_matches_the_standalone_project(self):
        with tempfile.TemporaryDirectory(prefix="maintenance-guide-") as temporary:
            project = creator.generate("maintenance-notes", Path(temporary) / "application")
            guide = (project / "MAINTENANCE.md").read_text()
            self.assertIn("Maintaining Maintenance Notes", guide)
            self.assertIn("**maintenance-notes**", guide)
            for name in ("README.md", "CONTRIBUTING.md", "AGENTS.md"):
                self.assertIn("[MAINTENANCE.md](MAINTENANCE.md)", (project / name).read_text())
            for script in re.findall(r"(?:python3|sh) (scripts/[A-Za-z0-9_.-]+)", guide):
                self.assertTrue((project / script).is_file(), script)
            self.assertIn("--project .", guide)
            self.assertNotIn("--project templates/", guide)
            self.assertIn("--image maintenance-notes:maintenance-check", guide)
            self.assertIn("docker build --no-cache -t maintenance-notes:maintenance-check .", guide)
            self.assertIn("## Releases, Updates and Recovery", guide)
            headings = re.findall(r"^#{1,6} (.+)$", guide, re.M)
            anchors = {re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-") for heading in headings}
            readme = (project / "README.md").read_text()
            for anchor in re.findall(r"\]\(MAINTENANCE\.md#([^)]+)\)", readme):
                self.assertIn(anchor, anchors)
            for helper in set(re.findall(r"/app/(sqlite-[a-z]+)", guide)):
                self.assertTrue((project / "scripts" / (helper + ".sh")).is_file())
                self.assertIn("/app/" + helper, (project / "Dockerfile").read_text())
            for block in re.findall(r"```sh\n(.*?)```", guide, re.S):
                self.assertNotRegex(block, r"(?:docker compose|dc)[^\n]*\bdown\b[^\n]*(?:--volumes| -v\b)")
            self.assertIn('image: "${RELEASE_IMAGE:?Set RELEASE_IMAGE to a verified local image ID}"', guide)
            self.assertNotIn("@NAME@", guide)
            self.assertNotIn("@DISPLAY@", guide)
            self.assertNotIn(str(creator.ROOT), guide)
            tools = json.loads((project / "scripts/security-tools.json").read_text())
            for version in (tools["cargo-audit"], tools["npm"], tools["trivy"]):
                self.assertIn(version, guide)

    def test_standalone_pin_checker_without_external_tools(self):
        with tempfile.TemporaryDirectory(prefix="standalone-pins-") as temporary:
            project = creator.generate("pin-notes", Path(temporary) / "application")
            environment = os.environ.copy()
            environment["PATH"] = ""
            result = subprocess.run([sys.executable, str(project / "scripts/check-toolchain-pins.py")],
                                    cwd=temporary, env=environment, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS:", result.stdout)
            workflow = (project / ".github/workflows/ci.yml").read_text()
            self.assertIn("python3 scripts/check-toolchain-pins.py", workflow)
            self.assertIn("working-directory: .", workflow)

    def test_onboarding_paths_scripts_and_identity(self):
        with tempfile.TemporaryDirectory(prefix="onboarding-docs-") as temporary:
            project = creator.generate("dev-notes", Path(temporary) / "application")
            scripts = json.loads((project / "frontend/package.json").read_text())["scripts"]
            for filename in ("README.md", "CONTRIBUTING.md", "MAINTENANCE.md", "AGENTS.md", "SECURITY.md"):
                text = (project / filename).read_text()
                for placeholder in ("@NAME@", "@DISPLAY@"):
                    self.assertNotIn(placeholder, text, filename)
                for command in re.findall(r"npm run ([a-zA-Z0-9:_-]+)", text):
                    self.assertIn(command, scripts, (filename, command))
                for path in re.findall(r"(?:python3|sh) ((?:\.\./)?scripts/[a-zA-Z0-9_.-]+)", text):
                    local = path.removeprefix("../")
                    self.assertTrue((project / local).is_file(), (filename, path))
                for path in re.findall(r"`((?:backend|frontend)/(?:src|tests|migrations|build\.rs)[a-zA-Z0-9_./-]*)`", text):
                    self.assertTrue((project / path).exists(), (filename, path))
            readme = (project / "README.md").read_text()
            contributing = (project / "CONTRIBUTING.md").read_text()
            self.assertIn("# Dev Notes", readme)
            self.assertIn('git commit -m "Initial application"', contributing)
            self.assertTrue((project / "backend/migrations/0001_greeting.sql").is_file())
            self.assertFalse((project / ".git").exists())
            self.assertIn("No upstream starter remote", contributing)

    def test_invalid_names_do_not_create_destinations(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "app"
            for name in ("", "../escape", "UPPER", "bad_name", "-bad", "bad-", "bad--name", "9app",
                         "a" * 33, "std", "core", "axum", "serde", "tower-http", "self", "crate", "con", "lpt1", "x;touch file", "éclair"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    creator.generate(name, destination)
                self.assertFalse(destination.exists())

    def test_existing_destinations_and_symlinks_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            sentinel = existing / "keep"
            sentinel.write_text("unchanged")
            file = root / "file"
            file.touch()
            link = root / "link"
            link.symlink_to(root / "absent")
            empty = root / "empty"
            empty.mkdir()
            for destination in (existing, file, link, empty):
                with self.subTest(destination=destination), self.assertRaises(ValueError):
                    creator.generate("garden-notes", destination)
            self.assertEqual(sentinel.read_text(), "unchanged")
            self.assertTrue(link.is_symlink())

    def test_missing_parent_and_source_repository_destination_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(FileNotFoundError):
            creator.generate("garden-notes", Path(temporary) / "missing/app")
        with self.assertRaises(ValueError):
            creator.generate("garden-notes", creator.ROOT / "should-not-be-generated")

    def test_failed_staging_and_concurrent_creation_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "app"
            with mock.patch.object(creator, "customize", side_effect=ValueError("upstream drift")):
                with self.assertRaises(ValueError):
                    creator.generate("garden-notes", destination)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])
            original = creator.customize
            def race(*args):
                destination.mkdir(exist_ok=True)
                (destination / "keep").write_text("concurrent")
                return original(*args)
            with mock.patch.object(creator, "customize", side_effect=race):
                with self.assertRaises(FileExistsError):
                    creator.generate("garden-notes", destination)
            self.assertEqual((destination / "keep").read_text(), "concurrent")

    def test_failed_publication_removes_only_the_claimed_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "app"
            with mock.patch.object(creator.shutil, "move", side_effect=OSError("publication failed")):
                with self.assertRaises(OSError):
                    creator.generate("garden-notes", destination)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_source_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "app"
            with mock.patch.object(Path, "is_symlink", autospec=True,
                                   side_effect=lambda path: path.name == "Dockerfile"):
                with self.assertRaisesRegex(ValueError, "ordinary source file"):
                    creator.generate("garden-notes", destination)
            self.assertFalse(destination.exists())


@unittest.skipUnless(RUN_RUSTFMT, "Use --rustfmt for pinned Rust formatting integration tests")
class GeneratedFormattingTests(unittest.TestCase):
    def test_generated_names_pass_rustfmt(self):
        with tempfile.TemporaryDirectory(prefix="generated-format-") as temporary:
            # Sweep every supported length as well as representative identities.
            # The fast tests separately assert rejection of 33-character names.
            for name in (*FORMAT_NAMES, *("x" * length for length in range(1, 33))):
                with self.subTest(name=name):
                    destination = creator.generate(name, Path(temporary) / name)
                    sources = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                               for path in (destination / "backend").rglob("*.rs")}
                    result = subprocess.run(["cargo", "fmt", "--all", "--", "--check"],
                                            cwd=destination / "backend", text=True,
                                            capture_output=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(sources, {path: (path.read_bytes(), path.stat().st_mtime_ns)
                                               for path in (destination / "backend").rglob("*.rs")},
                                     "Formatting checks must not rewrite generated Rust files")


if __name__ == "__main__":
    unittest.main()
