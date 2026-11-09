# Kitternel Light implementation proposal

Status: architecture approved; milestones 1–3 implemented. Work proceeds one milestone at a time, with a review checkpoint before starting milestone 4. The structure below describes the target foundation.

## Repository findings and scope

Initial planning inspected main at `5c632c2`, including AGENTS.md, START-HERE.md, LICENSE, and the first-task prompt. At that point there was no application, dependency manifest, CI, or test suite. The existing MIT license names NickyBass; preserve it rather than replacing it with a placeholder.

The initial request was planning only; the user subsequently approved milestone 1, then requested further work with an explicit constraint to proceed one milestone at a time. The user subsequently authorized milestone 3; the current implementation stops at milestone 3. The first-task prompt has been moved into this directory.

Light comes first: one Rust/Axum application, SQLite, and React/TypeScript. Advanced follows only after Light is stable and separately authorized. No authentication, RBAC, email, queues, Redis, microservices, Kubernetes, AI CLI, or PostgreSQL in this foundation.

## Architecture and proposed structure

Use a self-contained template with one backend crate, one frontend package, and one production process. Organize by concrete responsibility; introduce feature modules as real features appear. Do not add repository traits, dependency-injection frameworks, or shared database abstractions in anticipation of Advanced.

```text
/
  AGENTS.md
  README.md
  CONTRIBUTING.md
  SECURITY.md
  LICENSE
  .gitignore
  .github/workflows/ci.yml
  docs/
    development/
      CODEX-FIRST-TASK.md
      IMPLEMENTATION-PLAN.md
    deployment/
      docker.md
      dokploy.md
      coolify.md
      troubleshooting.md
  templates/light/
    Dockerfile
    .dockerignore
    compose.yaml
    .env.example
    backend/
      Cargo.toml
      Cargo.lock
      rust-toolchain.toml
      migrations/
      src/
        main.rs
        lib.rs
        config.rs
        error.rs
        db.rs
        routes/
          mod.rs
          hello.rs
          health.rs
        static_files.rs
      tests/
    frontend/
      package.json
      package-lock.json
      .node-version
      index.html
      vite.config.ts
      tsconfig.json
      src/
        main.tsx
        App.tsx
        api.ts
        styles.css
```

HTTP flow: reverse proxy terminates HTTPS; Axum serves `/api`, health endpoints, and compiled frontend assets on the same origin. During development Vite proxies API and health requests to Axum. Node is a build/development dependency only.

Handlers use explicit application state containing validated configuration and a small SQLx pool. Keep SQL parameterized and close to its feature. Centralize error-to-response mapping, return stable public errors, and retain diagnostic details only in structured server logs.

Proposed API contract:

- `GET /api/hello`: JSON greeting read from a seeded SQLite row, demonstrating migration, query, serialization, and frontend rendering without adding a public write API.
- `GET /health/live`: cheap 200 response when the HTTP process can respond; no database query.
- `GET /health/ready`: bounded database query and initialization state; 200 when ready, 503 otherwise, with no internal details.
- Unknown API and health paths: explicit 404, never SPA HTML. Missing assets return 404. SPA fallback applies only to eligible frontend navigation requests using GET/HEAD.

## Minimum viable foundation

Deliver one responsive landing page that renders a database-backed greeting and backend status, with loading, empty, and failure states. Include configuration validation, migrations, graceful SIGTERM shutdown, structured logs, focused automated tests, locked builds, and a production container with persistent storage.

Use Rust stable pinned to a tested release, Axum, Tokio with only needed features, SQLx SQLite/migrations, Serde, tracing, and narrowly selected HTTP middleware. Frontend: React, TypeScript, Vite, Tailwind CSS, npm with committed lockfile. Add shadcn/ui only when a concrete component needs it. Select maintained compatible versions during implementation and record exact tool versions; do not invent versions in this plan.

## First five implementation milestones

Each milestone is a small reviewable change; later milestones build on earlier acceptance criteria.

