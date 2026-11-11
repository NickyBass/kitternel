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

### Security remediation follow-up

Updated SQLx/SQLite and the pinned Debian runtime after reviewing CI artifacts. The [remediation record](SECURITY-REMEDIATION.md) documents verification, eliminated critical/RSA findings, size trade-off, and remaining vendor/upstream blockers. Checks remain blocking; no policy relaxations or broad suppressions were added. A disposable-volume old/new-image upgrade drill is included and copied to generated apps.

### Validated blocker resolution

The [current remediation record](SECURITY-REMEDIATION.md) supersedes the earlier blocking scan snapshots: local RustSec/npm/image policies now all pass without exceptions. The official temporary SQLx Git pin permits patched SQLite 0.39.1; the pinned Ubuntu LTS runtime has no reported HIGH/CRITICAL findings. Forty-two MEDIUM and four LOW image entries remain visible, including two CVEs whose vendor severity is lower on Ubuntu. Artifact/Code Scanning actions now declare Node 24 at immutable SHAs. Compatibility, migration/volume upgrade, recovery, resource trade-offs, infrastructure failures and unverified areas are documented. Remote CI still needs confirmation.

## Step 6B: Explicit GNU recovery utilities

Branch: `security/gnu-recovery-utilities`. Backup/restore maintenance helpers select
six verified GNU-prefixed executables with absolute paths and fail before touching
storage if a required utility is missing, fails identity verification, or is not GNU.
Default dirname/realpath/mktemp/sync/ln were uutils; rm already used GNU and is now
also protected against PATH shadowing. No package, base image, dependency lock,
migration, application behavior or scanner enforcement change was made.

