# Light verification record

Recorded on 2026-11-09 during milestone 5. This is evidence of specific local checks, not certification, a production deployment, or an ongoing CI status badge.

## Source and environment

Application source was validated from a fresh GitHub clone of main at `41b5cf09c366af94a557ee5490fd8712f3d7fd52`. That is the application implementation used by this milestone; Rust/frontend logic, migration SQL, and their lockfiles were not changed during the handoff. The milestone branch adds documentation, image-packaged SQLite helper scripts, their Docker drill, data-file ignore rules, and a CI step.

The fresh clone began without node_modules or a Rust target directory. Downloaded package caches and installed toolchains were reused with locked installation/build commands. The Docker tests used the image built from the milestone branch, including the new backup/restore scripts.

Environment: Linux/amd64, Rust 1.99.1, Node 24.22.1, npm 11.9.0, Python 3.12.14, Docker 29.9.2, and Compose 2.40.3. System Chromium was used through `CHROMIUM_PATH`; no interactive Desktop or public cloud preview is assumed.

## Executed checks

| Check | Actual result |
| --- | --- |
| Fresh GitHub checkout | Clone succeeded at the commit above |
| `npm ci --no-audit --no-fund` | Passed in the fresh clone |
| Frontend typecheck and lint | Passed |
| Component tests | 5 passed; none skipped |
| Frontend production build | Passed |
| Rust formatting and Clippy with warnings denied | Passed |
| Rust test suites | 21 passed; none skipped; zero-test binary/doc harnesses are not counted as validation |
| Locked backend build | Passed |
| Native process smoke suite | 7 passed |
| Incremental migration build regression | Passed: a SQL-only added migration was embedded and applied in a disposable copy |
| Documented `cargo run --locked` | Started with default frontend/database paths and a free test PORT; readiness and expected greeting were verified |
| Real-backend browser suite | 2 passed; included actual database data, mobile layout, SPA fallback, and API failure UI |
| Canonical Docker build | Passed with the existing cloud proxy CA supplied as a BuildKit secret; application builder layers reused valid cache |
| Docker/Compose smoke suite | 5 passed, including persistence across recreation, non-root/read-only operation, port/health behavior, SIGTERM, and rejected storage conditions |
| Backup/export/restore drill | 2 tests passed with the final helper scripts; details below |
| Shell syntax and local Markdown links | Checked locally; no missing local document targets |

The final helper refinement bounds foreign-key failure output to one row and was checked with the backup drill. Application/container behavior was validated separately by the Docker/Compose suite; application code was unchanged by that refinement. All disposable Docker test containers/volumes were removed. No real deployment data volume was used.

## Recovery evidence

The drill retained an application using WAL, wrote a non-seed greeting, created a snapshot through SQLite's online backup API, and checked integrity, foreign keys, journal mode, data, and successful migration metadata. It exported the finalized single file with `docker cp` and opened it independently using Python's SQLite library.

After changing the source data again, it restored the earlier snapshot into a different named volume and launched the matching application image there. HTTP reads confirmed the restored greeting while the original application still exposed its newer data. Restore and backup refusal cases covered occupied targets, existing snapshots, missing source, invalid filenames, corrupt database bytes, foreign-key violations, and orphaned WAL files. These checks validate a local consistent recovery drill, not off-host storage durability, encryption, scheduler behavior, or a promised RPO/RTO.

## Explicitly unverified

- GitHub Actions status: the workflow contains the same gates plus the backup drill, but requests to the GitHub Actions API returned Forbidden in this cloud session. No remote CI pass is claimed.
- Dokploy and Coolify: their official documentation repositories were inspected at commits pinned in each guide. Their documentation websites were blocked by the cloud network. No actual platform instance, proxy routing, scheduling/replacement behavior, DNS, or TLS issuance was tested.
- Private GitHub vulnerability reporting availability: the security policy provides a conditional route and fallback, not a claim that reporting is enabled.
- ARM, Windows, and macOS deployment behavior; production traffic/load/failure testing; host-loss recovery; off-host encrypted backup transfer and retention; production SLOs.
- Cargo advisory scanning, container vulnerability scanning, and an exhaustive dependency/security audit were not performed in this milestone. The previous review-remediation record reports its separate npm audit result; that is not a new scan here.
- Authentication, authorization, sessions/CSRF protection, and Advanced/PostgreSQL are outside the initial Light foundation and were not implemented or tested.

Use [CONTRIBUTING.md](../../CONTRIBUTING.md) for repeatable commands, the [Docker guide](../deployment/docker.md) for image setup, and the [backup/restore guide](../deployment/backup-restore.md) for operational prerequisites and cutover boundaries. Update this record when new evidence exists; do not convert documented configuration into a deployment-success claim.

## Post-review recovery corrections

Recorded on 2026-11-09 against milestone 5 commit `b044a53151e03dbf17e41bed9862569c0ec481a4`. Only recovery helpers, their smoke runner, and documentation changed; application code, migrations, and dependency lockfiles were unchanged.

Two new regressions failed against the original milestone image: foreign-key query execution errors were treated as successful checks, and restore accepted symlinked parent directories. Helpers now check SQLite exit status separately from result contents and require canonical existing database parent directories below `/data`. Publication explicitly treats its destination as a file. The smoke runner now propagates nested cleanup failures and continues attempting remaining volume removals.

The corrected canonical image built successfully as `kitternel-light:recovery-fixes`. `python3 scripts/sqlite-backup-smoke.py --image kitternel-light:recovery-fixes -v` passed all six tests: four Docker recovery tests and two isolated cleanup-failure simulations. Coverage includes both backup and restore rejection of malformed foreign-key schemas, symlinked parents inside/outside `/data`, ordinary nested-path persistence, and the existing live-WAL recovery drill. `python3 scripts/docker-smoke.py --image kitternel-light:recovery-fixes -v` passed all five Docker/Compose tests. Both helper scripts passed `sh -n`, and `git diff --check` passed. Disposable Docker test resources were removed.

Rust/frontend suites were not rerun for these script/documentation changes. The cleanup failures were simulated, not failures of the Docker daemon. No remote CI result or actual platform deployment is claimed.