| Milestone | Scope | Acceptance criteria |
| --- | --- | --- |
| 1. Runnable backend shell | Crate, pinned toolchain, validated config, Axum routing, tracing, shutdown, initial Rust CI | Locked build succeeds; liveness returns 200; invalid configuration fails clearly without secrets; route tests execute; fmt, Clippy with warnings denied, and tests pass. |
| 2. SQLite vertical slice | Versioned migration and seed, SQLx pool, greeting query, readiness | A new temporary database migrates; reopening preserves data; repeat migration is safe; WAL and per-connection foreign keys are verified; hello returns seeded data; bounded database failures produce readiness 503 and sanitized API errors. |
| 3. Frontend and single-origin serving | React/TypeScript/Vite/Tailwind landing page, API client, static routing | Locked npm install, typecheck, lint, UI tests, and production build pass; browser smoke test displays actual API data; failure state is tested; development proxy works; production serves assets; API/health 404s and missing assets cannot fall through to SPA HTML. |
| 4. Canonical container and persistence | Multi-stage Dockerfile, Compose, non-root runtime, health check | Image builds from lockfiles; container serves UI/API on configured PORT; health check runs with a probe actually present in the image; volume is writable by runtime UID; test-written data survives container recreation; SIGTERM completes within grace period; missing/unwritable storage fails clearly. |
| 5. Contributor and deployment handoff | Complete CI, quick start, security/feature status, Docker/Dokploy/Coolify instructions, backup/restore | Fresh documented setup succeeds; CI runs Rust/frontend gates plus container smoke and persistence tests; consistent SQLite backup restores to a separate database and passes integrity/data checks; each platform document states context, Dockerfile, port, mount, health, domain/TLS, and verification status. Platform deployments remain explicitly unverified until exercised on actual instances. |

Introduce relevant tests and documentation with each milestone; milestone 5 consolidates them rather than deferring quality until the end. Milestone 1 adds configuration and routing tests plus real-process HTTP/lifecycle smoke tests. Use the commands in the root README for current verification; later milestone checks remain pending.

## SQLite and migration policy

Proposed initial settings: WAL, foreign keys enabled on every connection, pool maximum 4, busy timeout 5 seconds, and `synchronous=FULL` for durability. Treat these as configurable starting points to validate under load, not performance promises. Bound pool acquisition and health query time independently; health probes must not consume the entire request budget.

Use a database file such as `/data/kitternel.db` on a local persistent filesystem. SQLite permits one writer at a time; keep write transactions short. Do not place a WAL database on network filesystems or share it across hosts/replicas. Document disk capacity, WAL growth/checkpoint behavior, and expected write limits.

For the foundation's single instance, apply embedded SQLx migrations before accepting traffic. Log migration start/outcome and refuse startup after failure. Seed data belongs in the initial migration, not each startup. Never silently reset a database or automatically apply destructive changes. Future destructive migrations require a separate reviewed operational procedure and verified backup. Re-running startup checks migration history safely.

## Docker, Dokploy, and Coolify

