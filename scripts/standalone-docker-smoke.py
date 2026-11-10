#!/usr/bin/env python3
"""Generate, build without cache, and verify an independent disposable application."""
import argparse
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
LABEL = "io.starter.smoke-run"


def run(phase, arguments, cwd, environment, timeout=120):
    print(f"[{phase}]", flush=True)
    try:
        process = subprocess.Popen(arguments, cwd=cwd, env=environment,
                                   start_new_session=os.name == "posix")
        try:
            returncode = process.wait(timeout=timeout)
        except BaseException:
            # Stop child suites and their Docker CLI descendants before inventorying
            # engine resources; otherwise an orphan could create resources afterward.
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()
            raise
        if returncode:
            raise subprocess.CalledProcessError(returncode, arguments)
        return returncode
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"{phase} failed ({type(error).__name__}); inspect the preceding output. "
                           "Check Docker/Compose availability, registry access, storage permissions, and disk space.") from error


def validate_files(project):
    required = ("Dockerfile", "compose.yaml", "README.md", "AGENTS.md", "LICENSE", ".dockerignore",
                "backend/Cargo.toml", "backend/Cargo.lock", "backend/src/main.rs",
                "backend/migrations/0001_greeting.sql", "frontend/package-lock.json",
                ".github/workflows/ci.yml", "scripts/docker-smoke.py", "scripts/sqlite-backup-smoke.py")
    for relative in required:
        if not (project / relative).is_file():
            raise RuntimeError(f"Generated project is missing {relative}")
    for path in project.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"Generated project contains a symlink: {path.relative_to(project)}")
        database_file = path.suffix in (".db", ".sqlite", ".sqlite3") or any(
            suffix in path.name for suffix in (".db-", ".sqlite-", ".sqlite3-"))
        local_env = path.name.startswith(".env") and path.name != ".env.example"
        if database_file or local_env or path.name in ("target", "node_modules", "dist", ".git", "data"):
            raise RuntimeError(f"Generated project contains an existing artifact: {path.relative_to(project)}")
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if str(ROOT) in text or "templates/light" in text or "../../../scripts" in text:
                raise RuntimeError(f"Generated file depends on source layout: {path.relative_to(project)}")


def docker_output(*arguments):
    return subprocess.run(["docker", *arguments], check=True, text=True,
                          capture_output=True, timeout=90).stdout.splitlines()


def resources(name):
    # Prefix includes a separator so similarly named projects cannot match.
    prefix = name + "-smoke-"
    containers = {line.split("\t")[0] for line in docker_output("ps", "--all", "--format", "{{.ID}}\t{{.Names}}")
                  if line.split("\t")[1].startswith(prefix)}
    containers.update(docker_output("ps", "--all", "--quiet", "--filter", f"label={LABEL}={name}"))
    volumes = {line for line in docker_output("volume", "ls", "--format", "{{.Name}}") if line.startswith(prefix)}
    networks = {line.split("\t")[0] for line in docker_output("network", "ls", "--format", "{{.ID}}\t{{.Name}}")
                if line.split("\t")[1].startswith(prefix)}
    return containers, volumes, networks


def cleanup(name, image):
    failures = []
    try:
        remaining = resources(name)
    except (OSError, subprocess.SubprocessError) as error:
        remaining = (set(), set(), set())
        failures.append(f"Cannot inventory temporary resources: {type(error).__name__}")
    if any(remaining):
        failures.append("Smoke suites left temporary resources; attempted scoped fallback removal")
    for kind, names in zip(("container", "volume", "network"), remaining):
        for resource in sorted(names):
            arguments = ["rm", "--force", resource] if kind == "container" else [kind, "rm", resource]
            try:
                docker_output(*arguments)
            except (OSError, subprocess.SubprocessError) as error:
                failures.append(f"Cannot remove {kind} {resource}: {type(error).__name__}")
    try:
        if docker_output("image", "ls", "--quiet", "--filter", f"reference={image}"):
            docker_output("image", "rm", image)
    except (OSError, subprocess.SubprocessError) as error:
        failures.append(f"Cannot remove validation image: {type(error).__name__}")
    try:
        if any(resources(name)):
            failures.append("Temporary Docker resources still exist after fallback cleanup")
    except (OSError, subprocess.SubprocessError) as error:
        failures.append(f"Cannot verify cleanup: {type(error).__name__}")
    if failures:
        raise RuntimeError("; ".join(failures))
    print("[cleanup] No temporary containers, volumes, or networks remain; image tag removed.", flush=True)


def build_command(image, proxy_ca=None):
    command = ["docker", "build", "--no-cache", "--progress=plain", "--tag", image]
    if proxy_ca:
        command += ["--secret", f"id=proxy_ca,src={proxy_ca}"]
    return [*command, "."]


def validate(proxy_ca=None):
    name = "light-e2e-" + uuid.uuid4().hex[:12]
    image = name + ":validation"
    print(f"Validation project: {name}; image: {image}", flush=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")}
    environment.pop("HOST_PORT", None)
    environment["SMOKE_RUN_ID"] = name
    spec = importlib.util.spec_from_file_location("create_light", ROOT / "scripts/create-light.py")
    creator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(creator)
    with tempfile.TemporaryDirectory(prefix="light-standalone-") as temporary:
        project = creator.generate(name, Path(temporary) / "application")
        validate_files(project)
        error = None
        try:
            run("Docker preflight", ["docker", "info", "--format", "{{.ServerVersion}}"], project, environment)
            run("Clean generated image build", build_command(image, proxy_ca), project, environment, timeout=1200)
            run("Generated Compose configuration", ["docker", "compose", "config", "--quiet"], project, environment)
            for script in ("test-smoke-cleanup.py", "test-smoke-paths.py", "docker-smoke.py", "sqlite-backup-smoke.py"):
                arguments = [sys.executable, str(project / "scripts" / script)]
                if script in ("docker-smoke.py", "sqlite-backup-smoke.py"):
                    arguments += ["--image", image]
                run(f"Generated {script}", [*arguments, "-v"], project, environment, timeout=600)
        except BaseException as failure:
            error = failure
            raise
        finally:
            try:
                cleanup(name, image)
            except (RuntimeError, OSError, subprocess.SubprocessError) as failure:
                if error is not None:
                    raise RuntimeError(f"{error}; cleanup also failed: {failure}") from error
                raise
    print("Independent generated Docker validation passed.", flush=True)


def interrupted(_number, _frame):
    raise KeyboardInterrupt("Validation interrupted; attempting scoped cleanup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy-ca", type=Path, help="Optional trusted CA file supplied only as a BuildKit secret")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    try:
        ca = args.proxy_ca.resolve(strict=True) if args.proxy_ca else None
        if ca and not ca.is_file():
            raise ValueError("--proxy-ca must name an existing trusted CA file")
        validate(ca)
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        parser.exit(1, f"Standalone validation failed: {error}\n")
