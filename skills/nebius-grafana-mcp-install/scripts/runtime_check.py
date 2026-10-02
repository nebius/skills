"""Internal runtime attestation. No credential contents are emitted."""

import os

from binary_state import inspect as inspect_binary
from pathlib import Path
import sys

from common import SetupError, check_path, digest, json_read, name, read_bytes
from origin import binding
from runtime_contract import FILES


def validate(home, directory, env, *, allow_missing_binary=False):
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
    receipt, present = inspect_binary(directory, binary_receipt_path.parent, home)
    if env["NEBIUS_GRAFANA_MCP_BINARY"] != receipt["path"]:
        raise SetupError("Runtime binary differs from its verified provenance.")
    if not present and not allow_missing_binary:
        raise SetupError("Owned binary is missing; invoke the install skill to repair it.")
    return present


if __name__ == "__main__":
    try:
        validate(Path.home(), Path(__file__).resolve().parent, os.environ)
    except (SetupError, OSError, KeyError, ValueError, TypeError):
        print("Runtime attestation failed; details withheld.", file=sys.stderr)
        sys.exit(1)