- One canonical Dockerfile at `templates/light/Dockerfile`, with build context `templates/light`. Separate locked frontend and Rust builder stages from a minimal compatible Linux runtime. Copy frontend build output as files served by Rust; no Node server in production.
- Prefer a conventional minimal glibc runtime initially for predictable SQLx/native linking and operational tools. Evaluate Alpine/musl or distroless only with measured size gains and compatible builds. Pin base image digests and define a deliberate security update process.
- Run as a fixed non-root UID/GID; prepare `/data` ownership for named volumes and document host bind-mount permissions. Never recursively change arbitrary host directory permissions at startup. Exclude secrets, databases, Git metadata, and local build outputs from the Docker context.
- Bind `0.0.0.0` with default PORT 8080. Production runtime configuration comes from environment variables; frontend API URLs stay relative. Missing required frontend assets or an unwritable database directory are startup errors.
- Compose runs one app service and mounts a named volume at `/data`. Persist the entire directory, including SQLite `-wal` and `-shm` files. Recreating the app must retain the volume; document that deleting volumes destroys data.
- Proposed Docker health check: a dedicated lightweight probe included in the image calls `/health/ready`, with a 3-second timeout, 30-second interval, three retries, and an initial startup grace period validated against migrations. Document separately that container health status alone does not guarantee automatic restart. Platform liveness/restart checks should use `/health/live` where separately supported.
- Dokploy and Coolify use the same Dockerfile/context and internal port, a persistent local mount at `/data`, and platform-managed HTTPS/domain routing. Set single-instance deployment and disable overlapping writers/rolling replicas for the SQLite foundation. Never promise zero downtime. Verify exact platform settings against the deployed version rather than assuming UI behavior.
- Stop accepting requests on SIGTERM, drain in-flight work within a configured grace period, and close the pool before exit. Coordinate proxy/container stop timeouts.
- Backups use the SQLite online backup API or a verified equivalent such as `VACUUM INTO`, with sufficient disk headroom and protected storage outside the application volume. Never copy only the live `.db` file in WAL mode. Test restoration separately; rolling back an image does not roll back its database schema.

## Decisions, trade-offs, and risks

| Decision/risk | Trade-off and mitigation |
| --- | --- |
| Single application process and same origin | Simple deployment and no default permissive CORS; frontend releases require rebuilding the image. Development proxy avoids enabling broad CORS. |
| SQLite WAL and bounded pool | Low overhead and simple operations; write concurrency and single-host availability are limited. Load-test contention, busy errors, query latency, and memory before setting capacity claims. Advanced will use PostgreSQL without forcing shared database abstractions now. |
| File-served frontend | Avoids embedding large assets into the binary; image must package the correct build and startup must verify its presence. Cache hashed assets long-term, but revalidate index.html; prevent path traversal. |
| Authentication deliberately absent | Foundation demonstrates public read-only data only. No protected-data or production-readiness claims. Cookie auth later requires CSRF defenses, secure session cookies, rotation, and tested server-side authorization. |
| Safe HTTP defaults | Bound request bodies and execution times, validate backend input, sanitize errors, and add appropriate content/security headers. Trust forwarded headers only from configured proxies; use actual deployment topology to determine secure redirects and client identity. |
| Dependency and build integrity | Commit Cargo/npm lockfiles, use locked/frozen installs, constrain features, pin CI actions, and minimize workflow permissions. Review advisories and update pins deliberately. Lockfiles improve repeatability but do not alone guarantee bit-for-bit reproducibility. |
| Storage loss and filesystem incompatibility | Local persistent storage, verified UID permissions, disk monitoring guidance, off-volume backups, restore drills, and no network-filesystem WAL. Never log credentials or database contents. |
| Migration and rollout downtime | Startup migrations simplify the single-instance foundation; serialize deployments, back up before schema changes, and document rollback compatibility. Readiness prevents traffic before initialization but does not establish platform routing behavior without testing. |
| Platform assumptions | Docker behavior can be tested locally; Dokploy/Coolify deployments require real instances and credentials. Mark untested steps and distinguish documented configuration from verified deployment. |

Advanced remains a separately deployable starter under `templates/advanced` in a later stage. Reuse documented conventions and API design where justified; do not build or scaffold it during these milestones.

## Review checkpoint

Review each completed milestone before moving to the next. Milestone 3 is the current delivery; milestone 4 (Docker and persistence smoke tests) has not been included. Authentication and Advanced remain separate later-stage tasks.

## Milestone 1 validation

Implemented the backend shell only. Local verification passed with Rust 1.99.1: `cargo fmt --all -- --check`, `cargo clippy --locked --all-targets --all-features -- -D warnings`, `cargo test --locked` (six tests), `cargo build --locked`, and the Python process smoke suite (three tests). The smoke suite verifies HTTP liveness, JSON lifecycle logs, clean SIGTERM exit, invalid configuration without value disclosure, and occupied-port failure. GitHub Actions is configured with the same commands but has not been executed remotely as part of this task. At the milestone 1 checkpoint, SQLite, readiness, frontend, containers, and platform deployment were still unimplemented.

