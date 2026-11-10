# Docker-first starter readiness

The current scope is standard Docker and Docker Compose. Platform integrations are deferred. Preserve the existing Rust/Axum/SQLite/React architecture and keep runtime dependencies unchanged.

## PR 1: Report Docker smoke cleanup failures

Branch: `fix/docker-smoke-cleanup`.

The main Docker fixture previously ignored nonzero removal exit codes. It now attempts every tracked container and its data volume, aggregates failures, and fails the owning unittest. Exceptions do not skip later removals. Nested backup fixtures propagate that failure while still attempting their additional volumes. Diagnostics identify resource names and exit codes or exception types without copying potentially sensitive command output.

Only fixture-owned names are removed. Existing intentional container removals also remove the name from tracking. A missing tracked resource is reported as a failure rather than accepting arbitrary daemon errors as harmless.

Acceptance criteria:

- Successful removals leave the test successful.
- Container and volume removal exit codes fail the outer test.
- Timeouts and OS errors do not skip subsequent resources.
- Multiple failures are reported together.
- Nested backup cleanup still attempts extra volumes and fails the outer test.
- Isolated regressions run without Docker and are included in CI.
- Existing Docker/Compose and volume backup/restore drills remain successful.

Run `python3 scripts/test-smoke-cleanup.py -v`, then the Docker and recovery commands in [CONTRIBUTING.md](../../CONTRIBUTING.md).

### PR 1 verification

Executed locally on Linux/amd64 on 2026-11-10:

- `python3 scripts/test-smoke-cleanup.py -v`: five tests passed. Against the original cleanup implementation, the regression suite failed as expected.
- `python3 scripts/docker-smoke.py --image kitternel-light:audit -v`: five tests passed, including non-root/read-only operation, health, graceful shutdown, Compose startup, and persistence across container recreation.
- `python3 scripts/sqlite-backup-smoke.py --image kitternel-light:audit -v`: six tests passed, including live-WAL backup/export and independent-volume restore.
- No fixture containers or volumes remained after the runs; `git diff --check` passed.

The image was reused from the preceding audit because this PR changes only test cleanup, CI, and documentation. No fresh image build, Rust/frontend suite rerun, generated-project verification, remote CI run, or platform deployment is claimed for this PR. Verification of a clean extracted project belongs to PR 4.

## PR 2: Resolve smoke-test binary paths consistently

Depends on PR 1 only for a clean review sequence. Support default, absolute, and relative `CARGO_TARGET_DIR` in native process/browser runners, with one documented resolution rule. Account for the executable suffix on supported hosts. Do not change application code. Test resolution without launching processes, then execute the native and browser suites with a genuinely external target directory and no stale local binary.

## PR 3: Extract and customize a complete standalone project

Implemented on `feat/light-project-generation`: `scripts/create-light.py NAME DESTINATION` generates a standalone layout with curated tracked files, scoped identity/path mappings, standalone documentation/agent instructions, and independent CI. See [CREATE-LIGHT.md](CREATE-LIGHT.md). Source symlinks, invalid names, existing destinations, missing parents, and destinations inside the source repository are rejected. Regression tests cover completeness, metadata/lockfile consistency, long names, default identity, source-layout references, and destination safety. Clean Docker deployment verification remains PR 4.

Depends on PR 2. Choose the smallest reproducible extraction mechanism, with validated project names and no overwriting of existing destinations. Include application code, migrations, lockfiles, Dockerfile, Compose, backup helpers, test runners, CI, documentation, license, and agent instructions. Preserve file modes and LF shell scripts.

Define explicit mappings for the project name, Cargo package, Rust crate identifier, executable, npm package, Docker image, and Compose project identifiers. Update lockfile package metadata consistently. Avoid replacing user data or migration history through indiscriminate text substitutions. Generated instructions must describe their actual standalone paths and commands.

Acceptance: extract both a default and a renamed project into temporary directories; verify completeness, naming consistency, rejected invalid names, destination safety, native/frontend checks, and runnable CI paths. A generator is a development tool, not a runtime dependency.

### PR 3 verification

Executed locally on Linux/amd64 on 2026-11-10. Seven generator tests passed, including customized/default/long project names, metadata and file completeness, reserved-name rejection, destination races, staging/publication failures, and symlink refusal. The original path and cleanup regression suites also passed (five tests each).

