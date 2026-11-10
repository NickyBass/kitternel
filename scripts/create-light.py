#!/usr/bin/env python3
"""Create a standalone Light application from explicitly selected tracked files."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
RUNNERS = (
    "backend-smoke.py", "browser-smoke.py", "docker-smoke.py", "sqlite-backup-smoke.py",
    "migration-build-smoke.py", "smoke_paths.py", "test-smoke-paths.py", "test-smoke-cleanup.py",
)
# Identity substitutions are limited to these known first-party text files.
IDENTITY_FILES = {
    ".github/workflows/ci.yml", "Dockerfile", "compose.yaml", ".env.example", "backend/Cargo.toml",
    "scripts/sqlite-backup.sh", "scripts/sqlite-restore.sh",
    "backend/src/main.rs", "backend/src/config.rs", "backend/migrations/0001_greeting.sql",
    *(f"backend/tests/{name}.rs" for name in ("database", "routes", "server", "static_files")),
    "frontend/index.html", "frontend/src/App.tsx",
    *(f"scripts/{name}" for name in RUNNERS),
}
RESERVED = set("as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while abstract become box do final macro override priv try typeof unsized virtual yield gen".lower().split())
RESERVED.update(("con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))))


def customize(relative, text, name):
    display = name.replace("-", " ").title()
    if relative == "Dockerfile":
        # The fixed non-root account is not an application identifier. Do not
        # collide with pre-existing OS accounts when the project is named root.
        text = text.replace("groupadd --gid 10001 kitternel", "groupadd --gid 10001 app")
        text = text.replace("--gid kitternel", "--gid app")
        text = text.replace("--shell /usr/sbin/nologin kitternel", "--shell /usr/sbin/nologin app")
        text = text.replace("-o kitternel -g kitternel", "-o app -g app")
    if relative in IDENTITY_FILES:
        # Whole identity tokens only; dependency names, routes, UIDs, SQL schema,
        # and security settings are not subject to arbitrary user substitutions.
        identities = {"kitternel_light": name.replace("-", "_"), "kitternel-light": name,
                      "Kitternel Light": display, "Kitternel": display, "kitternel": name}
        pattern = r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, identities)) + r")(?![A-Za-z0-9_])"
        text = re.sub(pattern, lambda match: identities[match[0]], text)

    if relative == "backend/Cargo.lock":
        old = 'name = "kitternel-light"\n'
        if text.count(old) != 1:
            raise ValueError("Expected exactly one template package in Cargo.lock")
        text = text.replace(old, f'name = "{name}"\n')
    if relative in ("frontend/package.json", "frontend/package-lock.json"):
        package = json.loads(text)
        package["name"] = f"{name}-frontend"
        if "packages" in package:
            package["packages"][""]["name"] = f"{name}-frontend"
        text = json.dumps(package, indent=2) + "\n"
    if relative.startswith("scripts/") or relative == ".github/workflows/ci.yml":
        text = text.replace("templates/light/", "").replace("../../../scripts/", "../scripts/")
    if relative == "scripts/docker-smoke.py":
        text = text.replace(f'.stdout.strip(), "{name}")', f'.stdout.strip(), "{name[:15]}")')
    if relative == "compose.yaml":
        text = f"name: {name}\n\n" + text
    if relative == ".github/workflows/ci.yml":
        text = text.replace("templates/light\n", ".\n")
    return text


def generate(name, destination):
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name) or len(name) > 32 or name in RESERVED:
        raise ValueError("Name must be 1–32 lowercase ASCII letters/digits with single internal hyphens, start with a letter, and not be a Rust keyword or reserved device name")
    manifest = tomllib.loads((ROOT / "templates/light/backend/Cargo.toml").read_text())
    crate_names = {dependency.replace("-", "_") for section in ("dependencies", "dev-dependencies")
                   for dependency in manifest.get(section, {})}
    if name.replace("-", "_") in crate_names | {"std", "core", "alloc", "test", "proc_macro"}:
        raise ValueError("Name conflicts with a Rust dependency or standard-library crate")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination must not already exist (including empty directories and symlinks)")
    parent = destination.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("Destination parent must be a directory")
    destination = parent / destination.name
    if destination.is_relative_to(ROOT.resolve()):
        raise ValueError("Destination must be outside the source repository")
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", "templates/light"],
                             check=True, capture_output=True).stdout.decode().split("\0")
    files = {path.removeprefix("templates/light/"): ROOT / path for path in tracked if path}
    files.update({f"scripts/{name}": ROOT / "scripts" / name for name in RUNNERS})
    files.update({name: ROOT / name for name in (".gitignore", ".gitattributes", "LICENSE")})
    files[".github/workflows/ci.yml"] = ROOT / ".github/workflows/ci.yml"
    with tempfile.TemporaryDirectory(prefix=".light-create-", dir=parent) as temporary:
        stage = Path(temporary)
        for relative, source in files.items():
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Expected an ordinary source file: {relative}")
            text = customize(relative, source.read_text(encoding="utf-8"), name)
            # Fail closed if upstream identities/layout drift beyond the known mapping.
            reference_check = text
            for identity in sorted((name, name.replace("-", "_"), name.replace("-", " ").title()), key=len, reverse=True):
                reference_check = reference_check.replace(identity, "PROJECT")
            if relative != "LICENSE" and re.search(r"kitternel|templates/light|\.\./\.\./\.\./scripts", reference_check, re.I):
                raise ValueError(f"Unmapped template reference in {relative}")
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            target.chmod(source.stat().st_mode & 0o777)
        for filename in ("README.md.in", "AGENTS.md.in", "CONTRIBUTING.md.in", "SECURITY.md.in"):
            source = ROOT / "scripts/project-files" / filename
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Expected an ordinary documentation template: {filename}")
            text = source.read_text().replace("@NAME@", name).replace("@DISPLAY@", name.replace("-", " ").title())
            (stage / source.stem).write_text(text, encoding="utf-8", newline="\n")
        # mkdir is the exclusive claim: never replace a concurrently created destination.
        destination.mkdir()
        try:
            for item in stage.iterdir():
                shutil.move(str(item), destination / item.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        result = generate(args.name, args.destination)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Project creation failed: {error}\n")
    print(f"Created {result}. Read README.md before building or deploying.")
