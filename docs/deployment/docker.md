# Light with Docker

This guide covers one application container on one Linux host. PostgreSQL, multiple app replicas, and platform-specific routing are outside this milestone. Run these commands from the repository root unless noted otherwise.

## Build

Requirements: Docker with BuildKit and Docker Compose v2. The canonical build context is `templates/light`, and the Dockerfile is `templates/light/Dockerfile`.

```sh
docker build -t kitternel-light:local templates/light
```

The Node and Rust builder stages use committed lockfiles and pinned toolchains/base image digests. The runtime contains the stripped Rust binary, compiled frontend, CA certificates, curl for health checks, and sqlite3 for trusted operator diagnostics. Node, npm, Cargo, and application source are absent from the runtime. Debian packages receive repository updates at build time; this is not a bit-for-bit reproducible package snapshot. Review and refresh image digests and package updates deliberately, then rerun smoke tests.

If the build runs behind the Codex Cloud TLS proxy, provide its existing trusted CA as an optional BuildKit secret:

```sh
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" \
  -t kitternel-light:local templates/light
```

The optional CA is mounted only for networked npm/Cargo steps, never copied into the image. Ordinary builds do not require that secret. Keep TLS and package-signature verification enabled. The build uses four Cargo jobs to bound resource use; Docker layer caching reuses unchanged build outputs.

## Start with Compose

```sh
cd templates/light
docker compose up -d --build
docker compose ps
```

The frontend and API are served on the host's loopback port 8080. Verify locally:

```sh
curl --fail http://127.0.0.1:8080/health/live
curl --fail http://127.0.0.1:8080/health/ready
curl --fail http://127.0.0.1:8080/api/hello
```

Compose binds only `127.0.0.1` by default; public HTTPS/domain routing belongs to a separately configured trusted reverse proxy. An optional `HOST_PORT=8081 docker compose up -d` changes the host port without changing the internal app port. Compose does not include a reverse-proxy container or supply TLS/authentication.

For a proxy-CA build, first build the image with the explicit secret command above, then use `docker compose up -d --no-build`. The Compose file deliberately has no dependency on a cloud-specific secret path.

The image binds `0.0.0.0:$PORT` (default 8080). `HTTP_HEADER_TIMEOUT_SECS` defaults to 10 (range 1–60), and `MAX_CONNECTIONS` defaults to 128 (range 1–4096). The HTTP/1 listener uses an explicit header timer, at most 64 headers, and a 32 KiB read buffer; at capacity, new connections wait in the operating system backlog until an active slot is released. These controls complement proxy limits and are not a DoS-resistance guarantee. Compose fixes the internal port at 8080; changing it requires updating both the environment and port mapping. Runtime paths are `/app/public` for frontend files and `/data/kitternel.db` for SQLite.

## Plain Docker

```sh
docker volume create kitternel-light-data
docker run -d --name kitternel-light \
  --read-only --tmpfs /tmp:size=32m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --stop-timeout 15 \
  -p 127.0.0.1:8080:8080 \
  --mount source=kitternel-light-data,target=/data \
  kitternel-light:local
```

Always mount a named persistent volume or an explicitly managed local bind directory at `/data`. The image does not declare an anonymous volume, making volume names and lifecycle explicit. Running without a mount on a writable container layer stores ephemeral data; it is not a supported persistent deployment. Running the documented read-only command without `/data` mounted fails during database initialization.

## Storage and permissions

The runtime UID/GID is `10001:10001`. `/data` in the image is owned by that user, mode 0750. An empty Docker named volume initialized from the image inherits those directory permissions. Populated volumes and bind mounts retain their permissions; verify them instead of assuming they were initialized by this image. On the host, provision a dedicated bind directory owned by UID/GID 10001 with restrictive permissions before deployment. Do not use chmod 777 or recursively change unrelated host directories. SELinux hosts may need an appropriate dedicated-directory label; that platform configuration has not been verified here.

Persist the entire directory, including SQLite WAL/SHM files. The root filesystem is read-only in Compose, with a bounded temporary `/tmp` mount and the explicit writable database volume. Use a local filesystem compatible with SQLite WAL; do not share a WAL database across hosts or use a network filesystem. Keep a single application replica and serialize deployments. Allow a maintenance window; no zero-downtime behavior is promised.

Only ordinary SQLite file paths are supported; `:memory:` and SQLite `file:` URIs are rejected before storage is opened. Migrations run before the listener starts, and existing seed data is not overwritten on restart. Back up before schema changes. Restarting an older image does not reverse a migration. Use SQLite's online backup API or another consistent method; copying only a live `.db` file is unsafe. Tested backup/restore procedures and platform deployment guides belong to milestone 5.

```sh
docker compose stop
# Reuses the named volume when started again.
docker compose up -d --no-build
# Removes the containers/network while preserving database volumes.
docker compose down
```

Do not run `docker compose down --volumes` or remove the named data volume unless data deletion is intentional.

## Health and shutdown

The image's health check calls `/health/ready` using curl on the configured internal port: interval 30 seconds, timeout 3 seconds, startup grace 15 seconds, three retries, and a two-second client deadline. Readiness queries SQLite with a one-second deadline. `/health/live` checks only whether HTTP can respond. A platform with separate liveness and readiness checks should use them accordingly.

Docker health status does not itself restart an unhealthy container. Compose's `unless-stopped` policy restarts exited processes; an orchestrator's unhealthy-container policy must be configured and verified separately. Slow migrations may require adjusting the startup grace period without disabling readiness checks.

The Rust binary is PID 1 and receives SIGTERM directly. It drains HTTP requests for up to ten seconds by default and closes the pool; Compose allows 15 seconds before SIGKILL. If `SHUTDOWN_TIMEOUT_SECS` changes, increase the container/platform grace period accordingly. Inspect `docker compose logs app` and `docker inspect` health/state output for startup or shutdown failures. Database initialization failures emit safe stage/category fields, a migration version when available, and a numeric SQLite error code. Consult those fields instead of enabling raw SQL/error-text logging. Never repair a migration failure by deleting production data.

## Validation

Build the image, then run the isolated smoke suite from the repository root:

```sh
python3 scripts/docker-smoke.py --image kitternel-light:local
```

The suite owns uniquely named disposable containers and volumes. It tests frontend assets/API/health responses, a non-default port, the bundled Docker health check, non-root/read-only operation, graceful SIGTERM, persisted data after recreation, and clear failures for missing/read-only storage or incompatible volume permissions. It never uses the Compose deployment's data volume and removes only its own test resources.

Validation in this task used Docker 29.9.2 and Compose 2.40.3 on Linux/amd64. The image built successfully with the cloud proxy CA supplied, and a subsequent build reused the Docker layer cache. All five Docker/Compose smoke tests passed; test resources were removed. The same commands are configured in GitHub Actions, but that workflow has not been executed remotely for these changes. ARM builds, Dokploy, Coolify, backup/restore, and production deployment have not been verified in this milestone.
