#!/usr/bin/env python3
"""Offline positive/negative pin checks using disposable declaration copies."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT if (ROOT / "backend/Cargo.toml").exists() else ROOT / "templates" / "light"
SPEC = importlib.util.spec_from_file_location("pin_checker", Path(__file__).with_name("check-toolchain-pins.py"))
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class PinTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pin-consistency-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / PROJECT.relative_to(ROOT)
        paths = [PROJECT / name for name in (
            "backend/rust-toolchain.toml", "backend/Cargo.toml", "backend/Cargo.lock",
            "frontend/.node-version", "frontend/package.json", "frontend/package-lock.json", "Dockerfile")]
        paths += [ROOT / name for name in (
            "scripts/security-tools.json", "scripts/install-security-tools.sh",
            ".github/workflows/ci.yml", ".github/workflows/security.yml")]
        guide = ROOT / "SECURITY-SCANNING.md"
        paths.append(guide if guide.exists() else ROOT / "docs/development/SECURITY-SCANNING.md")
        paths += [ROOT / name for name in ("README.md", "CONTRIBUTING.md") if (ROOT / name).exists()]
        for source in paths:
            target = self.root / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def replace(self, path, old, new):
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def edit_json(self, path, edit):
        content = json.loads(path.read_text())
        edit(content)
        path.write_text(json.dumps(content))

    def errors(self):
        return checker.check(self.root)[0]

    def fails(self, *filenames):
        errors = self.errors()
        self.assertTrue(errors)
        for name in filenames:
            self.assertIn(name, "\n".join(errors))

    def test_valid_current_declarations(self):
        self.assertEqual(self.errors(), [])

    def test_rust_builder_mismatch(self):
        docker = self.project / "Dockerfile"
        self.replace(docker, "FROM rust:", "FROM rust:0.0.1-unused-")
        self.fails("Dockerfile", "rust-toolchain.toml", "0.0.1")

    def test_selected_rust_mismatch(self):
        path = self.project / "backend/rust-toolchain.toml"
        data = checker.tomllib.loads(path.read_text())
        self.replace(path, data["toolchain"]["channel"], "99.0.0")
        self.fails("Dockerfile", "rust-toolchain.toml", "security-tools.json")

    def test_msrv_above_selected_compiler(self):
        path = self.project / "backend/Cargo.toml"
        msrv = checker.tomllib.loads(path.read_text())["package"]["rust-version"]
        self.replace(path, f'rust-version = "{msrv}"', 'rust-version = "99.0"')
        self.fails("Cargo.toml", "rust-toolchain.toml", "MSRV")

    def test_lower_msrv_is_valid(self):
        path = self.project / "backend/Cargo.toml"
        msrv = checker.tomllib.loads(path.read_text())["package"]["rust-version"]
        self.replace(path, f'rust-version = "{msrv}"', 'rust-version = "1.90"')
        self.assertEqual(self.errors(), [])

    def test_node_exact_pin_mismatch(self):
        (self.project / "frontend/.node-version").write_text("99.0.0\n")
        self.fails(".node-version", "Dockerfile", "package.json")

    def test_compatible_engine_ranges(self):
        selected = checker.version((self.project / "frontend/.node-version").read_text().strip(), "test")
        major, minor, patch = selected
        for constraint in (f">={major} <{major+1}", f"^{major}.0.0", f"~{major}.{minor}.0",
                           f"{major}.x", f"{major}.{minor}.*", f"{major} - {major}",
                           f"{major-1}.x || >={major}.{minor}.{patch}"):
            with self.subTest(constraint=constraint):
                self.edit_json(self.project / "frontend/package.json", lambda value: value["engines"].update(node=constraint))
                self.assertEqual(self.errors(), [])

    def test_engine_range_excludes_selected_pin(self):
        self.edit_json(self.project / "frontend/package.json", lambda value: value["engines"].update(node="<1"))
        self.fails("package.json", ".node-version", "outside engines.node")

    def test_unsupported_engine_syntax_is_explicit(self):
        self.edit_json(self.project / "frontend/package.json", lambda value: value["engines"].update(node="not-a-range"))
        self.fails("package.json", "Unsupported engines.node")

    def test_npm_metadata_mismatch(self):
        self.edit_json(self.project / "frontend/package.json", lambda value: value.update(packageManager="npm@99.0.0"))
        self.fails("package.json", "security-tools.json", "npm@99.0.0")

    def test_security_ci_npm_mismatch(self):
        path = self.root / ".github/workflows/security.yml"
        current = json.loads((self.root / "scripts/security-tools.json").read_text())["npm"]
        self.replace(path, "npm@" + current, "npm@99.0.0")
        self.fails("security.yml", "security-tools.json")

    def test_scanner_manifest_and_current_guide_mismatch(self):
        self.edit_json(self.root / "scripts/security-tools.json", lambda value: value.update(trivy="99.0.0"))
        self.fails("SECURITY-SCANNING.md", "security-tools.json", "99.0.0")

    def test_installer_version_and_integrity_guards(self):
        path = self.root / "scripts/install-security-tools.sh"
        original = path.read_text()
        for old, new in (('"$(version cargo-audit)"', '"99.0.0"'),
                         ('trivy_version=$(version trivy)', 'trivy_version=99.0.0'),
                         ('sha256sum --check', 'true'), (' --locked', '')):
            with self.subTest(mutation=old):
                path.write_text(original.replace(old, new))
                self.fails("install-security-tools.sh", "security-tools.json")
        path.write_text(original)

    def test_missing_and_malformed_checksum(self):
        path = self.root / "scripts/security-tools.json"
        original = path.read_text()
        for checksum in (None, "not-a-sha256", "a" * 63, int("1" * 64)):
            path.write_text(original)
            if checksum is None:
                self.edit_json(path, lambda value: value.pop("trivy-linux-amd64-sha256"))
            else:
                self.edit_json(path, lambda value: value.update({"trivy-linux-amd64-sha256": checksum}))
            self.fails("security-tools.json", "64-hex")

    def test_intentional_scanner_update_not_pinned_forever(self):
        tools = self.root / "scripts/security-tools.json"
        current = json.loads(tools.read_text())["trivy"]
        guide = self.root / ("SECURITY-SCANNING.md" if (self.root / "SECURITY-SCANNING.md").exists() else "docs/development/SECURITY-SCANNING.md")
        self.edit_json(tools, lambda value: value.update(trivy="99.0.0", **{"trivy-linux-amd64-sha256": "a" * 64}))
        self.replace(guide, "Trivy " + current, "Trivy 99.0.0")
        # Only format is checked offline; this synthetic checksum is not authenticated.
        self.assertEqual(self.errors(), [])

    def test_cargo_ranges_are_not_compared_to_locked_versions(self):
        path = self.project / "backend/Cargo.toml"
        constraint = checker.tomllib.loads(path.read_text())["dependencies"]["axum"]["version"]
        self.replace(path, f'axum = {{ version = "{constraint}"', 'axum = { version = ">=0.1, <99"')
        self.assertEqual(self.errors(), [])

    def test_sqlx_revision_agrees_with_lock_but_can_be_replaced(self):
        path = self.project / "backend/Cargo.toml"
        original = path.read_text()
        data = checker.tomllib.loads(original)["dependencies"]["sqlx"]
        if isinstance(data, dict) and "git" in data:
            self.replace(path, data["rev"], "0" * 40)
            self.fails("Cargo.toml", "Cargo.lock", "Git revision")
        # Source kind is checkable; version compatibility still needs Cargo.
        path.write_text(checker.re.sub(r"^sqlx = .*", 'sqlx = ">=0.1, <99"', original, flags=checker.re.M))
        lock = self.project / "backend/Cargo.lock"
        entries = checker.tomllib.loads(lock.read_text())["package"]
        sqlx_sources = {p.get("source", "") for p in entries if p["name"] == "sqlx"}
        if not any(source.startswith("registry+") for source in sqlx_sources):
            self.fails("Cargo.toml", "Cargo.lock", "registry lock entry")
            registry = next(p["source"] for p in entries if p.get("source", "").startswith("registry+"))
            for source in sqlx_sources:
                self.replace(lock, source, registry)
        self.assertEqual(self.errors(), [])

    def test_override_can_be_removed_intentionally(self):
        self.edit_json(self.project / "frontend/package.json", lambda value: value.pop("overrides", None))
        self.assertEqual(self.errors(), [])

    def test_ci_rust_and_node_reader_drift(self):
        path = self.root / ".github/workflows/ci.yml"
        original = path.read_text()
        path.write_text(original.replace("node-version-file: ", "node-version-file: ./"))
        self.assertEqual(self.errors(), [])
        path.write_text(original.replace("cargo test --locked", "cargo +99.0.0 test --locked"))
        self.fails("ci.yml", "rust-toolchain.toml")
        path.write_text(original + '\n# literal compiler assignment drift fixture\n          toolchain="99.0.0"\n')
        self.fails("ci.yml", "rust-toolchain.toml")
        path.write_text(original.replace("node-version-file:", "node-version-file: missing-file #"))
        self.fails("ci.yml", ".node-version")

    def test_current_documentation_claims_but_not_historical_snapshots(self):
        path = self.root / "CONTRIBUTING.md"
        with path.open("a") as stream:
            stream.write("\nUse Rust 99.0.0 through rustup.\n")
        self.fails("CONTRIBUTING.md", "rust-toolchain.toml", "99.0.0")
        path.write_text("Historical snapshot: Rust 99.0.0 was previously considered.\n")
        self.assertEqual(self.errors(), [])

    def test_without_external_tools_network_or_file_changes(self):
        def snapshot():
            return {p.relative_to(self.root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                    for p in self.root.rglob("*") if p.is_file()}
        before = snapshot()
        with mock.patch("socket.socket", side_effect=AssertionError("Network forbidden")), \
             mock.patch("subprocess.run", side_effect=AssertionError("External tools forbidden")):
            self.assertEqual(self.errors(), [])
        environment = os.environ.copy()
        environment["PATH"] = ""
        result = subprocess.run([sys.executable, str(ROOT / "scripts/check-toolchain-pins.py"), "--root", str(self.root)],
                                text=True, capture_output=True, env=environment, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(), before)
        self.edit_json(self.project / "frontend/package.json", lambda value: value.update(packageManager="npm@99.0.0"))
        result = subprocess.run([sys.executable, str(ROOT / "scripts/check-toolchain-pins.py"), "--root", str(self.root)],
                                text=True, capture_output=True, env=environment, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("package.json", result.stdout)
        self.assertIn("security-tools.json", result.stdout)


if __name__ == "__main__":
    unittest.main()
