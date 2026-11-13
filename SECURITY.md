# Security policy

Kitternel Light is a foundation preview. There is no production support commitment, security response SLA, or maintained release/backport matrix yet. Security fixes currently target the development main branch; deployments must track reviewed fixes and their own dependency/base-image updates.

## Reporting a vulnerability

Use the repository's [private vulnerability reporting page](https://github.com/NickyBass/kitternel/security/advisories/new) if GitHub enables it. Availability has not been verified; this document does not claim that private reporting is enabled. If it is unavailable, open a minimal issue requesting a private contact channel without including exploit details, credentials, private data, or reproduction against a real deployment. Do not post secrets or production database copies in issues, PRs, logs, or chat.

## Supported versions and generated applications

`v0.1.0-alpha.1` is being prepared; it is not released by this documentation change.
Until publication, security fixes target reviewed development `main`. Once the
first alpha is published, it is the only alpha line targeted for security review;
there is no stable/backport matrix or response SLA. Older snapshots may require
moving to reviewed current source. Report relevant issues even if applicability
is uncertain; do not assume a report guarantees a fix or timetable.

Starter reports concern the generator, templates and shipped tooling. Generated
applications are independently maintained: their owners must configure a private
reporting channel, support policy, updates and deployment controls. Kitternel has
no automatic connection to or patch service for generated applications.

For responsible disclosure, share only what maintainers need through a verified
private channel, allow assessment/coordination before public exploit details, and
do not test against another person's deployment without permission. Do not send
credentials or production database copies. If no private channel is available,
request one with a minimal nonsensitive issue and wait before sending details.

Maintainer action before publication: verify GitHub private vulnerability reporting
in repository settings and test the report flow with an account representing a
reporter, or document another verified private channel. A REST availability probe
on 2026-11-13 returned 404; that does not distinguish disabled, unavailable or
insufficiently authorized access. No setting was enabled by this preparation.
See the [publication checklist](docs/releases/PUBLICATION-CHECKLIST.md).

## Current security boundary

The included application exposes a public, read-only greeting and health endpoints. Authentication, authorization, sessions, CSRF defenses, tenant isolation, and private application data handling have not been implemented. A functioning container or green health check does not establish production readiness.

Implemented controls include bound SQL parameters, rejection of SQLite URI/in-memory configuration, safe public errors, sanitized diagnostic categories, same-origin requests without permissive CORS, production CSP/basic response headers, bounded HTTP header reads and active connections, and non-root Docker operation. The Compose example adds a read-only root filesystem, dropped capabilities, no-new-privileges, and loopback-only host publishing. These are individual controls, not a security certification or DoS-resistance claim.

Only trusted compiled assets belong in `FRONTEND_DIR`; it is not an upload directory or a sandbox for untrusted symlinks. Vite is a development server, not the production entrypoint. Use TLS at a trusted reverse proxy and do not expose unnecessary host ports. Forwarded headers currently grant no trust. Add secure cookies, CSRF protection, session rotation, and server-side authorization before implementing protected features.

## Dependencies and builds

Commit and review Cargo/npm lockfile changes, base image digests, toolchain pins, and CI action SHAs. Maintain TLS, package signatures, artifact checksums, and registry integrity checks. Run `npm audit`; run `cargo audit` when that tool is installed. Record the advisory source and actual exposure instead of claiming that one scan proves safety.

The development-only minimatch override is documented in the [technical reference](docs/development/LIGHT-REFERENCE.md) and [alpha risk register](docs/releases/ALPHA-LIMITATIONS.md). Review its compatibility and remove it once the parent tools support a fixed release. OS packages are resolved at image build time to obtain repository security updates, so byte-for-byte build reproducibility is not claimed. No automated update service or image publication is configured by this starter.

## Automated vulnerability policy

The [scanning guide](docs/development/SECURITY-SCANNING.md) documents pinned RustSec, npm, and final-image scanners, local commands, triggers, triage, report sanitization, and exception review. RustSec vulnerabilities in the full lockfile block conservatively; informational warnings are separate. Production npm HIGH/CRITICAL and image HIGH/CRITICAL block. Dev-only npm and lower/unknown findings remain visible. Scanner/tool/database failures are incomplete scans, never clean passes. No vulnerability suppressions or automatic upgrades are configured.

Reports are available as Actions artifacts by default. Code Scanning support has not been verified; SARIF upload requires explicit maintainer opt-in after checking repository visibility/plan/settings. Generated projects receive independent tooling and policy documentation. Dependency scanning complements application review and does not prove exploitability or production readiness.

## Operational responsibility

SQLite WAL requires a local compatible filesystem, one application instance per database, short transactions, and serialized deployments. Provision UID/GID 10001 storage permissions; do not use world-writable data directories. Configure disk capacity monitoring, retention, consistent backups, protected off-host copies, and periodic restore drills. Backup files may contain all application data and must receive the same confidentiality protections as the live database.

Use the [backup/restore procedure](docs/deployment/backup-restore.md). Restore into a fresh volume, verify integrity and application data, and stop validation containers before cutover. Do not overwrite a live database or automatically roll back to an image with incompatible migrations. Platform archive/snapshot features are not automatically consistent SQLite backups.

Dokploy/Coolify guides document the expected configuration, but their actual deployments remain unverified until tested on identified instances/versions. The [verification record](docs/development/verification.md) separates local tests from platform/remote CI evidence.

See the [current remediation record](docs/development/SECURITY-REMEDIATION.md) for locally validated results, the temporary official upstream SQLx pin, runtime selection, visible residual findings, and limits. Remote CI results require separate confirmation.

See the [alpha limitations](docs/releases/ALPHA-LIMITATIONS.md) for evidence dates,
platform scope and remaining dependency/runtime review items. Historical passing
counts are not current guarantees; refresh scans against the actual release image.
