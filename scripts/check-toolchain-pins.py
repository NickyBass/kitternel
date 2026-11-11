#!/usr/bin/env python3
"""Read-only offline consistency checks for the source template or a standalone app."""
import argparse
import json
from pathlib import Path
import re
import tomllib
from urllib.parse import parse_qs, urlsplit


VERSION = r"\d+\.\d+\.\d+"


def version(value, location, partial=False):
    pattern = r"v?\d+(?:\.\d+){0,2}" if partial else rf"v?{VERSION}"
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError(f"{location}: expected a stable numeric version, observed {value!r}")
    parts = tuple(map(int, value.removeprefix("v").split(".")))
    return parts + (0,) * (3 - len(parts))


def engine_allows(selected, expression):
    """Common stable npm comparator/OR, caret, tilde, wildcard and hyphen ranges.

    Unsupported syntax is explicit; this is not npm's dependency resolver.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("engines.node must contain a supported stable version range")
    alternatives = []
    for clause in expression.split("||"):
        clause = clause.strip()
        hyphen = re.fullmatch(r"(v?\d+(?:\.\d+){0,2})\s+-\s+(v?\d+(?:\.\d+){0,2})", clause)
        if hyphen:
            clause = f">={hyphen[1]} <={hyphen[2]}"
        clause = re.sub(r"(>=|<=|>|<|=|\^|~)\s+", r"\1", clause)
        terms = clause.split()
        if not terms:
            raise ValueError(f"Unsupported engines.node range: {expression!r}")
        matches = []
        for term in terms:
            if term in ("*", "x", "X"):
                matches.append(True)
                continue
            token = re.fullmatch(r"(>=|<=|>|<|=|\^|~)?v?(\d+(?:\.(?:\d+|[xX*])){0,2})", term)
            if not token:
                raise ValueError(f"Unsupported engines.node syntax {term!r}; use stable comparator ranges or extend the targeted checker")
            operator = token[1] or "="
            fields = token[2].split(".")
            wildcard = next((i for i, x in enumerate(fields) if x in ("x", "X", "*")), len(fields))
            if any(x not in ("x", "X", "*") for x in fields[wildcard:]):
                raise ValueError(f"Unsupported engines.node wildcard: {term!r}")
            precision = wildcard
            lower = tuple(map(int, fields[:precision])) + (0,) * (3 - precision)
            upper = list(lower)
            upper[precision - 1] += 1
            upper[precision:] = [0] * (3 - precision)
            upper = tuple(upper)
            if operator in ("^", "~"):
                index = (0 if precision == 1 else 1) if operator == "~" else (0 if lower[0] or precision == 1 else 1 if lower[1] or precision == 2 else 2)
                ceiling = list(lower)
                ceiling[index] += 1
                ceiling[index + 1:] = [0] * (2 - index)
                ok = lower <= selected < tuple(ceiling)
            elif operator == "=":
                ok = selected == lower if precision == 3 else lower <= selected < upper
            elif operator == ">=":
                ok = selected >= lower
            elif operator == "<":
                ok = selected < lower
            elif operator == ">":
                ok = selected > lower if precision == 3 else selected >= upper
            else:  # <= includes every patch/minor omitted from a partial bound.
                ok = selected <= lower if precision == 3 else selected < upper
            matches.append(ok)
        alternatives.append(all(matches))
    return any(alternatives)


def check(root):
    root = Path(root).resolve()
    project = root if (root / "backend/Cargo.toml").is_file() else root / "templates" / "light"
    errors, inventory = [], []

    def label(path):
        return path.relative_to(root).as_posix()

    def read(path):
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError(f"{label(path)}: cannot read required declaration ({type(error).__name__})") from error

    def json_file(path):
        try:
            return json.loads(read(path))
        except json.JSONDecodeError as error:
            raise ValueError(f"{label(path)}: invalid JSON at line {error.lineno}") from error

    def toml_file(path):
        try:
            return tomllib.loads(read(path))
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"{label(path)}: invalid TOML") from error

    def field(data, path, *keys):
        current = data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                raise ValueError(f"{label(path)}: missing required field {'.'.join(keys)}; restore the declaration or adapt the supported layout")
            current = current[key]
        return current

    def require(ok, paths, message):
        if not ok:
            errors.append(f"{' / '.join(label(p) for p in paths)}: {message}")

    def one(pattern, text, path, description):
        found = re.findall(pattern, text, re.M)
        if len(found) != 1:
            raise ValueError(f"{label(path)}: expected one {description}, observed {len(found)}; review the targeted extraction after layout changes")
        return found[0]

    toolchain_path = project / "backend/rust-toolchain.toml"
    cargo_path = project / "backend/Cargo.toml"
    cargo_lock_path = project / "backend/Cargo.lock"
    package_path = project / "frontend/package.json"
    npm_lock_path = project / "frontend/package-lock.json"
    node_path = project / "frontend/.node-version"
    tools_path = root / "scripts/security-tools.json"
    docker_path = project / "Dockerfile"
    ci_path = root / ".github/workflows/ci.yml"
    security_path = root / ".github/workflows/security.yml"
    installer_path = root / "scripts/install-security-tools.sh"
    guide_path = root / "SECURITY-SCANNING.md"
    if not guide_path.is_file():
        guide_path = root / "docs/development/SECURITY-SCANNING.md"

    selected_rust = field(toml_file(toolchain_path), toolchain_path, "toolchain", "channel")
    rust = version(selected_rust, label(toolchain_path))
    cargo = toml_file(cargo_path)
    cargo_lock = field(toml_file(cargo_lock_path), cargo_lock_path, "package")
    package = json_file(package_path)
    npm_lock = json_file(npm_lock_path)
    tools = json_file(tools_path)
    for key in ("name", "version"):
        field(cargo, cargo_path, "package", key)
        field(package, package_path, key)
    field(npm_lock, npm_lock_path, "packages", "")
    for key in ("rust-toolchain", "npm", "cargo-audit", "trivy"):
        field(tools, tools_path, key)
    node = version(read(node_path).strip(), label(node_path))
    docker, ci, security, installer = map(read, (docker_path, ci_path, security_path, installer_path))
    if "rust-version" in cargo["package"]:
        msrv = cargo["package"]["rust-version"]
        require(version(msrv, label(cargo_path), partial=True) <= rust, [cargo_path, toolchain_path],
                f"MSRV {msrv!r} must not exceed selected Rust {selected_rust!r}; review the compiler or supported minimum")
    docker_rust = one(rf"^FROM rust:({VERSION})[^\s]*", docker, docker_path, "Rust builder version")
    docker_node = one(rf"^FROM node:({VERSION})[^\s]*", docker, docker_path, "Node builder version")
    explicit_rust = one(rf"cargo \+({VERSION}) build", docker, docker_path, "explicit Cargo build toolchain")
    require(version(docker_rust, label(docker_path)) == rust and version(explicit_rust, label(docker_path)) == rust,
            [toolchain_path, docker_path], f"selected Rust {selected_rust!r}, Docker Rust {docker_rust!r}, cargo +{explicit_rust} must agree; update builder tag/digest and explicit command together")
    require(version(docker_node, label(docker_path)) == node, [node_path, docker_path],
            f"Node pin {read(node_path).strip()!r} must agree with Docker Node {docker_node!r}; review builder tag/digest")
    require(version(tools["rust-toolchain"], label(tools_path)) == rust, [toolchain_path, tools_path],
            f"security installer Rust {tools['rust-toolchain']!r} must agree with selected {selected_rust!r}")
    for key in ("npm", "cargo-audit", "trivy"):
        version(tools[key], f"{label(tools_path)} {key}")
    require(package.get("packageManager") == "npm@" + tools["npm"], [package_path, tools_path],
            f"packageManager {package.get('packageManager')!r} must select npm@{tools['npm']}; update npm metadata and installation together")
    for path, entry in ((package_path, package), (npm_lock_path, npm_lock["packages"][""])):
        constraint = entry.get("engines", {}).get("node")
        if constraint is not None:
            try:
                compatible = engine_allows(node, constraint)
            except ValueError as error:
                errors.append(f"{label(path)}: {error}")
                continue
            require(compatible, [node_path, path],
                    f"selected Node {read(node_path).strip()!r} is outside engines.node {constraint!r}; choose a compatible pin/range")
        elif path == package_path:
            require(False, [path], "engines.node is missing; declare the intended supported Node range")
    for entry in (npm_lock, npm_lock["packages"][""]):
        require(all(entry.get(k) == package[k] for k in ("name", "version")), [package_path, npm_lock_path],
                "npm lockfile package identity must agree with the manifest; regenerate/review the lockfile with the intended npm")
    require(any(p["name"] == cargo["package"]["name"] and p["version"] == cargo["package"]["version"] for p in cargo_lock),
            [cargo_path, cargo_lock_path], "local Cargo package identity/version must occur in Cargo.lock; resolve and review it deliberately")

    generation_path = root / ".github/workflows/generation.yml"
    rust_workflows = [(ci_path, ci), (security_path, security)]
    if generation_path.is_file():
        rust_workflows.append((generation_path, read(generation_path)))
    for path, workflow in rust_workflows:
        literals = re.findall(rf"(?:cargo \+|rustup toolchain install )({VERSION})", workflow)
        literals += re.findall(rf"^\s*toolchain=['\"]?({VERSION})['\"]?\s*$", workflow, re.M)
        for literal in literals:
            require(version(literal, label(path)) == rust, [path, toolchain_path], f"CI Rust override {literal!r} disagrees with {selected_rust!r}")
    for path, workflow in ((ci_path, ci), (security_path, security)):
        node_files = re.findall(r"node-version-file:\s*['\"]?([^\s'\"]+)", workflow)
        expected = (project / "frontend/.node-version").relative_to(root).as_posix()
        require([(root / value).resolve() for value in node_files] == [node_path.resolve()], [path, node_path],
                f"CI Node version-file observed {node_files!r}; expected [{expected!r}] so CI reads the selected pin")
        # Literal overrides must not silently bypass the version file/toolchain.
        for literal in re.findall(r"node-version:\s*['\"]?([^\s'\"]+)", workflow):
            require(version(literal, label(path)) == node, [path, node_path], f"CI Node override {literal!r} disagrees with the selected pin")
    require('rust-toolchain.toml' in ci and 'rustup toolchain install "$toolchain"' in ci,
            [ci_path, toolchain_path], "CI must derive its Rust installation from rust-toolchain.toml; review reader/install commands")
    npm_installs = re.findall(r"npm install --global npm@([^\s]+)", security)
    require(npm_installs == [tools["npm"]], [security_path, tools_path],
            f"security CI npm installs {npm_installs!r} must select [{tools['npm']!r}]")
    for mode in ("rust", "image"):
        require(f'sh scripts/install-security-tools.sh {mode} ' in security, [security_path, installer_path],
                f"security CI must use the manifest-driven {mode} installer; no independent scanner pin expected")
    snippets = (
        ('$script_dir/security-tools.json', "read scanner pins from security-tools.json"),
        ('toolchain=$(version rust-toolchain)', "read the security Rust toolchain"),
        ('--version "$(version cargo-audit)" --locked', f"install cargo-audit {tools['cargo-audit']} from the manifest with --locked"),
        ('trivy_version=$(version trivy)', f"select Trivy {tools['trivy']} from the manifest"),
        ('v${trivy_version}/trivy_${trivy_version}_Linux-64bit.tar.gz', "use the selected Trivy version in the download URL"),
        ('"$(version trivy-linux-amd64-sha256)"', "read the configured Trivy checksum"),
        ('sha256sum --check', "preserve Trivy SHA-256 verification"),
    )
    for snippet, relationship in snippets:
        require(snippet in installer, [installer_path, tools_path], f"installer must {relationship}; expected expression {snippet!r} not found (review intentional installer refactors)")
    checksum = tools.get("trivy-linux-amd64-sha256")
    require(isinstance(checksum, str) and bool(re.fullmatch(r"[a-fA-F0-9]{64}", checksum)), [tools_path],
            f"trivy-linux-amd64-sha256 must be a 64-hex SHA-256 string; observed type={type(checksum).__name__}, length={len(checksum) if isinstance(checksum, str) else 'not a string'}; verify the official release separately")
    intro = read(guide_path).split("## Local commands", 1)[0]
    for key, display in (("cargo-audit", "cargo-audit"), ("npm", "npm"), ("trivy", "Trivy")):
        documented = one(rf"\b{display} ({VERSION})", intro, guide_path, f"current {display} version in the scan-guide introduction")
        require(documented == tools[key], [guide_path, tools_path],
                f"scan guide declares {display} {documented}, manifest selects {tools[key]}; update the authoritative introduction")

    # Only current setup instructions, never dated maintenance snapshots.
    for filename in ("README.md", "CONTRIBUTING.md"):
        path = root / filename
        if not path.is_file():
            continue
        text = read(path)
        for pattern, expected, kind in (
            (rf"\bUse Rust ({VERSION})", rust, "Rust"),
            (rf"\b(?:Install Node\.js|Clippy, Node) ({VERSION})", node, "Node"),
        ):
            for claim in re.findall(pattern, text):
                require(version(claim, label(path)) == expected, [path, toolchain_path if kind == "Rust" else node_path],
                        f"current {kind} setup instruction {claim!r} must agree with the selected pin; update the instruction or link to the authoritative file")

    sqlx = cargo.get("dependencies", {}).get("sqlx")
    if isinstance(sqlx, dict) and "git" in sqlx:
        rev = sqlx.get("rev", "")
        require(isinstance(rev, str) and bool(re.fullmatch(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})", rev)), [cargo_path], "Git SQLx must use a full immutable revision; a future published dependency is allowed")
        matching = []
        for p in cargo_lock:
            if p["name"] != sqlx.get("package", "sqlx"):
                continue
            source = urlsplit(p.get("source", "").removeprefix("git+"))
            matching.append(source.fragment == rev and parse_qs(source.query).get("rev") == [rev]
                            and p.get("source", "").startswith("git+" + sqlx["git"] + "?"))
        require(any(matching), [cargo_path, cargo_lock_path], f"SQLx Git revision {rev!r} must match a lockfile source; resolve/review the intended dependency, not a different commit")
    elif isinstance(sqlx, str) or (isinstance(sqlx, dict) and "version" in sqlx and "path" not in sqlx):
        package_name = sqlx.get("package", "sqlx") if isinstance(sqlx, dict) else "sqlx"
        require(any(p["name"] == package_name and p.get("source", "").startswith("registry+") for p in cargo_lock),
                [cargo_path, cargo_lock_path], "registry SQLx declaration needs a registry lock entry; observed no matching source kind, resolve and review the intended dependency")
    inventory.append(f"Rust selected={selected_rust}; MSRV={cargo['package'].get('rust-version', 'not declared')}; Node={read(node_path).strip()}; npm={tools['npm']}")
    inventory.append(f"Scanners: cargo-audit={tools['cargo-audit']}; Trivy={tools['trivy']}; SHA-256 format only, authenticity not checked")
    inventory.append(f"SQLx declaration={'Git revision ' + str(sqlx.get('rev')) if isinstance(sqlx, dict) and 'git' in sqlx else 'published constraint'}; locked SQLite bindings={sorted({p['version'] for p in cargo_lock if p['name']=='libsqlite3-sys'})}")
    inventory.append(f"minimatch override={package.get('overrides', {}).get('minimatch', 'absent')}; locked versions={sorted({v['version'] for k,v in npm_lock['packages'].items() if k.endswith('node_modules/minimatch')})}")
    return errors, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Repository or standalone root (default: script's parent project)")
    args = parser.parse_args()
    try:
        errors, inventory = check(args.root)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"FAIL: cannot validate declarations: {error}; review the named file/required field and supported layout")
        return 1
    for item in inventory:
        print(item)
    for item in errors:
        print("FAIL: " + item)
    if not errors:
        print("PASS: offline pin relationships are consistent (not a vulnerability or upstream-integrity assessment)")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
