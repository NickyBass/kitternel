# First security remediation

Recorded on 2026-11-10 on Linux/amd64 after review of the Step 5 CI artifacts. This is a partial remediation, not a clean security result.

## Changes and reasons

- SQLx 0.8.6 -> 0.9.0 removes RSA and its unused cryptographic dependency chain from the lockfile. Rust 1.99.1 satisfies SQLx's Rust 1.94 requirement. The application API and migration SQL are unchanged.
- Resolve libsqlite3-sys to 0.37.0, the newest version allowed by SQLx 0.9's `>=0.30.1, <0.38.0` constraint. It bundles SQLite 3.51.3. Explicit `sqlite-bundled` and `sqlite-unlock-notify` features preserve the required SQLite backend without enabling 0.9's broad `sqlite` umbrella (which adds extension loading/deserialization).
- Runtime Debian 12 -> Debian 13, pinned to the verified trixie-slim multi-platform digest. Apply available APT upgrades before installing runtime packages so fixed base packages such as zlib receive current stable security updates. Node/Rust builders remain pinned and unchanged. Non-root UID/GID, health check, read-only compatibility, storage paths, and recovery helpers are preserved.
- Add a repeatable disposable-volume upgrade drill for dependency/base-image changes without new migrations. Generated apps also receive it.

## Scanner results

| Result | Before | After |
| --- | --- | --- |
| RustSec vulnerabilities | 2 | 1 |
| Runtime CRITICAL entries | 3 | 0 |
| Runtime HIGH entries | 95 | 93 |
| Runtime MEDIUM entries | 148 | 117 |
| Runtime LOW entries | 160 | 150 |
| Runtime UNKNOWN entries | 24 | 24 |

The updated image has 384 package/CVE entries. Trivy 0.76.2 scanned the freshly rebuilt final image with the official GHCR database; no ignore/config, severity threshold, or exception policy was changed. RustSec and image checks still return policy exit 1. These are reported package advisories, not reproduced application exploits. No remaining HIGH entry has a reported fixed version in the selected vendor database.

RUSTSEC-2023-0071 is removed with RSA. RUSTSEC-2026-0459 remains against libsqlite3-sys 0.37.0; its patched range starts at 0.39.0 (SQLite 3.54), outside the current stable SQLx constraint. The advisory requires opening attacker-influenced database/WAL files. Do not bypass the constraint, substitute an unverified fork, or ignore the finding globally. A compatible upstream release or separately designed/tested linkage to patched SQLite is needed to close it. Runtime HIGH findings still require vendor/component triage, fixes, or narrowly justified time-limited exceptions with evidence; no such exceptions were invented here. Alpha/release security gates remain blocked.

## Executed verification

- Rust formatting, check, Clippy with warnings denied, 21 tests, and locked debug build passed with the updated lockfile/features.
- Seven native process tests, two Chromium browser tests, and the incremental migration build regression passed.
- Canonical `docker build --no-cache --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -t kitternel-light:remediation templates/light` passed with TLS verification enabled. Five Docker/Compose tests and six SQLite recovery/cleanup tests passed.
- Built an old-release fixture with the existing Step 5 image (SQLx 0.8 / Debian 12), wrote a non-seed greeting, stopped/removed it, and opened the same disposable volume with the new image. The greeting and existing migration versions/success/checksums were retained; both containers stopped cleanly.
- Generator regressions passed; generated Cargo package metadata and Docker configuration incorporate the updated template. Security policy regressions passed; manifest/package identities and source layout remain consistent.
- Image size increased from 96,072,089 to 101,469,077 bytes uncompressed (about 5.4 MB). No throughput or memory benchmark was performed.

Repeat the upgrade drill using trusted locally built releases with the same database path and unchanged migration files:

```sh
python3 scripts/sqlite-upgrade-smoke.py --previous-image kitternel-light:security --image kitternel-light:remediation
```

The script inspects both local images first, owns only a fresh randomly named test volume, verifies data and exact existing migration metadata, and cleans up its containers/volume. It never opens deployment storage. It is not a migration rollback tool and is not automatically run in CI because no previous-release image is published by this repository.

Source dependency changes are intentional and limited to the SQLx upgrade and compatible SQLite binding update; frontend manifests/lockfile and application/migration source are unchanged. No platform deployment or integration, remote CI success, native Windows/ARM check, new full extracted-image build, or resolved-all-vulnerabilities claim is made. The updated commit is intended to improve the open Step 5 PR while preserving its honest blocking checks.