Generated `garden-notes` outside the source repository. Its locked frontend install, typecheck, lint, five component tests, and production build passed. Its Rust formatting, Clippy with warnings denied, 21 tests, and locked debug build passed. Its own seven process tests, two Chromium browser tests, incremental migration build regression, and both five-test runner regression suites passed. Compose configuration validation passed. No source-layout dependencies remained in generated files; the MIT notice was retained. Downloaded dependency caches were reused.

The final generation differs from that tested native/frontend project only in the neutral Docker OS-account label (`app`, still UID/GID 10001). No generated Docker image build or deployment/recovery suite, remote CI, native Windows/ARM validation, or platform deployment was executed. Those Docker checks remain PR 4; Windows-specific naming/modes are covered only by focused local checks and file rules.

## PR 4: Verify the extracted Docker-first starter end to end

Implemented on `test/standalone-docker-validation`: [standalone-docker-smoke.py](../../scripts/standalone-docker-smoke.py) creates a uniquely named fresh application outside the checkout, checks isolation/completeness, builds its image with `--no-cache`, and executes only the generated regression/Docker/recovery scripts. The Compose test now checks migration metadata and retains a modified greeting across graceful stop and forced container recreation. Scoped resource inventory and labelled helpers provide fallback cleanup after failures. See [the validation guide](STANDALONE-DOCKER-VALIDATION.md) for local/CI commands and limitations.

Depends on PR 3. From a clean renamed extraction, build the canonical production image without cached application layers. Validate Compose configuration and start it with isolated disposable volumes.

Acceptance: health and configurable port work; non-root/read-only operation and graceful SIGTERM pass; a changed SQLite value survives container removal/recreation; online backup and independent-volume restore retain expected application data; occupied/corrupt/unsafe recovery inputs fail. Exercise generated CI commands and verify cleanup. Document exact executed results and architecture limits. Do not substitute verification of the original repository for verification of the generated project.

### PR 4 verification

Executed on 2026-11-10 on Linux/amd64 with Docker 29.9.2, Compose 2.40.3, and Python 3.12.14. `python3 scripts/standalone-docker-smoke.py --proxy-ca "$CODEX_PROXY_CERT"` completed successfully for two fresh applications, `light-e2e-55568e22a2a5` and `light-e2e-993556d4048b`. The second run exercised the final command/child-process lifecycle implementation after interruption handling was strengthened. The optional CA was a BuildKit secret; TLS verification remained enabled.

Both runs built all application stages without cache from generated directories with no target, node_modules, dist, source-checkout paths, or database artifacts. Each passed generated Compose configuration validation, five cleanup regressions, five target-path regressions, five Docker/Compose tests, and six backup/recovery tests. The Compose test verified migration `1|1`, a changed greeting surviving a new container ID, and clean SIGTERM stops before and after recreation. HTTP checks exercised actual compiled frontend assets and database-backed API responses. Recovery covered live WAL, standalone export, integrity/FK/migration metadata, independent restored application reads, preserved source data, and refusal cases.

After both runs, a separate inventory confirmed zero matching containers, volumes, networks, and image tags. Temporary generated directories were removed; base images/build cache were retained without global pruning. Source regressions passed: nine orchestration/isolation/failure-cleanup tests, seven generator tests, and both five-test runner suites. `git diff --check` passed. Failure/timeout cleanup paths were simulated in unit tests, not by failing the daemon. A final stricter artifact precheck additionally rejects loose database/sidecar and local environment files; its generated-project checks passed in the focused suite.

No application source, runtime dependencies, Dockerfile, or deployment-platform settings changed. Rust/frontend unit/lint suites and browser rendering were not rerun in this step; the clean image builds compiled the generated Rust release binary and typechecked/built its frontend. No native Windows/ARM run, remote CI result, production capacity/TLS/host-loss recovery, or platform deployment is claimed. The new CI job is configured but was not observed running remotely.

No additional infrastructure, application authentication, or Advanced implementation belongs in these PRs. Platform deployment validation remains a later, separate task.


## Step 5: Automated vulnerability scanning

