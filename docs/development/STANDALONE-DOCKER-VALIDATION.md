# Independent generated Docker validation

From the source repository root, with Python 3.11+, Git, a reachable Docker daemon, BuildKit, and Compose v2:

```sh
python3 scripts/standalone-docker-smoke.py
```

The host needs no Rust, Node, npm packages, application database, or compiled frontend. Internet access to the pinned image/package registries is needed for the uncached build. In a managed TLS-proxy environment, pass the existing trusted public CA without disabling TLS:

```sh
python3 scripts/standalone-docker-smoke.py --proxy-ca "$CODEX_PROXY_CERT"
```

The certificate is supplied only as the canonical Dockerfile's `proxy_ca` BuildKit secret. The script does not print environment variables or read deployment databases. It uses the Docker endpoint/context selected by your normal CLI configuration; verify that you are connected to the intended test daemon.

## What is verified

1. Generate a uniquely named application in a temporary directory outside the source checkout. Validate required files, absence of symlinks, build/data directories, and source-layout references.
2. Run `docker build --no-cache --progress=plain` with only the generated directory as context and a unique image tag. No source binaries, node_modules, frontend dist, application image layers, database, or host build caches are copied or mounted. Pinned base images may already exist locally.
3. Validate the generated Compose configuration.
4. Execute the generated project's own path/cleanup regressions and Docker/backup suites from its root, using only the freshly built image.
5. Confirm actual Compose startup, readiness, applied migration metadata, non-root/read-only operation, frontend HTML/assets and API/health behavior, custom internal port, graceful shutdown, and data retention across plain-Docker and Compose container recreation. Compose recreation retains a deliberately changed greeting and uses a new container ID.
6. Exercise live WAL snapshot/export, integrity and migration checks, standalone snapshot reads, restore to a separate named volume, application reads from both source and restored databases, and refusal of unsafe/corrupt/occupied recovery inputs.
7. Verify that the suites removed every temporary container, volume, and network, remove the unique image tag, and remove the temporary generated directory.

The five Docker tests include the expanded Compose lifecycle test. The six backup runner tests include four Docker recovery tests and two isolated cleanup simulations. The generated path and cleanup regression suites have five tests each.

## Isolation, failures, and cleanup

Each invocation creates an application name `light-e2e-<random-id>` and a matching unique image tag. Each fixture adds another unique suffix. Compose is explicitly given that fixture's project name, an available loopback port, the generated Compose file, and an override selecting the newly built image. Volumes are fresh and belong only to that fixture. Inherited Compose settings and HOST_PORT are not reused.

`SMOKE_RUN_ID` labels Docker run/create containers, including unnamed helper containers. The final inventory selects only that exact label and the generated fixture-name prefix (including its separator). Fallback cleanup never uses global prune or deployment volume names. A resource left by a suite fails validation even if fallback removal succeeds. Removal errors are aggregated and the original test/build error is retained when cleanup also fails. Commands have deadlines and errors identify the failed phase.

On Unix, interrupted/timed-out child commands and their CLI descendants are stopped before fallback cleanup. SIGINT/SIGTERM trigger cleanup. SIGKILL, daemon/host loss, or a forcibly cancelled CI runner cannot guarantee cleanup; the script reports inventory/removal failures when it can. Record the printed unique project/image identity when diagnosing interrupted runs. Do not delete resources belonging to another invocation. Base images and Docker build cache are retained; no broad cache pruning is performed.

Focused failure/isolation regressions require no Docker:

```sh
python3 scripts/test-standalone-docker.py -v
```

CI runs these tests in `.github/workflows/generation.yml`, then a separate 30-minute job runs the full independent uncached validation. That source-repository workflow is not copied into generated apps: generated apps retain their own canonical application CI, without depending on the original generator.

## Evidence boundary

A passing run verifies the printed generated application on that Docker host and architecture. It does not establish production capacity, TLS routing, native Windows/ARM behavior, off-host encrypted recovery, GitHub CI success, browser rendering, or any platform deployment. Consult the [roadmap](DOCKER-FIRST-ROADMAP.md) for the actual recorded run, not just the configured commands.
