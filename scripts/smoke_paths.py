"""Resolve build artifacts using Cargo's own target-directory rules."""
import json
import os
from pathlib import Path
import subprocess


def backend_binary(backend):
    # Keep the caller's cwd: Cargo resolves relative CARGO_TARGET_DIR against it.
    metadata = subprocess.run(
        ["cargo", "metadata", "--offline", "--no-deps", "--format-version", "1",
         "--manifest-path", str(backend / "Cargo.toml")],
        check=True, capture_output=True, text=True, timeout=30,
    )
    target = Path(json.loads(metadata.stdout)["target_directory"])
    executable = target / "debug" / ("kitternel-light.exe" if os.name == "nt" else "kitternel-light")
    if not executable.is_file():
        raise FileNotFoundError("Smoke-test backend binary is missing from Cargo's selected target directory; "
                                "run cargo build --locked with the same working directory and Cargo configuration.")
    return executable
