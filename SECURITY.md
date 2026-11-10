# Security policy

Kitternel Light is a foundation preview. There is no production support commitment, security response SLA, or maintained release/backport matrix yet. Security fixes currently target the development main branch; deployments must track reviewed fixes and their own dependency/base-image updates.

## Reporting a vulnerability

Use the repository's [private vulnerability reporting page](https://github.com/NickyBass/kitternel/security/advisories/new) if GitHub enables it. Availability has not been verified; this document does not claim that private reporting is enabled. If it is unavailable, open a minimal issue requesting a private contact channel without including exploit details, credentials, private data, or reproduction against a real deployment. Do not post secrets or production database copies in issues, PRs, logs, or chat.

## Current security boundary

The included application exposes a public, read-only greeting and health endpoints. Authentication, authorization, sessions, CSRF defenses, tenant isolation, and private application data handling have not been implemented. A functioning container or green health check does not establish production readiness.

Implemented controls include bound SQL parameters, rejection of SQLite URI/in-memory configuration, safe public errors, sanitized diagnostic categories, same-origin requests without permissive CORS, production CSP/basic response headers, bounded HTTP header reads and active connections, and non-root Docker operation. The Compose example adds a read-only root filesystem, dropped capabilities, no-new-privileges, and loopback-only host publishing. These are individual controls, not a security certification or DoS-resistance claim.

Only trusted compiled assets belong in `FRONTEND_DIR`; it is not an upload directory or a sandbox for untrusted symlinks. Vite is a development server, not the production entrypoint. Use TLS at a trusted reverse proxy and do not expose unnecessary host ports. Forwarded headers currently grant no trust. Add secure cookies, CSRF protection, session rotation, and server-side authorization before implementing protected features.

## Dependencies and builds

Commit and review Cargo/npm lockfile changes, base image digests, toolchain pins, and CI action SHAs. Maintain TLS, package signatures, artifact checksums, and registry integrity checks. Run `npm audit`; run `cargo audit` when that tool is installed. Record the advisory source and actual exposure instead of claiming that one scan proves safety.

The development-only minimatch override is documented in the README. Review its compatibility and remove it once the parent tools support a fixed release. OS packages are resolved at image build time to obtain repository security updates, so byte-for-byte build reproducibility is not claimed. No automated update service or image publication is configured by this starter.

## Automated vulnerability policy

The [scanning guide](docs/development/SECURITY-SCANNING.md) documents pinned RustSec, npm, and final-image scanners, local commands, triggers, triage, report sanitization, and exception review. RustSec vulnerabilities in the full lockfile block conservatively; informational warnings are separate. Production npm HIGH/CRITICAL and image HIGH/CRITICAL block. Dev-only npm and lower/unknown findings remain visible. Scanner/tool/database failures are incomplete scans, never clean passes. No vulnerability suppressions or automatic upgrades are configured.

Reports are available as Actions artifacts by default. Code Scanning support has not been verified; SARIF upload requires explicit maintainer opt-in after checking repository visibility/plan/settings. Generated projects receive independent tooling and policy documentation. Dependency scanning complements application review and does not prove exploitability or production readiness.

## Operational responsibility

SQLite WAL requires a local compatible filesystem, one application instance per database, short transactions, and serialized deployments. Provision UID/GID 10001 storage permissions; do not use world-writable data directories. Configure disk capacity monitoring, retention, consistent backups, protected off-host copies, and periodic restore drills. Backup files may contain all application data and must receive the same confidentiality protections as the live database.

Use the [backup/restore procedure](docs/deployment/backup-restore.md). Restore into a fresh volume, verify integrity and application data, and stop validation containers before cutover. Do not overwrite a live database or automatically roll back to an image with incompatible migrations. Platform archive/snapshot features are not automatically consistent SQLite backups.

Dokploy/Coolify guides document the expected configuration, but their actual deployments remain unverified until tested on identified instances/versions. The [verification record](docs/development/verification.md) separates local tests from platform/remote CI evidence.
