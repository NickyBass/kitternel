# Contributing to Kitternel

Read [AGENTS.md](AGENTS.md) and the [implementation plan](docs/development/IMPLEMENTATION-PLAN.md) before changing code. Keep code, comments, documentation, and commit messages in English. Work on one focused milestone or feature at a time; authentication and Advanced need their own design and task.

## Prerequisites and first run

Use Rust 1.99.1 through rustup, including rustfmt and Clippy, Node 24.22.1, npm 11, a native C toolchain/linker, and Python 3 with its standard SQLite module. The version files under `templates/light` are authoritative. SQLx builds bundled SQLite; no SQLx CLI or database server is required. Docker with BuildKit and Compose v2 is required for container and backup/restore verification. Linux is the tested deployment target.

```sh
git clone https://github.com/NickyBass/kitternel.git
cd kitternel
cd templates/light/frontend
npm ci --no-audit --no-fund
npm run build
cd ../backend
cargo run --locked
```

From another terminal, check `/health/live`, `/health/ready`, and `/api/hello` on port 8080. Open the root page on that same machine. In a remote/cloud task, your own browser's localhost is a different computer; interactive preview depends on the client, while browser tests can run inside the task.

For frontend hot reload, leave the backend running and run `npm run dev` from `templates/light/frontend`. Vite uses port 5173 and proxies API/health to port 8080. Export `API_PROXY_TARGET=http://127.0.0.1:8081` if the backend uses a different port. The [README](README.md) documents runtime configuration and all defaults. `.env.example` is a reference; the backend does not load `.env` files automatically.

Cloud tasks already have an isolated checkout. Reuse it; do not create a Git worktree unless explicitly requested. Do not overwrite pre-existing changes or print credentials during diagnosis.

## Required checks

Run from `templates/light/frontend`:

```sh
npm ci --no-audit --no-fund
npm run typecheck
npm run lint
npm test
npm run build
```

Run from `templates/light/backend`:

```sh
cargo fmt --all -- --check
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo test --locked
cargo build --locked
python3 ../../../scripts/backend-smoke.py
python3 ../../../scripts/migration-build-smoke.py
```

The migration regression builds a disposable source copy twice using already downloaded dependencies offline. It does not alter migrations or build outputs in the checkout.

Install Chromium from `templates/light/frontend`, then run the isolated browser suite:

```sh
npx playwright install --with-deps chromium
python3 ../../../scripts/browser-smoke.py
```

On a managed machine with system Chromium, set `CHROMIUM_PATH` to its executable instead of downloading another copy. The browser helper owns a temporary database and server; it does not require an existing server. Process/signal tests target Unix. Report unsupported checks explicitly instead of describing them as passing.

From the repository root, validate packaging and data operations:

```sh
docker build -t kitternel-light:local templates/light
python3 scripts/docker-smoke.py --image kitternel-light:local
python3 scripts/sqlite-backup-smoke.py --image kitternel-light:local
```

See the [Docker guide](docs/deployment/docker.md) for the optional cloud proxy CA build secret. Test runners use uniquely named disposable Docker resources; do not substitute a real deployment volume into a smoke test. CI runs the same commands, with full frontend/Rust/browser gates in one job and packaging/storage gates in another. A local pass does not establish a remote GitHub Actions pass.

## Architecture and dependency changes

Keep one backend crate and one production process. Use cohesive modules and concrete feature boundaries. Add abstractions or dependencies only when a current feature needs them. Prefer maintained releases with narrow features and commit both lockfiles. Do not add Redis, queues, microservices, Kubernetes, PostgreSQL, or a component framework to the Light foundation.

Use bound SQL parameters, validated configuration, stable public errors, and safe structured diagnostics. Keep all API routes under `/api`; do not let SPA fallback mask API/health 404s. Maintain liveness/readiness separation, HTTP transport limits, graceful shutdown, and same-origin frontend requests. Never trust forwarded headers without an explicitly configured trusted proxy.

## Migrations and data safety

Add a new versioned SQL file to `backend/migrations`; never edit an applied migration. The build script watches new migration files. Startup applies migrations before accepting traffic and refuses incompatible history. Test a fresh database, repeated startup, and upgrading an existing database with retained data. Keep destructive migrations out of automatic startup; they require a separately reviewed operational procedure and a verified backup.

Tests must use temporary databases or disposable volumes. The supported deployment is single-instance SQLite WAL on a local filesystem. Use the [backup/restore guide](docs/deployment/backup-restore.md); do not copy a live database file or delete production storage to make a test pass.

## Pull requests and security

Explain the concrete problem and resulting behavior, list commands actually executed and their results, and identify risks/unverified platforms. Include regression tests and documentation with behavior changes. Keep unrelated formatting/refactoring out of the change. Pin CI actions to verified commit SHAs and keep workflow permissions minimal.

Report vulnerabilities using [SECURITY.md](SECURITY.md). Dependency checks can be run with `npm audit` from the frontend and `cargo audit` from the backend when cargo-audit is installed. Review advisory applicability and compatibility; do not disable integrity/TLS checks, suppress assertions, or blindly apply a downgrade suggested by audit tooling.

The existing [MIT license](LICENSE) remains in place. Do not invent a copyright holder or alter licensing as part of an unrelated contribution.
