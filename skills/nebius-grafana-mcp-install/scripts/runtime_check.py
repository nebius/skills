"""Internal runtime attestation. No credential contents are emitted."""

import os
from pathlib import Path
import sys

from common import SetupError, check_path, digest, json_read, name, read_bytes
from origin import binding
from runtime_contract import FILES


def validate(home, directory, env):
    agent = env["NEBIUS_GRAFANA_AGENT"]
    if agent not in {"codex", "claude"}:
        raise SetupError("Invalid runtime client binding.")
    profile = name(env["NEBIUS_GRAFANA_USER_PROFILE"])
    identity = Path(env["NEBIUS_GRAFANA_IDENTITY_FILE"])
    token = Path(env["GRAFANA_TOKEN_FILE"])
    state = identity.parent
    server = name(state.parent.name)
    expected_state = home / ".config/nebius-grafana-mcp" / agent / server / profile
    if identity != expected_state / "identity" or token != expected_state / "iam-token":
        raise SetupError("Runtime state does not match the selected client/profile.")
    binding(state, home, env.get("GRAFANA_URL"))
    check_path(state, home, directory=True, private=True)
    check_path(identity, home, private=True)
    read_bytes(identity, private=True, limit=1024)
    check_path(token, home, private=True, missing=True)
    check_path(directory, home, directory=True, private=True)
    manifest = json_read(directory / "manifest.json", private=True)
    expected_names = set(FILES)
    if set(manifest) != expected_names or set(p.name for p in directory.iterdir()) != {*expected_names, "manifest.json"}:
        raise SetupError("Incomplete runtime bundle.")
    from common import json_bytes
    bundle_digest = digest(json_bytes(manifest))
    if directory != home / ".local/share/nebius-grafana-mcp/runtime" / bundle_digest:
        raise SetupError("Runtime bundle identity or location changed.")
    for filename, checksum in manifest.items():
        if digest(read_bytes(directory / filename)) != checksum:
            raise SetupError("Runtime file integrity changed.")
    binary_receipt_path = Path(env["NEBIUS_GRAFANA_BINARY_RECEIPT"])
    if binary_receipt_path != home / ".local/share/nebius-grafana-mcp/bin/1.4.0/binary.json":
        raise SetupError("Unexpected binary receipt path.")
    check_path(binary_receipt_path, home, private=True)
    receipt = json_read(binary_receipt_path, private=True)
    binary = Path(env["NEBIUS_GRAFANA_MCP_BINARY"])
    if str(binary) != receipt.get("path") or receipt.get("version") != "1.4.0":
        raise SetupError("Runtime binary differs from its verified provenance.")
    if not binary.is_absolute() or binary.resolve(strict=True) != binary:
        raise SetupError("Runtime binary must use its verified physical path.")
    for ancestor in binary.parents:
        info = ancestor.stat()
        if info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
            if ancestor in (Path("/tmp"), Path("/private/tmp")) and info.st_mode & 0o1000:
                continue
            raise SetupError("Runtime binary has an unsafe ancestor.")
    if digest(read_bytes(binary, system=True, limit=256 * 1024 * 1024)) != receipt.get("sha256"):
        raise SetupError("Runtime binary integrity changed.")


if __name__ == "__main__":
    try:
        validate(Path.home(), Path(__file__).resolve().parent, os.environ)
    except (SetupError, OSError, KeyError, ValueError, TypeError):
        print("Runtime attestation failed; details withheld.", file=sys.stderr)
        sys.exit(1)