## Milestone 2 validation and decisions

Delivered a SQLx SQLite pool, embedded initial migration/seed, database-backed `/api/hello`, and database-aware `/health/ready`. Startup migrations complete before listening; failures stop startup without resetting the database. Greeting queries use a bound parameter. Public failures contain stable messages only; startup errors identify storage/connection/migration categories without printing SQL or paths.

The selected settings are WAL, per-connection foreign keys, `synchronous=FULL`, a five-second busy timeout, a four-connection maximum, and a two-second acquisition timeout. Readiness has an independent one-second deadline, and greeting queries have a three-second deadline. These favor a predictable small single-instance deployment; they are not measured capacity claims. Paths remain configurable through `SQLITE_PATH`, while pool/timing settings stay explicit constants until an actual tuning requirement justifies more configuration.

Local verification with Rust 1.99.1 passed formatting, Clippy with warnings denied, locked build, 11 Rust tests, and four real-process smoke tests. Checks cover persistent data on reopening, repeatable migrations, incompatible schema rejection, every connection's SQLite settings, live database greeting changes, sanitized failure responses, readiness timeout/recovery under pool exhaustion, HTTP behavior, SIGTERM exit, invalid configuration/storage, and occupied ports. GitHub Actions has not been executed remotely in this task.

At the milestone 2 checkpoint, frontend, static serving, Docker, backups/restore tooling, platform deployment documents, and Advanced were deferred. Database operations guidance is in the README; tested backup/restore procedures belong to later milestones. Milestone 2 has no public write endpoint and does not add authentication.

## Milestone 3 decisions

Delivered a React/TypeScript/Vite/Tailwind landing page with same-origin API requests, response validation, request cancellation, a five-second UI timeout, and loading/ready/empty/failure/retry states. No component library, client router, remote fonts, or additional UI framework is needed for one screen. Node 24.22.1 and npm 11.9.0 were tested; dependencies are locked. ESLint 10, Vite 8, and compatible plugins were selected from maintained releases rather than retaining the earlier draft's deprecated ESLint version.

Axum serves compiled assets from `FRONTEND_DIR` and rejects startup before database initialization if the frontend build is absent. Development requires one initial build, then Vite supplies hot reload and proxies API/health requests to Axum. This avoids adding a separate production/development mode flag or permissive CORS.

Unknown API/health routes and missing assets remain 404. SPA fallback only handles frontend GET/HEAD navigation accepting HTML; hidden files and traversal paths are rejected. API/health responses are not cached, index HTML is revalidated, and generated assets use immutable caching. Same-origin CSP and basic security headers apply to the production app. Only trusted build output belongs in the asset directory; the file server is not a sandbox for untrusted symlinks or a general file-upload service.

The CI now includes locked npm installation, typechecking, lint, component tests, frontend build, and real-backend Playwright tests in addition to the existing Rust gates. Docker and platform-specific verification remain for later milestones. Interactive cloud previews depend on client capabilities; no public preview or Desktop access is promised by this milestone.

## Milestone 3 validation

Verified locally with Rust 1.99.1, Node 24.22.1, npm 11.9.0, and system Chromium: frozen npm installation, TypeScript checks, ESLint without warnings, five component tests, and production frontend build passed. Rust formatting, Clippy with warnings denied, 15 Rust tests, locked backend build, five process smoke tests, and two real-backend Playwright tests passed. An additional browser check exercised Vite's development proxy: the database greeting rendered, readiness returned 200, and an unknown API path returned 404 with HTML Accept headers. Desktop/mobile screenshots were captured; the browser reported no application or console errors on the healthy production page. Initial route regressions (an obsolete root-404 expectation and an asset-directory redirect) were corrected and the affected checks rerun.

GitHub Actions has been updated but not run remotely. No Docker build, public preview, platform deployment, backup/restore, or authentication claim is made. The cloud backend was restarted with compiled frontend assets for inspection; this running process is temporary and is not a deployment.
