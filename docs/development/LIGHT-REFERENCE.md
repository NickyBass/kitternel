# Light technical reference

An open-source, AI-native Rust web development toolkit focused on small, maintainable applications and predictable deployment.

## Current status

Light milestones 1–5 provide a Rust/Axum backend with SQLite and a responsive React/TypeScript frontend. One application process serves the built frontend, API, and health endpoints. Configuration validation, JSON lifecycle logs, versioned migrations, a persistent greeting, and bounded graceful shutdown are included. A canonical Docker image and Compose configuration are included. Contributor/security documentation, platform configuration guides, and tested local backup/restore helpers are included. Real Dokploy/Coolify deployments remain unverified. Authentication and authorization are not provided. This is not a production-ready starter yet.

- **Light:** Rust, Axum, SQLite, React, TypeScript.
- **Advanced (later):** Rust, Axum, PostgreSQL, React, TypeScript.

See the [implementation plan](../../docs/development/IMPLEMENTATION-PLAN.md) for architecture, acceptance criteria, and trade-offs. The initial Light foundation is implemented. Authentication/authorization hardening and Advanced remain later stages, with separate design and approval.

## Guides and feature status

- [Contributing](../../CONTRIBUTING.md): prerequisites, local workflow, required checks, and migration rules.
- [Security policy](../../SECURITY.md): current boundaries and sensitive reporting.
- [Step-by-step Docker installation](../../docs/deployment/docker-installation.md), [Docker reference](../../docs/deployment/docker.md), [Dokploy](../../docs/deployment/dokploy.md), [Coolify](../../docs/deployment/coolify.md).
- [Backup and restore](../../docs/deployment/backup-restore.md), [troubleshooting](../../docs/deployment/troubleshooting.md), [verification record](../../docs/development/verification.md).

| Capability | Status |
| --- | --- |
| Axum + SQLite API, React/TypeScript/Tailwind UI | Implemented and tested locally |
| HTTP limits, safe configuration, structured diagnostics | Implemented with regression tests |
| Canonical Docker image and persistent Compose storage | Implemented and tested on Linux/amd64 |
| Consistent SQLite snapshot/export/restore to a fresh volume | Implemented; local Docker drill exercised |
| Dokploy and Coolify settings | Documented from official sources; real deployments unverified |
| GitHub Actions | Configured; remote run status must be checked on GitHub |
| Vulnerability scans | RustSec/npm/final-image tooling; [policy and limits](../../docs/development/SECURITY-SCANNING.md); blocking findings require triage |
| Authentication, authorization, sessions, CSRF | Later hardening stage; not implemented |
| Advanced / PostgreSQL | Later stage; not implemented |

No one-click deployment, zero-downtime, recovery-time, capacity, or production-readiness guarantee is made. See the verification record for the scope of actual checks.

## Create your own application

Run `python3 scripts/create-light.py garden-notes ../garden-notes` from this Git checkout. The new destination must not exist. See the [standalone creation guide](../../docs/development/CREATE-LIGHT.md) for naming rules, generated files, customization, and verification limits.

## Quick start

