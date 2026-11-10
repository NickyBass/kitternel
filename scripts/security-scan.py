#!/usr/bin/env python3
"""Run pinned scanners, publish sanitized reports, and enforce an explicit policy.

Exit 0: completed and policy passed; 1: completed with blocking findings;
2: incomplete scan/tool/database/schema failure. No dependency updates or ignores.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

TOOLS = json.loads(Path(__file__).with_name("security-tools.json").read_text())


def select(value, keys):
    return {key: value[key] for key in keys if key in value}


def execute(arguments):
    result = subprocess.run(arguments, text=True, capture_output=True, timeout=900)
    return result.returncode, result.stdout


def scan_json(arguments, allowed=(0,)):
    code, output = execute(arguments)
    if code not in allowed:
        raise ValueError(f"Scanner command failed with exit {code}; check tool installation, registry/DB access, CA trust, and disk space")
    report = json.loads(output)
    if not isinstance(report, dict) or "error" in report:
        raise ValueError("Scanner did not return a complete supported report; check registry/DB availability")
    return code, report


def require_version(command, expected):
    code, output = execute(command)
    if code or expected not in output.split():
        raise ValueError(f"Expected pinned scanner version {expected}; use scripts/install-security-tools.sh and security-tools.json")


def rust_report(report, code):
    settings = report["settings"]
    if settings["ignore"] or settings["severity"] is not None or settings["target_arch"] or settings["target_os"]:
        raise ValueError("RustSec report was filtered; remove local ignores, severity, or target filters")
    vulnerabilities = report["vulnerabilities"]
    entries = vulnerabilities["list"]
    if report["database"]["advisory-count"] <= 0 or vulnerabilities["count"] != len(entries):
        raise ValueError("Incomplete RustSec database or vulnerability count mismatch")
    if bool(entries) != bool(code):
        raise ValueError("RustSec exit status and vulnerability report disagree")
    def entry(item):
        return {"package": select(item["package"], ("name", "version")),
                "advisory": select(item["advisory"], ("id", "title", "package", "date", "url", "cvss", "informational", "aliases")),
                "versions": item.get("versions", {})}
    cleaned = {"database": select(report["database"], ("advisory-count", "last-commit", "last-updated")),
               "vulnerabilities": [entry(item) for item in entries],
               "warnings": {kind: [entry(item) for item in items] for kind, items in report["warnings"].items()}}
    return cleaned, len(entries)


def npm_report(report):
    if report["auditReportVersion"] != 2 or not isinstance(report["vulnerabilities"], dict):
        raise ValueError("Unsupported npm audit report")
    if report["metadata"]["vulnerabilities"]["total"] != len(report["vulnerabilities"]):
        raise ValueError("Incomplete npm vulnerability counts")
    report["metadata"]["dependencies"]["total"]
    cleaned = {"auditReportVersion": 2, "metadata": select(report["metadata"], ("vulnerabilities", "dependencies")), "vulnerabilities": {}}
    blocking = 0
    for name, item in report["vulnerabilities"].items():
        value = select(item, ("name", "severity", "isDirect", "range", "nodes", "effects", "fixAvailable"))
        severity = item.get("severity") or "unknown"
        if not isinstance(severity, str):
            raise ValueError("Malformed npm severity")
        value["severity"] = severity.lower()
        value["via"] = [select(via, ("source", "name", "dependency", "title", "url", "severity", "cwe", "cvss", "range"))
                        if isinstance(via, dict) else via for via in item["via"]]
        cleaned["vulnerabilities"][name] = value
        blocking += value["severity"] in ("high", "critical")
    return cleaned, blocking


def image_report(report):
    if report["SchemaVersion"] != 2 or report["ArtifactType"] != "container_image" or not report.get("Results"):
        raise ValueError("Unsupported/incomplete Trivy image report")
    results = []
    blocking = 0
    for result in report["Results"]:
        cleaned = select(result, ("Target", "Class", "Type"))
        cleaned["Vulnerabilities"] = []
        for item in result.get("Vulnerabilities", []):
            value = select(item, ("VulnerabilityID", "PkgName", "InstalledVersion", "FixedVersion", "Severity", "SeveritySource", "PrimaryURL", "Title", "Status", "CVSS", "CweIDs"))
            severity = item.get("Severity") or "UNKNOWN"
            if not isinstance(severity, str):
                raise ValueError("Malformed Trivy severity")
            value["Severity"] = severity.upper()
            cleaned["Vulnerabilities"].append(value)
            blocking += value["Severity"] in ("HIGH", "CRITICAL")
        results.append(cleaned)
    # ImageConfig and history can contain environment values. Never publish them.
    return {"SchemaVersion": 2, "ArtifactName": report["ArtifactName"], "ArtifactType": "container_image",
            "Metadata": {"OS": report["Metadata"]["OS"]}, "Results": results}, blocking


def write_report(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("rust", "npm", "image"))
    parser.add_argument("--project", required=True, type=Path, help="Application directory containing backend/frontend")
    parser.add_argument("--reports", type=Path, default=Path("security-reports"))
    parser.add_argument("--image", help="Already-built final production image for image scans")
    args = parser.parse_args(arguments)
    args.reports.mkdir(parents=True, exist_ok=True)
    # Remove only this component's prior outputs so failures cannot publish stale passes.
    for suffix in (".json", ".status.json", ".summary.md", ".sarif"):
        path = args.reports / (args.kind + suffix)
        if path.is_file():
            path.unlink()
    status = {"scanner": args.kind, "status": "infrastructure-error", "exit_code": 2,
              "scanned_at": datetime.now(timezone.utc).isoformat()}
    code = 2
    details = []
    try:
        if args.kind == "rust":
            require_version(["cargo", "audit", "--version"], TOOLS["cargo-audit"])
            returned, report = scan_json(["cargo", "audit", "--json", "--file", str(args.project / "backend/Cargo.lock")], allowed=(0, 1))
            report, blocking = rust_report(report, returned)
            write_report(args.reports / "rust.json", report)
            details = report["vulnerabilities"] + [{"informational": kind, **item} for kind, items in report["warnings"].items() for item in items]
            status["version"] = TOOLS["cargo-audit"]
        elif args.kind == "npm":
            require_version(["npm", "--version"], TOOLS["npm"])
            reports = {}
            for scope, flag in (("all", "--include=dev"), ("production", "--omit=dev")):
                returned, report = scan_json(["npm", "audit", "--json", "--audit-level=low", flag, "--prefix", str(args.project / "frontend")], allowed=(0, 1))
                reports[scope], count = npm_report(report)
                if returned and not report["vulnerabilities"]:
                    raise ValueError("npm audit failed without vulnerability findings; scan is incomplete")
                if scope == "production":
                    blocking = count
            write_report(args.reports / "npm.json", reports)
            details = [{"scope": scope, **item} for scope, report in reports.items() for item in report["vulnerabilities"].values()]
            status["version"] = TOOLS["npm"]
        else:
            if not args.image:
                raise ValueError("Image scanning requires --image pointing to an already-built final image")
            require_version(["trivy", "--version"], TOOLS["trivy"])
            _, report = scan_json(["trivy", "image", "--config", "", "--ignorefile", "", "--ignore-policy", "",
                                   "--ignore-status", "", "--skip-dirs", "", "--skip-files", "", "--ignore-unfixed=false",
                                   "--severity", "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL", "--pkg-types", "os,library",
                                   "--image-src", "docker", "--scanners", "vuln", "--format", "json",
                                   "--exit-code", "0", "--timeout", "10m", args.image])
            report, blocking = image_report(report)
            write_report(args.reports / "image.json", report)
            code_convert, _ = execute(["trivy", "convert", "--format", "sarif", "--output", str(args.reports / "image.sarif"), str(args.reports / "image.json")])
            if code_convert:
                raise ValueError("Trivy SARIF conversion failed; JSON scan exists but reporting is incomplete")
            sarif = json.loads((args.reports / "image.sarif").read_text())
            if sarif["version"] != "2.1.0" or not isinstance(sarif["runs"], list):
                raise ValueError("Trivy did not produce supported SARIF")
            details = [item for result in report["Results"] for item in result["Vulnerabilities"]]
            status["version"] = TOOLS["trivy"]
        code = 1 if blocking else 0
        status.update(status="policy-failed" if blocking else "passed", exit_code=code, blocking_findings=blocking)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        # Do not copy scanner stderr/HTTP errors: they can include registry credentials.
        status["reason"] = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else type(error).__name__
    write_report(args.reports / f"{args.kind}.status.json", status)
    summary = f"## {args.kind} security scan\n\nStatus: **{status['status']}**, exit `{code}`.\n\n"
    if "reason" in status:
        summary += "Scan incomplete: check scanner version, installation, database/registry access, and CA trust. No clean result is claimed.\n"
    priorities = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "MODERATE": 2, "UNKNOWN": 3, "LOW": 4, "INFO": 5}
    details.sort(key=lambda item: priorities.get(item.get("Severity", item.get("severity", "UNKNOWN")).upper(), 3))
    counts = Counter(item.get("Severity", item.get("severity", "UNKNOWN")) for item in details)
    summary += "\nReported severity counts (Rust entries retain CVSS vectors): " + json.dumps(dict(counts), sort_keys=True) + "\n"
    summary += "\nFindings below are scanner reports, not proof of exploitability. Full details are in JSON artifacts.\n\n```json\n"
    summary += json.dumps(details[:50], indent=2).replace("`", "\\u0060") + "\n```\n"
    if len(details) > 50:
        summary += f"\nShowing 50 of {len(details)} entries; download the full JSON report.\n"
    (args.reports / f"{args.kind}.summary.md").write_text(summary, encoding="utf-8")
    print(f"{args.kind}: {status['status']} (exit {code}); reports: {args.reports}")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError:
        print("Security reports could not be written; check the output directory and permissions. Scan incomplete.", file=sys.stderr)
        sys.exit(2)
