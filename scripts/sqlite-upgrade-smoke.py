#!/usr/bin/env python3
"""Verify two locally built releases retain data and migrations on a disposable volume."""
import argparse
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("docker_smoke", Path(__file__).with_name("docker-smoke.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def verify(previous_image, image):
    for reference in (previous_image, image):
        base.docker("image", "inspect", reference)
    fixture = base.DockerSmoke()
    fixture.setUp()
    try:
        base.IMAGE = previous_image
        previous = fixture.start("previous-release")
        fixture.wait_ready(previous)
        base.docker("exec", previous, "sqlite3", "/data/kitternel.db",
                    "UPDATE greetings SET message = 'Retained from previous release' WHERE id = 1;")
        history = base.docker("exec", previous, "sqlite3", "/data/kitternel.db",
                              "SELECT version,success,hex(checksum) FROM _sqlx_migrations ORDER BY version;").stdout
        fixture.stop_cleanly(previous)
        base.docker("rm", previous)
        fixture.containers.remove(previous)
        base.IMAGE = image
        replacement = fixture.start("replacement-release")
        port = fixture.wait_ready(replacement)
        if json.loads(base.http_request(port, "/api/hello")[1]) != {"message": "Retained from previous release"}:
            raise AssertionError("Upgrade did not retain application data")
        if base.docker("exec", replacement, "sqlite3", "/data/kitternel.db",
                       "SELECT version,success,hex(checksum) FROM _sqlx_migrations ORDER BY version;").stdout != history:
            raise AssertionError("Upgrade changed existing migration history")
        fixture.stop_cleanly(replacement)
    finally:
        if not fixture.doCleanups():
            raise RuntimeError("Upgrade drill cleanup failed")
    print("Upgrade retained changed application data and migration checksums on a disposable volume.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-image", required=True, help="Trusted local previous release with the same database path")
    parser.add_argument("--image", required=True, help="Trusted local replacement release without new migrations")
    args = parser.parse_args()
    verify(args.previous_image, args.image)
