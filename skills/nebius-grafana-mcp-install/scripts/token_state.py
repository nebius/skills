"""Bind cached tokens and process deadlines to observations and operational session limits."""

import json
import os
import re
from pathlib import Path
import sys
import time

from common import SetupError, atomic_write, digest, json_bytes, json_read, read_bytes

MAX_STARTUP_AGE = 3600
ROTATE_AGE = 36000
STOP_AGE = 39600  # Operational cap only; token expiry is not known.


def token_bytes(path):
    value = read_bytes(path, private=True, limit=65536)
    lines = value.splitlines()
    if len(lines) != 1 or not re.fullmatch(rb"[A-Za-z0-9._~+/-]+=*", lines[0]):
        raise SetupError("Invalid token payload; contents withheld.")
    return lines[0]


def record(path, observed_at, home):
    now = time.time()
    if not 0 <= now - observed_at <= 300:
        raise SetupError("Invalid token observation time.")
    data = token_bytes(path)
    metadata = Path(str(path) + ".json")
    previous = read_bytes(metadata, private=True) if metadata.exists() else None
    if previous is not None:
        old = json_read(metadata, private=True)
        if old.get("sha256") == digest(data):
            old_observed = old.get("observed_at")
            if old.get("version") != 2 or type(old_observed) not in (int, float) or not 0 < old_observed <= now:
                raise SetupError("Repeated token has invalid observation metadata.")
            # A CLI may return cached bytes. Never relabel the same credential
            # as newly observed. Observation never establishes actual token expiry.
            observed_at = min(observed_at, old_observed)
    atomic_write(metadata, json_bytes({"version": 2, "sha256": digest(data), "observed_at": observed_at}),
                 home, expected=previous)


def snapshot(path, now=None):
    now = time.time() if now is None else now
    value = token_bytes(path)
    meta = json_read(Path(str(path) + ".json"), private=True)
    observed = meta.get("observed_at")
    if (set(meta) != {"version", "sha256", "observed_at"} or meta["version"] != 2
            or type(observed) not in (int, float) or not 0 <= now - observed <= MAX_STARTUP_AGE
            or meta["sha256"] != digest(value)):
        raise SetupError("Cached token is missing valid, fresh observation metadata.")
    return value, meta


def inspect(path, now=None):
    # Only observation time is returned to the shell, never a credential/hash.
    return snapshot(path, now)[1]["observed_at"]


def freeze(path, destination, home):
    _, metadata = snapshot(path)
    atomic_write(destination, json_bytes(metadata), home)
    return metadata["observed_at"]


def changed(path, generation_file):
    _, current = snapshot(path)
    previous = json_read(generation_file, private=True)
    return current["sha256"] != previous.get("sha256")


def remaining(observed, start_wall, start_mono, wall, mono):
    return min(observed + STOP_AGE - wall,
               observed + STOP_AGE - start_wall - (mono - start_mono))


def watch(observed, reason_file):
    start_wall, start_mono = time.time(), time.monotonic()
    while remaining(observed, start_wall, start_mono, time.time(), time.monotonic()) > 0:
        time.sleep(1)
    fd = os.open(reason_file, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "w") as out:
        out.write("credential-deadline\n")


def main():
    try:
        action, path = sys.argv[1:3]
        if action == "record":
            record(Path(path), float(sys.argv[3]), Path.home())
        elif action == "inspect":
            print(int(inspect(Path(path))))
        elif action == "generation-observed":
            meta = json_read(Path(path), private=True)
            observed = meta.get("observed_at")
            # Credential loading owns startup freshness. Watchdog attachment
            # tracks this frozen generation's original operational deadline.
            if (set(meta) != {"version", "sha256", "observed_at"} or meta["version"] != 2
                    or type(observed) not in (int, float) or not 0 <= time.time() - observed < STOP_AGE
                    or not isinstance(meta["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", meta["sha256"])):
                raise SetupError("Invalid prepared generation.")
            print(int(observed))
        elif action == "watch":
            watch(float(path), sys.argv[3])
        elif action == "freeze":
            print(int(freeze(Path(path), Path(sys.argv[3]), Path.home())))
        elif action == "changed":
            return 0 if changed(Path(path), Path(sys.argv[3])) else 1
        else:
            raise SetupError("Unsupported token-state operation.")
    except (SetupError, PermissionError, OSError, ValueError, IndexError, json.JSONDecodeError):
        print("Token state validation failed; credential contents withheld.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
