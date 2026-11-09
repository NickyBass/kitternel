# Light on Coolify

Status: documentation-based configuration, not a verified Coolify deployment. No Coolify instance, platform credentials, DNS/TLS issuance, or rolling-update behavior was exercised. Confirm field names and generated settings on the installed version.

Create a Git-backed application with the **Dockerfile** build pack. Keep the repository-owned canonical Dockerfile; neither the static-site pack nor a Dockerfile entered without Git supplies the required source context.

| Setting | Required value |
| --- | --- |
| Repository/ref | Your reviewed Kitternel repository and immutable commit/release |
| Base Directory | `/templates/light` (effective build context: `templates/light`) |
| Dockerfile Location | `/Dockerfile`, relative to Base Directory |
| Build stage, if configured | `runtime`, or the default final stage |
| Ports Exposes | `8080` |
| Ports Mappings | None needed for platform proxy routing |
| Command | Preserve `/app/kitternel-light` ENTRYPOINT |
| Persistent Storage | Volume Mount or dedicated Directory Mount, Destination Path `/data` |
| Replicas/destination | One application instance on the server holding the local volume |
| Container naming | **Consistent name (no rolling updates)**, or the installed version's documented stop-first equivalent |
| Stop Grace Period | `15` seconds or longer than the configured drain deadline |
| Domain | HTTPS URL on an operator-owned domain, routed to internal HTTP port `8080` |

Verify that the generated build is equivalent to `docker build -f templates/light/Dockerfile templates/light`. The frontend and Rust API are built into one image; there is no separate publish directory, Vite service, or production Node process.

Set runtime environment values:

```dotenv
PORT=8080
SQLITE_PATH=/data/kitternel.db
FRONTEND_DIR=/app/public
LOG_LEVEL=info
SHUTDOWN_TIMEOUT_SECS=10
HTTP_HEADER_TIMEOUT_SECS=10
MAX_CONNECTIONS=128
```

Do not mark these as frontend build variables. The foundation requires no application credential. Keep later secrets in supported secure runtime bindings and out of build arguments/repository files.

## Storage, health, and redeploys

Add persistent storage before the first deployment and verify writes as UID/GID 10001. Mount the entire `/data` directory, not just its `.db` file. Record the actual volume name/server path for backup and recovery. Do not use a clone/build directory or a network filesystem for SQLite WAL. Keep the application pinned to the local storage server; deploying it on another server does not move its data automatically. Preview instances require separate volumes.

The official health guide says non-Compose Dockerfile applications use a detected image `HEALTHCHECK` instead of adding the dashboard check. This image supplies that command and curl. Confirm the effective check targets `/health/ready` on internal port 8080, not `/` or the proxy's external HTTPS port. Retain a suitable startup grace period for migrations. Where separate liveness is supported, use `/health/live`. Verify actual routing of unhealthy containers on your selected proxy; do not infer it from an image health result.

Coolify's documented rolling path can start a replacement before stopping the old container. This starter requires serialized replacement on the same SQLite volume. Configure **Consistent name (no rolling updates)** where available and set **Advanced > Operations > Stop Grace Period (seconds)** to at least 15. The docs identify consistent naming as a condition that prevents rolling overlap. If the installed version cannot provide stop-first behavior, stop the existing application explicitly before deploying its replacement. Expect an interruption; do not claim zero downtime. Confirm ordering in deployment logs and actual container state.

Set DNS for the operator-owned domain, enable platform-managed HTTPS, and route the domain root to the internal app port 8080. The SPA and API share the same origin. Do not enable permissive CORS or treat forwarded headers as trusted application identity.

Before real traffic, verify image build context, migration logs, internal health, valid public TLS, landing-page greeting, and data retained after redeploy. Use the [backup/restore drill](backup-restore.md) on a separate volume. A platform volume archive is not automatically a consistent SQLite backup. Preserve the old volume during recovery and use an image compatible with the snapshot's migration history.

## Sources and verification boundary

Consulted the official [Dockerfile build guide](https://github.com/coollabsio/documentation-coolify/blob/e80b8f40b2e9a53022f1181c1089b04b2d4ebe69/content/docs/applications/builds/dockerfile.mdx), [storage guide](https://github.com/coollabsio/documentation-coolify/blob/e80b8f40b2e9a53022f1181c1089b04b2d4ebe69/content/docs/applications/configuration/persistent-storage.mdx), [health checks](https://github.com/coollabsio/documentation-coolify/blob/e80b8f40b2e9a53022f1181c1089b04b2d4ebe69/content/docs/applications/configuration/health-checks.mdx), and [rolling updates](https://github.com/coollabsio/documentation-coolify/blob/e80b8f40b2e9a53022f1181c1089b04b2d4ebe69/content/docs/applications/deployments/rolling-updates.mdx). They document configuration, not an instance tested by this project. Actual platform deployment, HTTPS routing, stop-first ordering, volume permissions, and persistence remain unverified until exercised on the target version. See [troubleshooting](troubleshooting.md).
