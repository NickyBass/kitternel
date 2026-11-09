# Light on Dokploy

Status: documentation-based configuration, not a verified Dokploy deployment. No Dokploy instance, platform credentials, domain, or certificate issuance was exercised. Field names may differ by installed version; confirm the rendered build/service settings before deployment.

Use an **Application** with Dockerfile build type, not a static-site build. Reuse the canonical Dockerfile; do not introduce a separate build for Dokploy.

| Setting | Required value |
| --- | --- |
| Repository/ref | Your reviewed Kitternel repository and immutable commit/release |
| Effective build context | `templates/light` |
| Dockerfile | `templates/light/Dockerfile`, or `Dockerfile` relative to that context; confirm the generated Docker build command |
| Docker Context Path | `templates/light` relative to the checked-out repository |
| Docker Build Stage | `runtime`, or leave unset to select the final stage |
| Application command | Keep image ENTRYPOINT `/app/kitternel-light` |
| Internal/domain target port | `8080` over HTTP |
| Persistent mount | Named local volume or dedicated local directory, target `/data` |
| Replicas | Exactly `1`, on the node holding the local database volume |
| Update and rollback order | `stop-first`, with parallelism `1`; verify no overlap on the same database |
| Container stop grace | At least `15` seconds for the default ten-second drain deadline |
| Domain/TLS | Operator-owned domain with DNS pointing at the Dokploy proxy; enable HTTPS and verify the certificate |

The official build documentation describes **Dockerfile Path**, **Docker Context Path**, and **Docker Build Stage**. Because path resolution can differ between platform versions, the invariant is the Docker command equivalent of `docker build -f templates/light/Dockerfile templates/light` from the repository root. A log showing the repository root as the build context will fail the Dockerfile's `COPY backend/` and `COPY frontend/` paths; fix the platform context instead of creating a divergent Dockerfile.

Set runtime environment variables in Dokploy:

```dotenv
PORT=8080
SQLITE_PATH=/data/kitternel.db
FRONTEND_DIR=/app/public
LOG_LEVEL=info
SHUTDOWN_TIMEOUT_SECS=10
HTTP_HEADER_TIMEOUT_SECS=10
MAX_CONNECTIONS=128
```

These are runtime values, not frontend build variables or secrets. The foundation requires no application credentials. Build secrets, if later required, must use the platform's supported BuildKit mechanism rather than Docker build arguments.

## Storage, health, and deployment sequence

Create persistent storage outside the source checkout. Preserve the entire `/data` directory and verify ownership/permissions for UID/GID 10001. Empty Docker volumes initialized from the image can inherit permissions; populated volumes and bind mounts require explicit verification. Do not place the WAL database on network storage or allow scheduling onto another node with an empty local volume. Never use the repository working directory as the database mount: Dokploy may replace it during redeploy.

Dokploy Applications expose Swarm update, rollback, placement, and health controls. This guide does not introduce or require additional orchestration infrastructure; it describes settings on an existing Dokploy instance. Select one replica and a stable node. Set both update and rollback order to `stop-first`; do not copy the platform's general zero-downtime/start-first examples for this SQLite starter. Inspect actual task/container overlap during a staging redeploy.

Keep the image's health check or configure an equivalent GET of `http://127.0.0.1:8080/health/ready`, with a two-second HTTP deadline, three-second check timeout, 30-second interval, 15-second startup grace, and three retries. The image includes curl. If a separate liveness check exists, use `/health/live`. Confirm the effective health command and restart/traffic behavior on the installed version; Docker health status alone is not an availability guarantee.

Route the domain root `/` to the app's internal port 8080. The frontend/API use the same origin; no CORS override or separate frontend domain is needed. Do not publish a redundant public host port. TLS terminates at Dokploy's proxy; the Rust process remains HTTP internally.

Before real traffic: verify startup/migration logs, internal health, the HTTPS root page and greeting, API/health 404s, and retained data after container replacement. Run a [backup/restore drill](backup-restore.md) using a separate volume and the matching image. Persistent-volume archive features alone do not prove SQLite consistency. Preview deployments must use isolated databases, never the production mount. Configure rollback only for schema-compatible images; an image rollback does not undo database changes.

## Sources and verification boundary

Consulted the official [build settings](https://github.com/Dokploy/website/blob/29e9c02c5e806450b1cfb6d8a2a330728f2193e0/apps/docs/content/docs/core/applications/build-type.mdx), [advanced settings](https://github.com/Dokploy/website/blob/29e9c02c5e806450b1cfb6d8a2a330728f2193e0/apps/docs/content/docs/core/applications/advanced.mdx), and [volume troubleshooting](https://github.com/Dokploy/website/blob/29e9c02c5e806450b1cfb6d8a2a330728f2193e0/apps/docs/content/docs/core/troubleshooting/volumes-mounts.mdx). These are documentation sources, not a tested platform version. HTTPS, platform routing, scheduling, permissions, stop-first behavior, and replacement persistence remain to be verified on the target instance. See [troubleshooting](troubleshooting.md).