Local verification passed: generator 7, security policy 11, cleanup 5, target paths 5,
standalone orchestration 9, canonical Docker/Compose 5, recovery/cleanup 8, plus a
final focused failure-propagation test. The independent generated application passed
its clean Docker build, Compose/runtime/recovery suites and scoped resource cleanup.
Both candidate images report 42 MEDIUM and 4 LOW occurrences, unchanged from the
46-occurrence/36-CVE baseline; all 20 uutils entries remain visible. RustSec and npm
pass with zero findings. Initial disk-exhaustion failures, cache recovery, exact
commands, implementation details and remaining verification limits are recorded in
[SECURITY-REMEDIATION.md](SECURITY-REMEDIATION.md#step-6b-explicit-gnu-recovery-utilities).

Future work: investigate the supported Ubuntu provider transition separately;
do not force removal of protected packages. This step reduces operational exposure
and does not mark the uutils vulnerability group resolved. Remote CI and platform
integrations were not verified.

## Step 7B.2: Independent maintenance guide

Branch: `docs/generated-maintenance-guide`. Generated projects receive a personalized
`MAINTENANCE.md`, linked from README, CONTRIBUTING and AGENTS. It covers ownership,
pin locations, Rust/MSRV/Cargo, the temporary SQLx/SQLite binding constraint,
Node/npm/frontend overrides, Docker/package maintenance, explicit GNU recovery
commands, the stopped protected-provider replacement, and independent security upkeep.
Release/rollback is an overview only; the detailed runbook remains separate work.

Generator regressions (eight fast tests plus one optional five-name rustfmt test),
Python/Git-only generation, nine standalone orchestration tests and eleven copied
security policy tests passed. A fresh `maintenance-notes` application outside this
checkout passed Compose configuration and its own RustSec/npm scans (zero findings);
Cargo tree confirmed libsqlite3-sys 0.39.1. Local links, script paths, identities and
scanner-version documentation are regression checked. No dependency update,
Docker rebuild, live image scan, runtime/recovery drill or remote CI is claimed.

Additional diagnostic: `cargo fmt --all -- --check` fails for the longer generated
name `maintenance-notes` because its default SQLite-path line needs wrapping in
`backend/src/config.rs`. The existing five-name Step 7B.1 matrix still passes; its
import-group fix did not cover this length-dependent case. No application source
was changed here; that defect needs a separate focused correction. Documentation
and compiler/security procedures do not imply that this formatting failure passed.

## Step 7B.3: Safe application releases and recovery

Branch: `docs/generated-release-recovery`. The generated maintenance guide now
contains the manual "Releases, Updates and Recovery" runbook. README links to it
instead of duplicating backup commands. Tests check local section anchors, helper
paths, image-only Compose selection and the absence of destructive volume-removal
commands in executable examples. No runtime/configuration/dependency policy changed.

The runbook records clean source revisions, retains previous local image IDs/tags,
validates a candidate by image ID, selects it through an explicit operator-owned
Compose override, keeps project/volume identity stable, freezes writers, proves a
snapshot restore, and replaces containers serially. It distinguishes image rollback
from snapshot recovery and potential loss of subsequent writes. Additive SQL does
not prove old-binary compatibility: SQLx may reject migration versions absent from
that binary. A production volume cutover remains an explicit reviewed operator
mapping, not an automatic switch.

### Executed verification (2026-11-11, Linux/amd64)

- `python3 scripts/test-create-light.py --rustfmt -v`: nine tests passed, including
  the existing five-name formatting matrix. Python/Git-only mode passed with the
  optional formatting test skipped. Nine standalone orchestration tests passed.
  Python syntax and `git diff --check` passed.
- Generated `rel-231c5a` outside the checkout; baseline command:
  `docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -t rel-231c5a:local .`
  from that application's root. Build succeeded; caching was retained, not disabled.
- A disposable validation harness executed the generated runbook's shell blocks
  for sections 1–6, adding the documented optional public CA secret to candidate
  build and using a unique HOST_PORT. Both baseline/candidate used the generated
  Dockerfile/context; the candidate differed by revision label only, not new schema
  or application features. A temporary application Git repository supplied its own
  committed revision. No original application binaries/assets/data were copied.
- Candidate ID passed `scripts/docker-smoke.py --image "$CANDIDATE_ID" -v` (5 tests),
  `scripts/sqlite-backup-smoke.py --image "$CANDIDATE_ID" -v` (8 tests), and its own
  image scan. Copied RustSec/npm wrappers passed independently with zero findings.
  Trivy: 46 occurrences/36 CVEs, 42 MEDIUM, 4 LOW, no HIGH/CRITICAL/UNKNOWN.
- Actual Compose image-ID deployment, different container identity, unchanged data
  volume, health/data/migration checks, schema-compatible image rollback, finalized
  snapshot export, independent restore and restored application reads all passed.
  Original data retained a deliberately later value; restored data retained the
  earlier snapshot value. Cleanup and a separate inventory found no owned containers,
  volumes, networks or image tags left behind.
- Clean/dirty Git preflight and private record-directory permissions were checked.
  The manual external-volume override syntax was checked with Compose config only;
  no production data-volume cutover is claimed. Docker 29.9.2/Compose 2.40.3 were used.

The first rehearsal stopped at an additional harness inspection: after the restored
app had enabled WAL and stopped, a fully read-only volume mount could not create
required SQLite shared-memory files (SQLITE_CANTOPEN). Backup/restore and the restored
app had already worked; deployment/rollback were not reached in that attempt. Scoped
cleanup passed. The harness's later read-only SQL checks now use a normal writable
data-volume mount while keeping the root filesystem read-only. A fresh generated
fixture and the complete rehearsal then passed. The guide explains this distinction.

The known `maintenance-notes` wrapping defect was reproduced separately: rustfmt
exits 1 in config.rs. It remains an outstanding pre-alpha issue, not a regression
from this documentation change. The short rehearsal name passes formatting. No
format gate was weakened. Native/frontend unit or browser suites were not rerun;
Docker builds compiled Rust and typechecked/built the frontend. No incompatible or
breaking migration rollback, real production cutover, off-host recovery, remote CI,
Windows/ARM or zero-loss disaster-recovery guarantee is claimed. No Step 7B.4 work.

## Step 7B.4: Offline toolchain and dependency pin consistency

Branch: `test/toolchain-pin-consistency`. A Python 3.11+ standard-library checker
reads the existing source-template or standalone declarations without network,
external tool execution or file rewriting. The generator copies it and its focused
regressions; the existing application CI runs them from the project root before
Node installation/builds. No new version manifest or update framework is introduced.

Validated relationships: selected Rust/Docker/explicit Cargo/security-install
compiler; MSRV no greater than selected Rust; Node Docker/CI readers and supported
engine ranges; npm metadata/security CI; local package identities; scanner installer
manifest selections, locked cargo-audit install, checksum format/verification wiring;
current scan-guide and explicit setup-version claims. Git SQLx revisions are checked
against lock sources when used; a future published dependency is allowed. SQLite
binding versions and optional minimatch overrides are inventory, not permanent pins.
The checker does not resolve Cargo/npm constraints, authenticate checksums/digests,
prove MSRV compatibility or perform security scans. Known-layout extraction and
common stable Node range support are documented; unsupported syntax fails explicitly.

Executed verification on 2026-11-11:

- Source checker passed. Twenty-one positive/negative tests passed, using only
  disposable declaration copies. Tests cover valid ranges, version drift, checksums,
  installer guards, legitimate updates, document claims, CLI exit diagnostics and
  file-content/mtime invariance. Empty-PATH execution and blocked socket/subprocess
  calls demonstrate the absence of external tool/network requirements.
- Generator suite passed ten tests with its optional five-name rustfmt integration;
  Python/Git-only mode passed nine tests with that integration skipped. Existing
  standalone orchestration (9) and security-policy regressions (11) passed.
- A fresh `maintenance-notes` project outside the checkout ran its own checker and
  all 21 copied regressions with PATH empty, plus 11 copied security-policy tests.
  Source and generated workflows passed actionlint 1.7.12. Python syntax and diff
  whitespace checks passed; no installed application/tool versions were changed.
- Known unrelated `maintenance-notes` rustfmt wrapping failure was reproduced with
  exit 1 in config.rs while its pin checker passed. It remains an outstanding
  pre-alpha defect; formatting gates were not weakened.

No dependency resolution/update, scanner/archive download, Docker build/runtime,
frontend build/unit/browser suite, native Rust compilation/test suite, or remote CI
execution is claimed for this development-validation-only change. Runtime source,
Docker images/digests, dependency locks, migrations, tool pins and vulnerability
policies remain unchanged. Step 7B.5 is separate work.

## Step 7B.5: Standalone developer workflow and onboarding

Branch: `docs/generated-developer-workflow`. Generated README now gives concise
Docker/native quick starts and a linked module map. CONTRIBUTING covers independent
Git ownership, working directories/configuration, opt-in backend/frontend edits,
immutable migration development, checks and safe troubleshooting. AGENTS adds the
current module map and validation entry points while preserving the owner's freedom
to evolve the application. Detailed updates, releases and recovery stay in the
existing MAINTENANCE guide. No application source, migrations, dependencies, tool
pins, generator behavior or security policy changed.

Generator regressions validate generated relative links and cross-document heading
anchors, referenced script/source paths, npm script names, identity substitution,
absence of placeholders and inherited Git metadata. Existing safety tests remain.

Executed verification on 2026-11-11:

- Generator suite: 11 tests passed including optional five-name rustfmt integration;
  Python/Git-only mode: 10 passed, one optional integration skipped. Pin checker and
  21 regressions passed, as did 11 security-policy, 9 standalone-orchestration and
  5 copied smoke-path regressions. Python syntax, workflow actionlint 1.7.12 and
  diff whitespace checks passed.
- A fresh `dev-notes` application outside the checkout had no inherited Git history
  or remotes. Git initialization, staged review and an initial commit succeeded;
  synthetic local env/database/build/report files were ignored and .env.example
  remained trackable. Its copied pin checker and all 21 copied regressions passed.
- In that independent application, locked Cargo check/Clippy/tests/build and format
  checks passed (21 Rust tests). Locked npm install, typecheck/lint/tests/build
  passed (5 frontend tests), using the selected tools and isolated build/cache paths.
- Documented native startup created the default database directory, served built
  assets and API, and passed readiness. Vite served its development entry and
  proxied API/readiness correctly. The documented read-only Python database query
  returned integrity `ok` and the applied migration metadata. Owned processes were
  stopped with SIGTERM; Rust exited cleanly. Seven native smoke tests passed.
- Only the disposable copy received the illustrative backend/frontend edits and
  corresponding assertions. Format plus all 21 Rust tests, and frontend typecheck,
  lint, 5 tests and production build passed afterwards. No illustrative SQL migration
  was applied; schema-change/upgrade behavior was not rehearsed in this task.
- Generated Compose configuration passed. An initial invalid synthetic .env fixture
  was corrected before retrying; Compose reads that file even though Rust does not
  load it automatically. Temporary Git/source/build/database resources were scoped
  to this audit's disposable application; no temporary repository was pushed.

Known `maintenance-notes` config.rs wrapping failure was reproduced with rustfmt
exit 1 and deliberately left unchanged; no formatting gate was weakened. Docker
images/runtime/recovery, browser automation, live security scans and remote CI were
not run for this documentation change. Compose syntax and native startup do not
prove container runtime or deployment behavior. No platform integrations or Step 8
work are included.

### Step 7B.5 follow-up: APT and browser download reliability

After the original documentation validation, the maintainer supplied three failed
GitHub job archives. The light job failed resolving azure.archive.ubuntu.com during
Playwright dependency installation; both standalone jobs failed resolving Ubuntu
archive/security hosts. APT then continued with missing indexes and reported that
packages were unavailable. These logs do not demonstrate an application-code defect
or identify the underlying DNS infrastructure fault.

The authorized follow-up keeps the same pinned images, packages and application
code. Docker APT commands select three download retries; update uses
`APT::Update::Error-Mode=any` so incomplete indexes stop the build. The disposable
CI runner uses the same APT settings. Browser installation has at most three
attempts with ten-second delays, still bounded by the existing job deadline.
Persistent failures remain failures; real browser tests are not skipped or retried
as a substitute for installation. No resolver/mirror/signature/TLS changes are made.

Verification on 2026-11-11:

- Generator suite: 13 tests passed including pinned rustfmt integration. New tests
  execute the generated workflow's Bash block with controlled commands: first-try
  success, recovery on attempt three, exhausted retries, and APT-config failure.
  They also execute the Docker RUN chain with controlled package-command failures
  to verify that subsequent package/user operations stop.
- In the actual pinned Ubuntu image, a disposable localhost repository probe
  returned exit 0 for ordinary APT update and exit 100 with strict error mode.
  It used isolated temporary source/list paths and installed nothing.
- `python3 scripts/standalone-docker-smoke.py --proxy-ca "$CODEX_PROXY_CERT"`
  passed: fresh external generated application, uncached canonical image build,
  Compose validation, 5 cleanup and 5 binary-path tests, 5 Docker runtime tests,
  and 8 recovery tests. These include health/API/assets, non-root/read-only runtime,
  graceful shutdown, recreation persistence, backup/restore, concurrent publication
  and unsafe-input refusal. Scoped resource inventory and cleanup passed.
- Offline pin checker and 21 regressions, 11 security-policy, 9 orchestration and
  5 source cleanup regressions passed. Source and fresh generated workflows passed
  actionlint 1.7.12; Python syntax and diff whitespace checks passed.

This verifies local resilience/error handling and Docker behavior, not repair of a
persistent GitHub DNS outage. Real Playwright installation/automation on a hosted
runner and new remote CI outcomes remain unverified; no live vulnerability scans
were run. Application Rust/frontend unit suites were not rerun for this follow-up;
the clean Docker build compiled Rust and built the frontend. The separately known
personalized config.rs formatting defect remains unchanged.

## Step 7C: Generated Rust formatting stability

Branch: `fix/generated-config-formatting`, based on main including merged PR #12.
The known maintenance-notes failure was reproduced before editing: its personalized
SQLite default made the lookup expression 103 columns, requiring rustfmt wrapping.
The production default now lives in a private string constant, so the expression's
layout does not depend on the project name. The SQLite path, override precedence,
validation and allocation behavior are preserved; the generator is unchanged.

The expanded matrix also exposed short-name wrapping changes for `a` in the
default-path assertion and the HTTP test's expected greeting tuple. Test-local
expected values now keep those expressions independent of substituted literal
length. Expected values and assertions remain; no API or migration change is made.

Executed verification on 2026-11-11:

- Fast generator suite: 13 passed with one optional integration skipped. A new CLI
  regression generates successfully with only Git on PATH and Python invoked by
  its absolute path, without Cargo/rustfmt/Node. The opt-in suite passed all 14 tests.
- Pinned rustfmt checked 42 generated applications: a, a-app, dev-notes,
  audit-notes-7a, maintenance-notes, maple-notes, sunrise-notes, zebra-notes,
  one-two-three-four, a 32-character name, and x repeated at every length 1..32.
  The existing 33-character rejection remains. Every check preserved all generated
  Rust file bytes and mtimes. Existing CI runs this integration without a new job.
- Source backend format, locked check, all-target/all-feature Clippy with warnings
  denied, and all 21 tests passed. Fresh external maintenance-notes passed format,
  all 21 backend tests and a locked build. Generated `a` and the 32-character name
  each passed all 6 configuration tests, including literal default and explicit
  absolute/relative/space/Unicode path overrides and invalid-input rejection.
- Two real native starts of maintenance-notes verified the default path and an
  environment-selected path containing spaces. Each database had migration version
  1 and passed integrity/readiness/API checks. The override used an independent
  database and preserved known data in the original. Both owned processes stopped
  cleanly. This probe used disposable assets/data, not a frontend production build.
- Source and standalone offline pin checks, 21 pin regressions, 9 standalone
  orchestration regressions, Python syntax and diff whitespace checks passed.
  Generated Cargo/npm locks still match only the existing identity customization;
  no dependency, lockfile, toolchain, migration, Docker or scanner changes occurred.

Generated troubleshooting/maintenance instructions no longer advertise this defect
as outstanding. Earlier entries retain historical failures. Docker, frontend and
live scanner suites were not rerun because this correction changes formatting
layout and configuration test coverage only. New remote CI outcomes are separate
from the locally executed checks; no Step 8 or merge is included.
