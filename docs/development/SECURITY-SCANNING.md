# Vulnerability scanning

These are development/CI tools, never runtime dependencies. Pins live in `scripts/security-tools.json`: cargo-audit 0.23.0, npm 11.9.0, Trivy 0.76.2. Installation uses a locked cargo-audit build and a Trivy Linux/amd64 archive with a reviewed SHA-256. New advisories arrive independently of tool pins: results are time-dependent, not proof of vulnerability-free software.

## Local commands

From the project/repository root, install the tools into a user-owned directory and add its bin directory to PATH:

```sh
sh scripts/install-security-tools.sh rust /tmp/security-tools
sh scripts/install-security-tools.sh image /tmp/security-tools
export PATH="/tmp/security-tools/bin:$PATH"
# Use Node 24 and npm 11.9.0 as pinned; CI installs that npm explicitly.
# If needed, install npm in your user-managed Node environment:
# npm install --global npm@11.9.0 --ignore-scripts --no-audit --no-fund
python3 scripts/security-scan.py rust --project templates/light
python3 scripts/security-scan.py npm --project templates/light
docker build -t kitternel-light:local templates/light
python3 scripts/security-scan.py image --project templates/light --image kitternel-light:local
```

Rust audit reads the existing Cargo.lock; npm audit reads the existing package-lock without executing install scripts. Both npm production and development dependency graphs are reported, with a separate production audit for enforcement. No command updates dependencies or runs audit fix. Trivy scans the already-built final image from the Docker daemon, including OS and detectable application packages, without a second build. Stripped Rust binaries and bundled frontend dependencies are not a complete Trivy inventory: the separate Rust/npm checks remain mandatory.

Trivy needs a writable cache and vulnerability database access. You may select an allowed official DB repository with `TRIVY_DB_REPOSITORY=ghcr.io/aquasecurity/trivy-db:2` if the default official mirror is unavailable. Do not disable TLS or use stale/empty databases as a clean result. For managed build proxies, use the canonical Dockerfile's optional public CA BuildKit secret. Unsupported tool installations, registry/DB failures, malformed/filtered reports, and wrong versions fail distinctly.

## Enforcement

The wrapper exits **0** for a completed non-blocking result, **1** for blocking findings, and **2** for an incomplete/infrastructure failure. Download `*.status.json` to distinguish them; installation/build failures also retain their failing CI step. No `continue-on-error` or blanket ignores are used.

- Rust: conservatively block every RustSec vulnerability in the complete lockfile, including unknown severity. Informational/unmaintained/unsound warnings remain visible separately and do not alone fail. The lockfile can contain optional/unselected, development, build, or other-target packages; a block does not establish production exploitability. Use Cargo tree/features to assess actual exposure before remediation. JSON retains CVSS vectors; `cargo audit --file templates/light/backend/Cargo.lock` also prints numeric scores/severity when available.
- npm: block HIGH/CRITICAL in the production audit. Keep all dev/tooling findings, lower severities, unknown severities, advisory paths, and fix suggestions visible in the full report. Compare all versus production reports to identify development-only exposure. Development-only findings are reporting-only, not silently discarded.
- Image: block HIGH/CRITICAL for all detected runtime package findings, even without a published fix. Keep MEDIUM/LOW/UNKNOWN and vendor status visible. Disabled default ignore/config files and explicit all-severity/package-type settings prevent incidental local ignore files from hiding results. Vendor backports, package presence, and reachability need investigation; a scanner hit is not proof that the application exposes the flaw.

Review each advisory ID, affected version, dependency path, feature/target selection, attack prerequisites, vendor status, and patched versions. Prefer a small reviewed update with compatibility, native/frontend, and Docker/recovery checks. Never apply forced upgrades or suppress findings merely to pass CI. For a necessary temporary exception, propose a separate narrowly scoped policy change with advisory/package/version/target, evidence, owner, expiry, review date, and regression coverage; retain the original finding. No exceptions are configured here.

## CI, reports, and permissions

Security runs on relevant application/tool/workflow pull requests, relevant pushes to main, weekly Monday 06:23 UTC, and workflow_dispatch. Unrelated documentation changes do not trigger it. The existing Docker build/smoke job moved from CI to Security, so its final image is built once and used by both tests and scanner. The independent extraction-validation workflow remains separate because it verifies a different generated application.

The dependency and image jobs have read-only repository permissions, no private registry secrets, no application install hooks, and no privileged pull_request_target or workflow_run handling. Third-party actions are pinned to commits. Scans for the same ref are serialized without hiding a failed result. Other scans/tests still run after a policy failure; that failure remains a failed job. If branch protection previously required `CI / docker`, update it to the corresponding Security docker check.

JSON, summaries, and image SARIF are downloadable Actions artifacts retained for 14 days, including blocking results. Image configuration/environment/history and raw scanner stderr are excluded. Upload only these sanitized reports, never raw Docker inspect/config, registry credentials, application databases, or scanner caches.

Code Scanning availability is **not assumed**. Its repository visibility/plan/settings could not be verified through the API in this environment. Maintainers must confirm support and enable it before setting repository variable `ENABLE_CODE_SCANNING=true`. Only then does a separate non-PR job request security-events write permission and upload image SARIF. Fork PR scans never receive that permission. Upload/configuration failure is visible; artifacts remain the default supported route. Generated projects inherit the same explicit opt-in and must check their own plan/settings.

## Scope and limits

Generated projects receive their own security workflow, wrapper, installer, pins, tests, and this guide; no original checkout or generator is required after extraction. Configure branch filters if the default branch differs from main. Host-specific findings can differ from complete-lockfile findings. Database freshness, scanner coverage, vendor severity, false positives, and unavailable fixes require human review. Scanning does not replace application review, authorization/input-validation tests, configuration review, or operational backup/restore drills. It does not validate deployments or establish production readiness.
