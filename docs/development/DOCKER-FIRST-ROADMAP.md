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
