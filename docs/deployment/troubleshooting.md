# Light deployment troubleshooting

Start with the exact image/commit, runtime configuration names, logs, health result, and actual storage mount. Inspect credential presence only; do not dump process environments or credential files. The guides distinguish a local Docker check from verified behavior on Dokploy/Coolify.

| Symptom | Focused diagnosis and correction |
| --- | --- |
| Docker `COPY backend/` or `COPY frontend/` fails | Effective context must be `templates/light`. Check the platform-generated build command and canonical Dockerfile path; do not create a second Dockerfile. |
| `FRONTEND_DIR must contain a built index.html` | Native quick start requires `npm ci` and `npm run build` before backend startup. In the image, assets must be `/app/public`; do not point at Vite source or mount over that directory. |
| `SQLITE_PATH` configuration rejected | Use an ordinary file path, `/data/kitternel.db` in the image. Empty paths, `:memory:`, and `file:` SQLite URIs are intentionally rejected. |
| Database `storage`/`connection` error | Inspect the `/data` mount, UID/GID 10001 permissions, read-only flags, free space, and local filesystem. The root filesystem should be read-only but `/data` must be writable. Do not use chmod 777 or remove the database. |
| `checksum_mismatch` or `missing_migration` | Match the database with its known image/migration history. Restore an edited applied migration in source control or use a compatible release. Do not edit checksum rows or reset production data to make startup pass. |
| `execution_failed` during migration | Use the logged migration version and numeric SQLite code. Reproduce safely on a consistent backup/fresh test volume, review SQL/schema compatibility, and correct the migration in a separate reviewed change. Public errors intentionally omit raw SQL and paths. |
| Data resets after redeploy | Confirm actual `/data` mount name/path and stable node/project identity. An empty replacement volume or container writable layer is not the old database. Stop further writes and investigate; restore from a verified snapshot to a new volume. |
| `database is locked` / repeated 503 | Check for overlapping app instances, long external transactions, incompatible filesystem/locking, pool saturation, or disk failure. Keep one app instance; readiness times out independently after one second. Do not remove timeouts or disable WAL/foreign keys as a blanket fix. |
| App is healthy internally, public domain fails | Verify internal port 8080, proxy network/target, DNS, certificate, and platform health/routing rules. The app speaks HTTP internally; HTTPS belongs to the trusted proxy. Platform behavior is unverified until tested on the target instance. |
| Health is unhealthy but process runs | Inspect effective curl command, PORT, startup grace, and readiness response. Docker health does not itself restart a process; platform restart policy is separate. `/health/live` may be 200 while the database is unavailable. |
| HTTP 408 or headers rejected | `HTTP_HEADER_TIMEOUT_SECS` defaults to 10; headers are limited to 64 and a 32 KiB buffer. Examine legitimate client/proxy header sizes before changing limits. Do not remove transport limits globally. |
| Requests queue under load | `MAX_CONNECTIONS` bounds active transports; SQLite permits one writer. Measure the actual workload, query duration, CPU/memory/disk, and proxy timeouts. A larger pool or more replicas is not an automatic SQLite scaling solution. |
| SIGKILL / exit 137 on shutdown | Ensure the binary receives SIGTERM directly and container grace exceeds `SHUTDOWN_TIMEOUT_SECS`. Compose uses 15 seconds for a ten-second drain. Inspect memory limits/OOM state separately; 137 alone does not prove an OOM kill. |
| Backup helper fails | Verify source volume/path, backup mount ownership/free space, safe unique filename, and SQLite integrity/foreign keys. A partial or rejected backup is not a successful recovery point. Export only finalized snapshots. |
| Restore helper refuses a target | Existing database/sidecars are a protection against overwrite. Use a new volume and preserve the old one. A corrupt source must be replaced with a trusted consistent snapshot, not forced into a live database. |
| Docker build HTTPS fails in cloud | Use the documented optional BuildKit proxy CA secret. Preserve TLS verification and inherited proxy settings; an explicit policy denial requires environment configuration rather than bypassing the proxy. |
| Browser cannot reach cloud localhost | The service is on the cloud machine. Use a client-supported preview if one exists, or the isolated browser test/screenshot workflow. Do not assume a Desktop panel or public URL is available. |

## Safe inspection

From `templates/light`:

```sh
docker compose ps
docker compose logs --tail 100 app
kitternel_container=$(docker compose ps -q app)
docker inspect "$kitternel_container" --format '{{json .State.Health}}'
docker inspect "$kitternel_container" --format '{{json .Mounts}}'
docker compose exec -T app id
docker compose exec -T app curl --noproxy 127.0.0.1 --fail --silent http://127.0.0.1:8080/health/ready
```

Do not paste private mount paths, application data, or platform credentials into public issue reports. For a minimal bug report, include versions/commit, sanitized diagnostic stage/category, steps using disposable storage, expected/actual behavior, and checks actually run. Use [SECURITY.md](../../SECURITY.md) for sensitive findings.

## Evidence boundaries

A passing formatter/typecheck is not an application smoke test. An open port or container PID is not proof of readiness. A volume listing is not proof of persistence. A snapshot file is not proof of restorability. Use the project's HTTP, container-recreation, and backup/restore tests, then perform the platform-specific validation steps on the target instance before claiming deployment success.
