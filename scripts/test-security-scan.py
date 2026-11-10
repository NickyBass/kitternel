#!/usr/bin/env python3
"""Security policy and failure/sanitization regressions; no network or scanners required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("security_scan", Path(__file__).with_name("security-scan.py"))
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def advisory():
    return {"package": {"name": "example", "version": "1.0", "source": "PRIVATE"},
            "advisory": {"id": "RUSTSEC-test", "title": "Example", "cvss": None},
            "versions": {"patched": [">=2"]}}


def rust(entries=None, warnings=None):
    entries = entries or []
    return {"database": {"advisory-count": 1, "last-commit": "abc"},
            "settings": {"ignore": [], "severity": None, "target_arch": [], "target_os": []},
            "vulnerabilities": {"count": len(entries), "list": entries}, "warnings": warnings or {}}


def npm(severity=None):
    values = {} if severity is None else {"example": {"name": "example", "severity": severity,
                "nodes": ["node_modules/example"], "via": [{"url": "https://example.com/advisory"}],
                "fixAvailable": {"name": "example", "version": "2", "isSemVerMajor": True}}}
    return {"auditReportVersion": 2, "metadata": {"vulnerabilities": {"total": len(values)},
            "dependencies": {"total": 1}}, "vulnerabilities": values}


def image(severity="UNKNOWN"):
    return {"SchemaVersion": 2, "ArtifactType": "container_image", "ArtifactName": "example:local",
            "Metadata": {"OS": {"Family": "debian"}, "ImageConfig": {"Env": ["TOKEN=PRIVATE"]}},
            "Results": [{"Class": "os-pkgs", "Type": "debian", "Target": "debian",
                         "Vulnerabilities": [{"VulnerabilityID": "CVE-example", "Severity": severity,
                                              "PkgName": "example", "InstalledVersion": "1", "FixedVersion": "2"}]}]}


class SecurityTests(unittest.TestCase):
    def test_rust_vulnerabilities_block_but_informationals_do_not(self):
        cleaned, blocking = scan.rust_report(rust([advisory()]), 1)
        self.assertEqual(blocking, 1)
        self.assertNotIn("PRIVATE", json.dumps(cleaned))
        cleaned, blocking = scan.rust_report(rust(warnings={"unmaintained": [advisory()]}), 0)
        self.assertEqual(blocking, 0)
        self.assertIn("unmaintained", cleaned["warnings"])

    def test_filtered_or_inconsistent_rust_results_are_rejected(self):
        for field, value in (("ignore", ["RUSTSEC-test"]), ("severity", "high"), ("target_os", ["linux"])):
            report = rust()
            report["settings"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                scan.rust_report(report, 0)
        with self.assertRaises(ValueError):
            scan.rust_report(rust([advisory()]), 0)
        report = rust()
        report["database"]["advisory-count"] = 0
        with self.assertRaises(ValueError):
            scan.rust_report(report, 0)

    def test_npm_threshold_and_unknowns_retain_paths_and_fixes(self):
        for severity in ("critical", "high", "moderate", "low", "unknown"):
            cleaned, blocking = scan.npm_report(npm(severity))
            self.assertEqual(blocking, int(severity in ("critical", "high")))
            self.assertEqual(cleaned["vulnerabilities"]["example"]["nodes"], ["node_modules/example"])
            self.assertIn("fixAvailable", cleaned["vulnerabilities"]["example"])

    def test_npm_dev_only_high_is_reported_without_blocking_production(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(scan, "require_version"), mock.patch.object(scan, "scan_json", side_effect=[(1, npm("high")), (0, npm())]):
            self.assertEqual(scan.main(["npm", "--project", ".", "--reports", temporary]), 0)
            report = json.loads((Path(temporary) / "npm.json").read_text())
            self.assertIn("example", report["all"]["vulnerabilities"])
            self.assertEqual(report["production"]["vulnerabilities"], {})

    def test_npm_production_high_blocks(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(scan, "require_version"), mock.patch.object(scan, "scan_json", return_value=(1, npm("high"))):
            self.assertEqual(scan.main(["npm", "--project", ".", "--reports", temporary]), 1)

    def test_image_threshold_sanitization_and_unknown_visibility(self):
        for severity in ("HIGH", "CRITICAL", "MEDIUM", "LOW", "UNKNOWN"):
            cleaned, blocking = scan.image_report(image(severity))
            self.assertEqual(blocking, int(severity in ("HIGH", "CRITICAL")))
            self.assertNotIn("ImageConfig", json.dumps(cleaned))
            self.assertNotIn("PRIVATE", json.dumps(cleaned))
            self.assertEqual(cleaned["Results"][0]["Vulnerabilities"][0]["Severity"], severity)

    def test_command_failures_and_error_payloads_cannot_be_clean(self):
        for code, text in ((2, '{}'), (1, '{"error":"PRIVATE"}'), (0, 'not JSON')):
            with self.subTest(code=code, text=text), mock.patch.object(scan, "execute", return_value=(code, text)):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    scan.scan_json(["scanner"], allowed=(0, 1))

    def test_missing_tool_invalid_schema_and_conversion_errors_are_infrastructure(self):
        for failure in (FileNotFoundError("PRIVATE"), KeyError("PRIVATE"), ValueError("Scanner installation failed")):
            with tempfile.TemporaryDirectory() as temporary, mock.patch.object(scan, "require_version", side_effect=failure):
                directory = Path(temporary)
                (directory / "image.json").write_text('old clean report')
                self.assertEqual(scan.main(["image", "--project", ".", "--image", "example", "--reports", temporary]), 2)
                self.assertFalse((directory / "image.json").exists())
                status = json.loads((directory / "image.status.json").read_text())
                self.assertEqual(status["status"], "infrastructure-error")
                self.assertNotIn("PRIVATE", (directory / "image.status.json").read_text())
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(scan, "require_version"), mock.patch.object(scan, "scan_json", return_value=(0, image())), mock.patch.object(scan, "execute", return_value=(1, "PRIVATE")):
            self.assertEqual(scan.main(["image", "--project", ".", "--image", "example", "--reports", temporary]), 2)

    def test_image_scan_forces_all_packages_and_no_incidental_ignores(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            def convert(arguments):
                (directory / "image.sarif").write_text('{"version":"2.1.0","runs":[]}')
                return 0, ""
            with mock.patch.object(scan, "require_version"), mock.patch.object(scan, "scan_json", return_value=(0, image())) as command, mock.patch.object(scan, "execute", side_effect=convert):
                self.assertEqual(scan.main(["image", "--project", ".", "--image", "example", "--reports", temporary]), 0)
                arguments = command.call_args.args[0]
                self.assertEqual(arguments[arguments.index("--ignorefile") + 1], "")
                self.assertEqual(arguments[arguments.index("--config") + 1], "")
                for flag in ("--ignore-policy", "--ignore-status", "--skip-dirs", "--skip-files"):
                    self.assertEqual(arguments[arguments.index(flag) + 1], "")
                self.assertIn("--ignore-unfixed=false", arguments)
                self.assertIn("os,library", arguments)
                self.assertIn("UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL", arguments)
                self.assertEqual(arguments[arguments.index("--image-src") + 1], "docker")

    def test_workflow_npm_pin_matches_manifest(self):
        workflow = Path(__file__).resolve().parents[1] / ".github/workflows/security.yml"
        self.assertIn("npm install --global npm@" + scan.TOOLS["npm"], workflow.read_text())

    def test_incomplete_reports_and_wrong_versions_are_rejected(self):
        for report in ({}, {"auditReportVersion": 2}, {"auditReportVersion": 1, "vulnerabilities": {}}):
            with self.assertRaises((ValueError, KeyError)):
                scan.npm_report(report)
        with mock.patch.object(scan, "execute", return_value=(0, "wrong version PRIVATE")):
            with self.assertRaisesRegex(ValueError, "pinned scanner version"):
                scan.require_version(["scanner"], "1.0")


if __name__ == "__main__":
    unittest.main()
