# Alpha limitations and risk register

Prepared 2026-11-13. Applies to the Light foundation at source baseline
`0214e52317d74fac3c7d8f2d120f6711da51377d` (PR #13), plus documentation-only
release preparation. This is a disclosure record, not a security certification.

## Evidence provenance

The complete Step 8A Markdown report and evidence ZIP from 2026-11-11 are **not
available in the replacement workspace**. The prior audit conclusion visible in
the task conversation was CONDITIONAL GO with no confirmed P0/P1 blockers. That
summary is not a substitute for the original report or scanner artifacts.
The prior conversation reported passing generated backend/frontend/browser,
Docker and recovery checks. They are historical results, not newly executed tests
in this preparation. Recover the original attachments for the release archive.

The repository's [remediation record](../development/SECURITY-REMEDIATION.md),
[Docker-first roadmap](../development/DOCKER-FIRST-ROADMAP.md) and
[verification record](../development/verification.md) contain separate dated
implementation evidence. Their snapshots have different scopes and must not be
combined into an undated claim that every current check passed.

## Dependency and runtime decisions

| Item | Current evidence and impact | Required follow-up |
| --- | --- | --- |
| SQLx upstream Git revision | `backend/Cargo.toml` selects official upstream commit `10462fa4414c6c7f1ed1d39bb31678e3b726878c`; lockfile resolves libsqlite3-sys 0.39.1. The remediation record explains the patched SQLite binding and upstream PR #4502. This includes commits beyond published SQLx 0.9.0; immutable does not mean risk-free. | Maintainers track a compatible published release; generated owners review and validate replacement. No automatic upgrade. |
| minimatch override | `frontend/package.json` temporarily overrides development tooling to 11.0.5; lockfile and Node 24 compatibility remain deliberate choices. | Review parent tool support and remove only with validation. |
| npm audit | The 2026-11-11 audit summary reported zero findings. The on-disk remediation record separately reports zero findings on 2026-11-10. Neither establishes current advisory status. | Run both full and production scopes using the copied security wrapper before release. |
| Runtime package findings | Step 8A's 2026-11-11 final-image summary reported **41 MEDIUM, 4 LOW, 1 UNKNOWN**, no HIGH/CRITICAL. The 2026-11-10 remediation snapshot separately reported 42 MEDIUM / 4 LOW. Different scan dates/classifications must remain visible. Full Step 8A artifacts are missing here. | Refresh the actual built image scan and review all findings; preserve artifacts and image identity. |
| uutils provider | The documented runtime retains protected rust-coreutils. Fixed-path GNU recovery helpers reduce use of affected implementations; they do not eliminate installed-package findings. | Follow vendor updates; do not force protected-package removal or replace providers in this documentation task. |
| Pebble executable | The prior audit conversation identified an UNKNOWN finding in Go stdlib in `/usr/bin/pebble`, with uncertain application relevance. Its full historical scanner artifact is unavailable here. A fresh Step 8B generated image again contains `/usr/bin/pebble`; `dpkg-query -S /usr/bin/pebble` found no owning package. No new vulnerability scan or exploit reproduction was performed; do not describe it as fixed, removed, harmless or vendor-patched. The configured application entrypoint is Rust, not Pebble. | Inventory the exact release image, identify provenance/use and inspect the new finding. If still present, retain explicit triage; no removal/image change in this task. |
| Reproducibility | Cargo/npm graphs and base images are pinned, while runtime packages receive repository updates at build time. | Retain exact tested image identity and artifacts; rebuilding old source need not reproduce identical bytes. |

Detailed scanner policy: full-lockfile RustSec vulnerabilities block; production
npm HIGH/CRITICAL and image HIGH/CRITICAL block. Lower/UNKNOWN findings remain
visible for triage. A nonblocking scanner finding is not proof of non-exploitability;
scanner/database/tool failure is incomplete evidence. No blanket exception is
introduced here. See [scanning policy](../development/SECURITY-SCANNING.md).

Risk ownership: repository maintainers own starter decisions before release;
generated-application owners own their graphs, reports and deployment afterward.
Use the [publication checklist](PUBLICATION-CHECKLIST.md) to record a concrete
owner, review date and evidence link for these items at each candidate review.

## Platform support

| Environment | Evidence boundary |
| --- | --- |
| Linux/amd64 with Docker/Compose, single instance, local storage | Validated in the dated repository records and prior audit summary. Step 8B quick-start results are recorded separately in the preparation validation record. |
| Native Unix development with selected Rust/Node/npm versions | Dated checks exist; Rust 1.99.1 is selected, MSRV declaration 1.99 is not separately certified across all patch versions/targets. |
| Windows/macOS Docker, ARM, SELinux host behavior | Expected to need environment-specific setup; not validated as supported runtime platforms. Cross-platform tools alone do not establish compatibility. |
| Dokploy/Coolify | Guides exist; actual deployments remain unverified. |
| Multiple replicas, networked SQLite filesystem, PostgreSQL/Kubernetes | Outside the current Light deployment model; absence is not an alpha defect. |

## Application and operational limits

- Public, read-only greeting and health endpoints only. Authentication,
  authorization, tenant isolation, sessions and CSRF defenses are absent.
- Trusted compiled assets only in FRONTEND_DIR; not an upload/symlink sandbox.
  Vite is a development server and binds all interfaces by default.
- Provision UID/GID 10001 and restrictive storage access. Native parent directory
  permissions inherit the environment; no universal permission guarantee is made.
- One SQLite instance on a local WAL-compatible filesystem. Preserve the entire
  data directory and Compose project/volume identity; serialize replacements.
- Backup helpers need the matching image's GNU-prefixed utilities, SQLite CLI and
  local hard-link support. Restore into fresh independent storage first; never
  overwrite a live database. A local second volume does not protect against host
  loss. Owners provide off-host copies, encryption, retention and periodic drills.
- TLS termination, capacity/disk monitoring, reverse-proxy configuration, DoS
  protection and application-specific recovery objectives remain operator work.
- Generated GitHub security push coverage names `main`; owners using another
  primary branch must adapt it. Branch rules, artifact availability and private
  reporting are repository settings, not capabilities a generated file enables.
- No support SLA, stable alpha compatibility, automatic upstream sync, centralized
  patching, production readiness or universal lossless rollback is promised.