Install [rustup](https://rustup.rs/) using the official instructions. A native C linker is also required (for example, `build-essential` on Debian/Ubuntu). The backend's `rust-toolchain.toml` pins Rust and the required formatter/linter. Run commands from the backend directory so rustup selects that toolchain. SQLx builds bundled SQLite; no separate database server or SQLx CLI is needed. Install Node.js 24.22.1 (pinned in `frontend/.node-version`) and npm 11; the tested npm version is 11.9.0. Node is needed for development and frontend builds, not to serve the compiled application.

```sh
cd templates/light/frontend
npm ci --no-audit --no-fund
npm run build
cd ../backend
cargo run --locked
```

Startup checks that the frontend build exists, creates `data/kitternel.db`, applies embedded migrations, then listens on `0.0.0.0:8080`. Open `http://localhost:8080` in a browser on the same machine to see the landing page and real database greeting. From another terminal:

```sh
curl --fail http://127.0.0.1:8080/health/live
curl --fail http://127.0.0.1:8080/health/ready
curl --fail http://127.0.0.1:8080/api/hello
```

Expected responses, respectively:

```json
{"status":"ok"}
{"status":"ready"}
{"message":"Hello from Kitternel Light."}
```

Liveness checks only the HTTP process; readiness executes a database query with a one-second deadline. `/api/hello` reads the greeting from SQLite on each request, with a three-second deadline. Database failures return HTTP 503 with safe public messages. Unknown API and health routes return 404. Eligible frontend navigation requests receive the SPA entrypoint; missing assets and file paths return 404. All API endpoints are read-only; no public data mutation endpoint is provided.

## Runtime configuration

| Variable | Default | Accepted values |
| --- | --- | --- |
| `PORT` | `8080` | Integer from 1 to 65535 |
| `LOG_LEVEL` | `info` | `error`, `warn`, `info`, `debug`, `trace` |
| `SHUTDOWN_TIMEOUT_SECS` | `10` | Integer from 1 to 300 |
| `HTTP_HEADER_TIMEOUT_SECS` | `10` | Integer from 1 to 60; total time allowed to receive request headers |
| `MAX_CONNECTIONS` | `128` | Integer from 1 to 4096; maximum active HTTP connections |
| `SQLITE_PATH` | `data/kitternel.db` | Ordinary persistent file path; empty values, `:memory:`, and `file:` SQLite URIs are rejected |
| `FRONTEND_DIR` | `../frontend/dist` | Directory containing the compiled `index.html` and assets |

Relative paths resolve from the process working directory. Example:

```sh
PORT=8081 SQLITE_PATH=data/example.db cargo run --locked
```

`templates/light/.env.example` documents values; the application does not automatically load `.env` files. Invalid configuration exits nonzero without echoing supplied values. Lifecycle logs use JSON on stdout; terminal errors use stderr. Database startup errors emit structured stage/category fields and, where applicable, the migration version and numeric SQLite code. Public messages remain generic; database contents, SQL, paths, and arbitrary database error text are not logged. Request headers, bodies, and query strings are not logged. No permissive CORS or forwarded-header trust is enabled.

The HTTP/1 transport uses an explicit Tokio timer for header deadlines, accepts at most 64 headers within a 32 KiB read buffer, and bounds active connections using `MAX_CONNECTIONS`. At capacity, accepting new connections pauses until a slot is released; the operating system backlog is not an application task queue. Header deadlines are measured per header read, rather than renewed for every byte. These limits bound resources; they are not a throughput or DoS-resistance guarantee.

On Unix, SIGTERM or SIGINT stops accepting connections and drains in-flight requests. Draining beyond the configured deadline exits nonzero. Other platforms use Ctrl+C. The database pool closes after successful HTTP shutdown. Send signals directly to the binary and allow a stop grace period longer than the configured drain deadline.

## Frontend development

After the initial frontend build, keep the backend running on port 8080. In another terminal:

```sh
cd templates/light/frontend
npm run dev
```

Vite runs on port 5173 with hot reload and proxies `/api` and `/health` to the backend. It uses a strict port to avoid silently switching to a port the developer did not expect. If the backend uses another port, export `API_PROXY_TARGET`, for example:

```sh
API_PROXY_TARGET=http://127.0.0.1:8081 npm run dev
```

The client always uses relative API URLs. No broad CORS policy is required. Production serves Vite's build through Axum; no Vite or Node process is required at runtime. Rebuild the frontend to update the files served by Axum. The single landing page demonstrates loading, ready, empty-message, failure, and retry states; a client-side routing library is deliberately deferred until a real multi-page feature needs one.

Only trusted compiled frontend files belong in `FRONTEND_DIR`. Keep databases, secrets, and symlinks to private files outside that directory. Axum rejects hidden files and traversal paths, reserves `/api` and `/health`, and limits SPA fallback to GET/HEAD navigation accepting HTML. Fingerprinted files under `/assets/` have immutable caching; HTML is revalidated, and API/health responses use `no-store`. The application supplies a same-origin Content Security Policy, `nosniff`, frame denial, and a restrictive referrer policy. These headers do not supply authentication or authorization.

In Codex Cloud, loopback addresses belong to the cloud machine, not your computer. An interactive preview depends on capabilities exposed by your client; it is not guaranteed. Browser tests can still run inside the cloud and save screenshots without an interactive Desktop panel.

## Docker

For a first installation, follow the [step-by-step Docker guide](../../docs/deployment/docker-installation.md). It covers Windows PowerShell and Linux/macOS terminals, prerequisites, private repository access, health checks, persistent data, updates, troubleshooting, and an AI-assistance prompt. No host Rust or Node installation is required for this workflow.

From the repository root:

```sh
docker build -t kitternel-light:local templates/light
cd templates/light
docker compose up -d --no-build
```

Compose serves the frontend and API on loopback port 8080, mounts a named SQLite volume at `/data`, and runs as UID/GID 10001 with a read-only application filesystem. If port 8080 is occupied, use `HOST_PORT=8081 docker compose up -d --no-build`. The image health check queries database readiness; SIGTERM reaches the Rust process directly.

See the [Docker guide](../../docs/deployment/docker.md) for plain Docker commands, cloud proxy CA support, storage permissions, health semantics, and data lifecycle precautions. The guide uses a single instance on local persistent storage; it does not claim zero downtime or verified Dokploy/Coolify deployment.

After building, run the container checks from the repository root:

```sh
python3 scripts/docker-smoke.py --image kitternel-light:local
python3 scripts/sqlite-backup-smoke.py --image kitternel-light:local
```

The suite creates and cleans up only uniquely named disposable test resources, including a separate Compose project. Never delete the deployment's data volume as part of an upgrade or troubleshooting step.

## SQLite operations

The pool has at most four connections and a two-second acquisition timeout. Every connection enables foreign keys and a five-second busy timeout. WAL mode supports concurrent readers; `synchronous=FULL` favors durability. These conservative settings are starting points, not throughput guarantees. SQLite still permits only one writer at a time.

Migrations live in `templates/light/backend/migrations/` and are embedded at compile time. Restarting the application applies pending migrations before serving traffic. Existing migrations are checksum-checked and must not be edited after deployment: add a new reviewed migration and rebuild instead. The backend build script watches the migrations directory so adding only a new SQL file also updates incremental builds. Initial seed data is inserted by migration only; restarting does not overwrite changes. Migration failures abort startup without resetting the database. Destructive schema changes require a separate reviewed procedure and a verified backup; none are included here.

Use storage owned by the process user, with access restricted to authorized operators. The parent directory is created when absent, using inherited filesystem permissions; provision restrictive directory permissions/umask for real deployments. Persist the entire database directory, including WAL/SHM files, on a local filesystem. Do not share the WAL database between hosts, use network filesystems, or run overlapping app replicas. Do not commit production data.

Do not copy only the live `.db` file to create a backup. Use SQLite's online backup API or a safe equivalent and verify restoration. Container operation is documented in the Docker guide. Use the [backup/restore procedure](../../docs/deployment/backup-restore.md) for the tested local drill; platform settings and their unverified deployment status are documented separately.

## Verification

From `templates/light/frontend`:

```sh
npm ci --no-audit --no-fund
npm run typecheck
npm run lint
npm test
npm run build
```

Then from `templates/light/backend`:

```sh
cargo fmt --all -- --check
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo test --locked
cargo build --locked
python3 ../../../scripts/backend-smoke.py
python3 ../../../scripts/migration-build-smoke.py
```

The process smoke suite requires Python 3 and Unix SIGTERM support, with no third-party Python packages. Each test uses temporary storage and the compiled frontend. It checks real HTTP liveness/database data, JSON lifecycle logs, clean SIGTERM exit, invalid configuration, occupied ports, invalid storage, missing frontend builds, URI rejection, and safe migration diagnostics. The incremental migration regression builds a temporary backend copy twice, adding only SQL between builds, and verifies the new migration was applied. It reuses downloaded Cargo dependencies offline, requires the normal toolchain/dependencies to be installed first, and leaves the checkout and its target directory untouched. Rust tests check SQLite behavior, bounded readiness, static-file routing, traversal rejection, caching, security headers, slow-header expiry, connection backpressure/recovery, in-flight shutdown draining, and forced shutdown deadlines.

For real-browser tests, install Chromium using Playwright from `templates/light/frontend`:

```sh
npx playwright install --with-deps chromium
python3 ../../../scripts/browser-smoke.py
```

The browser helper starts an isolated real backend on a temporary port with a temporary database, runs Playwright against the production frontend, and stops the backend afterward. No pre-existing server is needed. If system Chromium is already available, use `CHROMIUM_PATH=/path/to/chromium python3 ../../../scripts/browser-smoke.py` instead of downloading another browser. The suite verifies actual database data rendered in the page, client-route fallback, mobile layout, absence of browser errors, and an API failure state. Screenshots are saved to the ignored `frontend/test-results/` directory. `npm run test:e2e` alone targets an already running server at `BASE_URL` (default port 8080).

CI runs the same frontend/Rust checks and isolated browser suite, plus a separate canonical Docker build, container/Compose smoke suite, and consistent SQLite backup/export/restore drill. The frontend temporarily overrides `minimatch` to 11.0.5 to address GHSA-g3hv-75wg-m249 in development tooling. Node 24 is supported by that release; lint/typecheck/tests/build have been exercised with the override. Remove it when the parent tools declare a compatible fixed release, then rerun verification. Cargo and npm lockfiles fix resolved dependencies; update them deliberately alongside compatibility checks. Local validation does not establish that GitHub Actions has run remotely.

See [agent instructions](../../AGENTS.md) before making changes. Keep code and documentation in English; make focused changes with relevant tests. Existing cloud checkouts are already isolated: use them directly rather than creating worktrees unless explicitly requested.

## License

[MIT](../../LICENSE).
