# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
FROM node:24.22.1-bookworm-slim@sha256:be8204d4bd327363357f532187b752ff62759c31bedf98e9e18fc08c9cbd605c AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    set -eu; if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM rust:1.99.1-slim-bookworm@sha256:f2c004e3d2d8b547e8cf7ffbc29205385f4e71d23e53e4e383065db5e9f822cd AS backend
WORKDIR /build/backend
COPY backend/ ./
RUN --mount=type=secret,id=proxy_ca \
    set -eu; if [ -f /run/secrets/proxy_ca ]; then export CARGO_HTTP_CAINFO=/run/secrets/proxy_ca; fi; \
    CARGO_PROFILE_RELEASE_STRIP=symbols cargo +1.99.1 build --release --locked --jobs 4

FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS runtime
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends ca-certificates curl sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 kitternel \
    && useradd --uid 10001 --gid kitternel --no-create-home --shell /usr/sbin/nologin kitternel \
    && install -d -o kitternel -g kitternel -m 0750 /data /backups
WORKDIR /app
COPY --from=backend /build/backend/target/release/kitternel-light /app/kitternel-light
COPY --from=frontend /build/frontend/dist /app/public
COPY --chmod=755 scripts/sqlite-backup.sh /app/sqlite-backup
COPY --chmod=755 scripts/sqlite-restore.sh /app/sqlite-restore
ENV PORT=8080 LOG_LEVEL=info SHUTDOWN_TIMEOUT_SECS=10 SQLITE_PATH=/data/kitternel.db FRONTEND_DIR=/app/public
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD curl --noproxy 127.0.0.1 --fail --silent --show-error --max-time 2 "http://127.0.0.1:${PORT}/health/ready" || exit 1
ENTRYPOINT ["/app/kitternel-light"]
