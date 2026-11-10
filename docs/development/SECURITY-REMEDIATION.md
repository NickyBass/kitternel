# Security remediation

## Current validated resolution

Recorded on 2026-11-10. The earlier blocked snapshots below are historical. Current local RustSec, npm, and final-image checks all complete with exit 0, using unchanged enforcement thresholds and no advisory exceptions.

- Pin SQLx to the official upstream security-support commit `10462fa4414c6c7f1ed1d39bb31678e3b726878c` (upstream PR #4502). That commit permits libsqlite3-sys 0.39.x; the lockfile now resolves stable libsqlite3-sys 0.39.1 with patched bundled SQLite. This is an explicit temporary upstream Git pin, not a fork or a moving branch. It includes 49 upstream commits after the 0.9.0 tag, so compatibility validation matters. Replace it with a crates.io release containing the fix when available; do not automatically follow upstream main.
- Use the official Ubuntu 26.04 LTS runtime, pinned to digest `sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c`, retaining glibc, the same three requested runtime packages, non-root identity, health command, storage paths, and read-only operation. Debian 13 still had reported HIGH findings without fixes; the Ubuntu vendor/package set has no reported HIGH/CRITICAL findings. An Alpine alternative could not be validated because its package repository was blocked by this environment, and was not adopted.
- Update upload-artifact to v7.0.2, download-artifact to v8.0.2, and upload-sarif to the verified v4 commit, all pinned to immutable SHAs. Their official action metadata declares Node 24. Relevant input names were verified and source/generated workflows passed actionlint. No remote execution of these actions is claimed.

Final scanner results: RustSec has zero vulnerabilities and no informational warnings; npm reports zero production/development vulnerabilities; Trivy reports zero HIGH/CRITICAL/UNKNOWN, 42 MEDIUM and 4 LOW entries. All findings remain in artifacts. Two previously HIGH CVE identifiers, CVE-2026-78408 and CVE-2026-9538, remain reported as MEDIUM by Ubuntu; they were not silently discarded or demonstrated fixed. Severity counts across distributions reflect both changed packages and vendor assessments. Passing policy is not a vulnerability-free or exploitability claim.

Executed checks passed: pinned-upstream Rust formatting, Clippy, 21 tests and locked build; seven native process tests, two Chromium browser tests, incremental migration build regression; five Docker/Compose tests; six recovery/cleanup tests; old-image-to-new-image data/checksum preservation drill; seven generator and eleven security-policy tests. The canonical image was built successfully and matches the tested Ubuntu candidate digest. Frontend build layers were reused because frontend content/lockfiles were unchanged. The fresh backend/Ubuntu runtime candidate build compiled the new dependency graph and installed/upgraded its runtime packages; no all-layer uncached-build claim is made for this follow-up.

Initial canonical build/test attempts failed when the environment filled its disk. Only two earlier audit build-output directories were removed; application code and deployment volumes were preserved. The interrupted checks were rerun after space recovery and are not counted as passing attempts. A candidate scan attempted before its image existed correctly reported infrastructure failure, and was rerun after the build completed. No matching disposable containers/volumes remained after final verification.

Trade-offs: uncompressed image size is 139,022,963 bytes versus 101,469,077 for the preceding Debian 13 image. A single local 200-request keep-alive sample measured RSS 8,464 KiB versus 7,896 KiB, seven threads in each, greeting median 0.357 vs 0.333 ms and p95 0.466 vs 0.489 ms. These small serial samples are not a capacity/load or statistical regression guarantee. Retained medium/low findings, the temporary upstream pin, native Windows/ARM support, and future database updates still require maintenance. No platform integration was modified or tested; remote CI, artifact upload and Code Scanning remain unverified from this environment.


## Historical first remediation snapshot

Recorded on 2026-11-10 on Linux/amd64 after review of the Step 5 CI artifacts. At this stage the remediation was partial and security checks remained blocked.

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

## Step 6B: explicit GNU recovery utilities

The production-image maintenance helpers now use absolute GNU-prefixed commands:
`/usr/bin/gnudirname`, `/usr/bin/gnurealpath`, `/usr/bin/gnumktemp`,
`/usr/bin/gnurm`, `/usr/bin/gnusync`, and `/usr/bin/gnuln`.
Each helper checks executability and the `GNU coreutils` version identity before
accessing storage. Missing, failing, or non-GNU executables fail explicitly; no
PATH/default-provider fallback is allowed. Fixed paths are intentional for the
current Ubuntu image, not a promise of direct host/other-distribution support.

| Operation | Selection and behavior retained |
| --- | --- |
| Parent extraction and canonical validation | GNU dirname and realpath (`-e --`) |
| Private temporary files | GNU mktemp; existing umask/template unchanged |
| Failure/exit cleanup | GNU rm (`-f`, explicit quoted paths) |
| Filesystem durability | GNU sync (`-f`) |
| Atomic no-clobber publication | GNU ln (`-T --`), no forced overwrite |

These commands execute inside maintenance containers only. SQLite CLI remains the
database backup/integrity/restore engine. Shell `printf`, tests, traps and conditionals
are builtins. Export uses host-side `docker cp`; host commands and fixture setup
commands are not changed. Normal application startup does not invoke these helpers.
GNU coreutils 9.7 identity was checked by executing all six commands in the actual
candidate image, not inferred from package names. GNU was already installed: no
Dockerfile, package installation, dependency lock, migration or scanner policy changed.

This reduces operational use of affected uutils implementations; it does not fix
or remove the installed rust-coreutils package. The package is intentionally retained
because safely replacing its protected Ubuntu provider is a separate reviewed task.
Do not force removal of protected/essential packages. Other runtime findings and
the temporary SQLx upstream pin remain maintenance work.

### Step 6B verification

Executed on Linux/amd64, 2026-11-10:

```sh
sh -n templates/light/scripts/sqlite-backup.sh
sh -n templates/light/scripts/sqlite-restore.sh
python3 scripts/test-create-light.py -v
python3 scripts/test-security-scan.py -v
python3 scripts/test-smoke-cleanup.py -v
python3 scripts/test-smoke-paths.py -v
python3 scripts/test-standalone-docker.py -v
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" -t kitternel-light:gnu-recovery templates/light
python3 scripts/docker-smoke.py --image kitternel-light:gnu-recovery -v
python3 scripts/sqlite-backup-smoke.py --image kitternel-light:gnu-recovery -v
python3 scripts/sqlite-backup-smoke.py --image kitternel-light:gnu-recovery -v SQLiteBackupSmoke.test_gnu_identity_missing_tools_and_failure_propagation
python3 scripts/security-scan.py rust --project templates/light --reports /tmp/step6b-security
python3 scripts/security-scan.py npm --project templates/light --reports /tmp/step6b-security
python3 scripts/security-scan.py image --project templates/light --image kitternel-light:gnu-recovery --reports /tmp/step6b-security
python3 scripts/standalone-docker-smoke.py --proxy-ca "$CODEX_PROXY_CERT"
git diff --check
```

The six GNU-prefixed executables are supplied by the already installed
`gnu-coreutils` package. The default dirname, realpath, mktemp, sync and ln resolve to uutils 0.10.0.
Default rm already resolves to GNU 9.7; its explicit GNU path additionally prevents
PATH shadowing without claiming a provider change for that operation.
`ln -T`, `sync -f` and canonical/temp-file behavior retain their existing arguments;
explicitly selecting dirname/rm alongside them keeps all maintenance filesystem
operations on the same verified provider.

Regression totals: generator 7, security policy 11, cleanup 5, target paths 5,
standalone orchestration 9. Canonical-image Docker/Compose tests: 5; recovery/cleanup:
8. A focused final utility-failure test also checks version-command failure and
restore sync failure. Coverage includes GNU identity, missing/non-executable tools,
wrong identity, PATH shadowing, failure propagation, concurrent publication,
space/dollar/Unicode database filenames, WAL backup/export, migration checksums,
unchanged live-source data, invalid inputs, symlinks and orphan sidecars.

RustSec and both npm audit scopes pass with zero findings. Trivy before/after:
46 occurrences, 36 distinct CVEs, 42 MEDIUM, 4 LOW, zero HIGH/CRITICAL/UNKNOWN.
All 20 uutils findings remain visible. No ignore rules or severity changes were made.
The generated image was additionally scanned using its own copied security script;
it produced the same counts. All scans used the committed tool pins; the allowed
Trivy GHCR database and optional public build CA preserved TLS verification.

Initial uncached standalone build and overlapping runtime checks failed because
the environment ran out of disk. Two reproducible Cargo target caches (the checkout
and an earlier temporary clean-build fixture) were removed, with no database volume
or source changes. Those failed attempts are not counted as passing. The canonical
image build reused existing layers; the repeated standalone validation built the
independent application without cache. Rust/frontend unit, lint and browser suites
were not rerun because their code/dependencies are unchanged; the clean generated
build compiled Rust and typechecked/built the frontend. Native Windows/ARM, remote
GitHub Actions and production deployments remain unverified.