Implemented on `security/automated-vulnerability-scanning`. The [security guide](SECURITY-SCANNING.md) defines pinned tools, commands, trigger/enforcement policy, artifacts, SARIF opt-in, triage, and exception requirements. The existing Docker build/smoke job moved into the path-filtered Security workflow and shares its final image with Trivy; there is no second scan-only image build. Weekly/manual runs refresh findings. Generated apps receive independent security CI, installer, pins, wrapper, tests, and guidance. No runtime dependencies, application behavior, base images, or lockfiles were changed.

### Step 5 verification and findings

Executed locally on Linux/amd64 on 2026-11-10:

- Installed cargo-audit 0.23.0 with `--locked`, Trivy 0.76.2 with verified archive SHA-256, and validated workflows with actionlint 1.7.12 (verified release checksum). npm 11.9.0 was already installed. Both committed installer modes passed.
- `python3 scripts/test-security-scan.py -v`: 11 policy/error/sanitization tests passed; the same 11 tests passed in a generated app. Generator (7), standalone orchestration (9), target-path (5), and cleanup (5) regressions passed.
- Source and generated workflow validation passed actionlint, including optional SARIF permissions and standalone paths. No GitHub workflow run is claimed.
- Source `security-scan.py rust` completed with exit 1 (blocking vulnerabilities): RUSTSEC-2026-0459 in libsqlite3-sys 0.30.1, CVSS 6.8/medium, patched >=0.39.0; RUSTSEC-2023-0071 in rsa 0.9.10, CVSS 5.9/medium, patched >=0.10.0. Numeric severity was verified with cargo-audit's terminal report; JSON preserves CVSS vectors. There were no informational warnings. Cargo tree confirms SQLite is selected through sqlx-sqlite/sqlx; rsa is in the lockfile but absent from the current selected dependency tree. The conservative full-lockfile policy blocks both without asserting that rsa is exposed in this application. SQLite exposure depends on opening an attacker-influenced database/WAL pair; no exploit was reproduced. No suppressions or dependency changes were applied.
- Source `security-scan.py npm` completed with exit 0: no reported production or development vulnerabilities. No lockfile/install-script changes occurred.
- Built the canonical image with `docker build --no-cache --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -t kitternel-light:security templates/light`. Trivy scanned that final image successfully; policy exit 1: 430 package/CVE entries (188 distinct CVEs), comprising 3 CRITICAL, 95 HIGH, 148 MEDIUM, 160 LOW, 24 UNKNOWN. These are scanner findings, not demonstrated application exploits. Critical entries are CVE-2025-7458 in libsqlite3-0 and sqlite3, and CVE-2023-45853 in zlib1g; the latter is vendor-labelled will_not_fix and needs component/backport triage. No fixed version was reported for those critical entries. Image remediation/justified narrow exceptions require separate review; the security jobs are expected to remain red until findings are addressed.
- The default Trivy DB mirror returned Forbidden. Selecting the allowed official GHCR database with `TRIVY_DB_REPOSITORY=ghcr.io/aquasecurity/trivy-db:2` succeeded. The failed download was not treated as a clean scan. JSON and converted SARIF 2.1.0 were produced and checked; ImageConfig/environment/history are absent. Failure fixtures verify that raw error credentials are not published.
- Generated `secure-final` outside the repository. Its own Rust and npm audits completed with the same blocking/passing results, using only generated tools/configuration. Its workflows passed actionlint; no original source-layout references remain. No generated image was built again for this security-only change.
- The newly built source image passed five Docker/Compose tests and six SQLite recovery/cleanup tests. Disposable suite containers/volumes were removed. Shell syntax, diff whitespace, and absence of manifest/lockfile changes were checked.

Limitations: GitHub repository metadata/API returned Forbidden, so visibility, plan, Code Scanning support, SARIF upload, and remote CI remain unverified. Artifacts/summaries are the default; Code Scanning requires explicit maintainer opt-in. Trivy detected OS packages but no language inventory in the stripped runtime image: separate full Rust/npm audits remain essential. Rust/frontend unit/lint/browser suites were not rerun because application source and dependency locks are unchanged. No native Windows/ARM, production deployment, load/exploit test, or platform integration was performed. This work adds transparent detection, not a claim that discovered vulnerabilities are fixed or the project is vulnerability-free.
