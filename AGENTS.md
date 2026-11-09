# Kitternel — Agent Instructions

## Mission
Kitternel is an open-source, AI-ready, performance-conscious web application toolkit. Build reliable, maintainable applications that deploy predictably via Docker, Dokploy, and Coolify.

## Project stages
- Stage 1: establish the repository and a working `templates/light` vertical slice.
- Stage 2: harden Light with authentication, authorization, tests, and UI primitives.
- Stage 3: add `templates/advanced` with PostgreSQL after Light is stable.
- Do not implement later stages without an explicit task.

## Stack for Light
- Rust stable, Axum, Tokio, SQLx with SQLite, Serde, tracing.
- React, TypeScript, Vite, Tailwind CSS; add shadcn/ui when needed.
- SQLite in WAL mode with foreign keys enabled, bounded busy timeout, and modest connection pool.
- A single production application container serves the compiled frontend and `/api` endpoints.
- The SQLite database must be stored in a persistent mounted directory, never inside the immutable application image.

## Architecture
- Keep backend modules cohesive and boundaries explicit; avoid premature microservices, generic frameworks, and abstractions without current use cases.
- Keep API routes under `/api`; include `/health/live` and `/health/ready` with clear semantics.
- Use one origin for frontend and API by default; SPA fallback must not mask API 404s.
- Use environment variables for runtime configuration. Provide `.env.example` without secrets.
- Prefer SQLx migrations, parameterized SQL, explicit error types, and predictable startup/shutdown.
- Treat reverse-proxy forwarded headers as untrusted unless a trusted proxy is configured.
- Never commit secrets, credentials, production data, or private keys.

## Security
- Default to safe configurations: no permissive CORS, no debug endpoints in production, no hard-coded credentials.
- Never claim authentication, authorization, or CSRF protections exist until implemented and tested.
- When adding cookie-based auth, use Secure/HttpOnly/SameSite where appropriate, CSRF defenses, session rotation, and server-side authorization checks.
- Validate user input on the backend. Avoid exposing internal error details to clients.
- Avoid logging credentials, session tokens, or personal data.

## Deployment
- One canonical multi-stage Dockerfile per template, reused by plain Docker, Dokploy, and Coolify.
- Bind to `0.0.0.0` and a configurable `PORT`; document exposed ports and health checks.
- Build frontend assets before packaging the runtime image.
- Prefer a non-root runtime user and minimal runtime image when feasible.
- Keep database migrations controlled, observable, and documented; do not perform destructive migrations automatically.
- Include persistent-volume instructions, backup/restore guidance, and deployment troubleshooting.
- Document deployment paths separately for Docker, Dokploy, and Coolify without maintaining divergent application builds.
- Do not promise one-click deployment or zero-downtime behavior unless verified.

## AI collaboration
- Before making changes, inspect the repository and explain a short implementation plan.
- Make focused changes and avoid unrelated refactoring.
- Add or update tests and docs for behavior changes.
- If a command cannot run, report exactly why; never claim checks passed without running them.
- Prefer established, maintained dependencies; avoid unnecessary packages.
- Keep code, comments, commit messages, and all documentation in English.
- In pull request summaries, list changes, verification commands/results, risks, and follow-up tasks.

## Quality gates
- Backend: `cargo fmt --all -- --check`, `cargo clippy --all-targets --all-features -- -D warnings`, `cargo test` (adapt workspace paths as needed).
- Frontend: package-manager lockfile integrity, typecheck, lint, tests where configured, and production build.
- Deployment: `docker build`, container startup, HTTP health checks, and persistent-storage smoke test when Docker is available.
- Keep CI and local verification commands consistent.

## Initial task boundary
- First task should create a minimal functioning vertical slice, documentation, and basic CI.
- Do not add auth, RBAC, email, Redis, background queues, or advanced template in the initial task.
