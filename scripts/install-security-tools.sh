#!/bin/sh
# Development/CI tooling only. No network scripts are evaluated.
set -eu
[ "$#" -eq 2 ] || { echo 'Usage: install-security-tools.sh rust|image PREFIX' >&2; exit 2; }
component=$1
prefix=$2
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
version() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$script_dir/security-tools.json" "$1"; }
mkdir -p "$prefix/bin"
case "$component" in
    rust)
        toolchain=$(version rust-toolchain)
        rustup toolchain install "$toolchain" --profile minimal
        cargo +"$toolchain" install cargo-audit --version "$(version cargo-audit)" --locked --root "$prefix"
        ;;
    image)
        [ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo 'Pinned Trivy download supports Linux/amd64 only; install the pinned release manually on other hosts.' >&2; exit 2; }
        temporary=$(mktemp -d)
        trap 'rm -rf "$temporary"' 0
        trap 'exit 2' HUP INT TERM
        trivy_version=$(version trivy)
        curl --fail --silent --show-error --location "https://github.com/aquasecurity/trivy/releases/download/v${trivy_version}/trivy_${trivy_version}_Linux-64bit.tar.gz" --output "$temporary/trivy.tar.gz"
        printf '%s  %s\n' "$(version trivy-linux-amd64-sha256)" "$temporary/trivy.tar.gz" | sha256sum --check
        tar -xzf "$temporary/trivy.tar.gz" -C "$prefix/bin" trivy
        ;;
    *) echo 'Expected rust or image' >&2; exit 2 ;;
esac
