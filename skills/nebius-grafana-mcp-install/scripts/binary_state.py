"""Validate the canonical owned executable without executing it or reading auth."""

import platform
import re

from common import SetupError, check_path, digest, json_read, read_bytes

VERSION = "1.4.0"


def artifact(source, system=None):
    system = (system or f"{platform.system()}-{platform.machine()}").replace("aarch64", "arm64")
    catalog = json_read(source / "artifacts.json")
    item = catalog["archives"].get(system)
    if not item or catalog["version"] != VERSION:
        raise SetupError("Supported platforms are macOS/Linux on arm64 or x86_64.")
    return item, f"https://github.com/grafana/mcp-grafana/releases/download/v{VERSION}/{item['name']}"


def inspect(source, base, home, *, system=None):
    item, url = artifact(source, system)
    check_path(base, home, directory=True, private=True)
    path = base / "binary.json"
    check_path(path, home, private=True)
    receipt = json_read(path, private=True)
    binary = base / "mcp-grafana"
    if (set(receipt) != {"path", "sha256", "version", "source", "archive_sha256"}
            or receipt.get("path") != str(binary) or receipt.get("version") != VERSION
            or receipt.get("source") != url or receipt.get("archive_sha256") != item["sha256"]
            or not isinstance(receipt.get("sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", receipt["sha256"])):
        raise SetupError("Managed binary provenance changed; refusing reuse.")
    check_path(binary, home, missing=True)
    if not binary.exists():
        return receipt, False
    if (binary.stat().st_mode & 0o777 != 0o700
            or digest(read_bytes(binary, limit=256 * 1024 * 1024)) != receipt["sha256"]):
        raise SetupError("Managed binary integrity changed; refusing reuse.")
    return receipt, True
