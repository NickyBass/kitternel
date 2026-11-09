# Codex Cloud — First Task

You are the founding engineer of **Kitternel**, an open-source, AI-ready Rust web toolkit. Read `AGENTS.md` before editing anything.

## Goal
Create the first working foundation of Kitternel, focusing only on **Kitternel Light**. The repository must be easy to understand, easy to extend with AI coding agents, and straightforward to deploy using Docker, Dokploy, and Coolify.

## Deliverables
1. Create `templates/light/` containing:
   - A Rust stable backend with Axum, Tokio, Serde, tracing, SQLx + SQLite.
   - A React + TypeScript + Vite frontend with Tailwind CSS.
   - A clean, responsive, minimal starter landing screen that demonstrates an API call and shows backend status; do not create a full admin dashboard yet.
   - `/api/hello`, `/health/live`, and `/health/ready` endpoints with appropriate response semantics.
   - An initial SQLite migration and a simple end-to-end database interaction, with tests.
   - Environment-based configuration with documented defaults and `.env.example`.
   - SPA routing fallback that does not swallow `/api/*` 404 responses.
2. Provide a canonical, multi-stage `Dockerfile` for Light. The production image should run a single Rust application process that serves the React build and the API. Store SQLite data on a mounted persistent volume, with a documented database path. Bind to `0.0.0.0:$PORT`.
3. Provide `compose.yaml` for local production-like deployment, with a persistent volume and a health check. Avoid a separate reverse-proxy container.
4. Add `docs/deployment/docker.md`, `docs/deployment/dokploy.md`, `docs/deployment/coolify.md`, and `docs/deployment/troubleshooting.md`. Explain actual settings users must configure (build context, Dockerfile path, port, environment variables, persistent volume, domain, health endpoint). If platform-specific behavior cannot be verified, mark it as unverified rather than guessing.
5. Add root `README.md` with project mission, architecture, quick start, feature status, and roadmap for Light and Advanced. Include `CONTRIBUTING.md`, `SECURITY.md`, `.gitignore`, and a proposed MIT `LICENSE` (do not invent a copyright holder; use a neutral placeholder if necessary and flag it).
6. Add GitHub Actions CI for Rust formatting, linting, tests, frontend typechecking/build, and a Docker build smoke test where practical. Pin or constrain actions and dependencies appropriately and generate lockfiles.
7. Document commands for local development, running migrations, tests, building the frontend, Docker builds, and backup/restore basics for SQLite. Explain that backups require consistency (SQLite backup API or safe equivalent).

## Engineering requirements
- Favor clarity and correctness over unnecessary abstractions.
- Keep dependencies lean and current. Use supported stable versions and lockfiles.
- Ensure SQLite WAL, foreign keys, busy timeout, and a small pool are configured thoughtfully.
- Provide structured logging and graceful shutdown.
- Use a non-root container runtime where feasible, with explicit writable volume permissions.
- Do not add authentication, RBAC, queues, Redis, metrics infrastructure, PostgreSQL, or an AI CLI yet. These are later milestones.
- Avoid misleading claims such as 'production-ready' until the relevant security, backup, and deployment tests exist.
- All text and documentation must be in English.

## Workflow
1. Inspect the repo and provide a brief plan.
2. Implement the smallest coherent working version.
3. Run formatting, linting, tests, frontend build, and Docker smoke tests when the environment supports them.
4. Fix issues found by those checks.
5. Summarize files changed, commands actually run, results, unresolved issues, and a suggested next PR.
6. Open a pull request if the environment supports it; otherwise provide a reviewable diff/commit.

## Definition of done
- A new contributor can clone the repository and run Light locally from the documented instructions.
- Docker builds and serves the React frontend and Rust API in one application container.
- SQLite data survives application container recreation when the documented volume is mounted.
- The health endpoints behave correctly and are suitable for container/platform checks.
- CI is configured and documentation clearly identifies verified vs. unverified deployment steps.
