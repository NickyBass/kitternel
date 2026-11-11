#!/usr/bin/env python3
"""Test standalone generation; opt into pinned Rust formatting with --rustfmt."""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("create_light", Path(__file__).with_name("create-light.py"))
creator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(creator)


# Cover imports before axum, between dependencies, and after std/tokio/tower.
FORMAT_NAMES = ("a-app", "audit-notes-7a", "maple-notes", "sunrise-notes", "zebra-notes")
RUN_RUSTFMT = "--rustfmt" in sys.argv
if RUN_RUSTFMT:
    sys.argv.remove("--rustfmt")


class GenerationTests(unittest.TestCase):
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
            for name in FORMAT_NAMES:
                with self.subTest(name=name):
                    destination = creator.generate(name, Path(temporary) / name)
                    result = subprocess.run(["cargo", "fmt", "--all", "--", "--check"],
                                            cwd=destination / "backend", text=True,
                                            capture_output=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
