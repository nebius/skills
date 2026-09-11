"""Human-operated, user-scoped setup and credential-free local inspection."""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import signal
import sys

from client_config import Client
from common import (SetupError, atomic_write, check_path, clean_env, command,
                    json_bytes, json_read, lock, mkdir_private, name, read_bytes)
from materialize import acquire_binary, bundle_id, materialize, source_files, verify_bundle
from origin import binding, canonical_origin
import token_state


@dataclass(frozen=True)
class Layout:
    home: Path
    agent: str
    profile: str
    grafana_url: str
    server: str = "grafana-nebius"

    def __post_init__(self):
        if self.agent not in {"codex", "claude"}:
            raise SetupError("Select codex or claude explicitly.")
        name(self.profile)
        object.__setattr__(self, "grafana_url", canonical_origin(self.grafana_url))
        # Match the runtime's alphanumeric-leading path/name contract before
        # preflight, downloads or human authentication can have side effects.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.server):
            raise SetupError("Server names must start with a letter or digit and use only letters, digits, underscores and hyphens (maximum 64 characters).")

    @property
    def root(self):
        return self.home / ".local/share/nebius-grafana-mcp"

    @property
    def client_state(self):
        return self.home / ".config/nebius-grafana-mcp" / self.agent

    @property
    def state(self):
        return self.client_state / self.server / self.profile

    @property
    def receipt(self):
        return self.state / "registration.json"

    def environment(self, binary):
        return {
            "NEBIUS_GRAFANA_AGENT": self.agent,
            "NEBIUS_GRAFANA_USER_PROFILE": self.profile,
            "NEBIUS_GRAFANA_IDENTITY_FILE": str(self.state / "identity"),
            "GRAFANA_TOKEN_FILE": str(self.state / "iam-token"),
            "GRAFANA_URL": self.grafana_url,
            "NEBIUS_GRAFANA_MCP_BINARY": binary["path"],
            "NEBIUS_GRAFANA_BINARY_RECEIPT": str(self.root / "bin/1.4.0/binary.json"),
        }


def preflight(layout, run, env):
    result = run(["nebius", "version"], env=env, timeout=10).decode().strip()
    match = re.fullmatch(r"(?:v)?(\d+)\.(\d+)\.(\d+)", result)
    if not match or tuple(map(int, match.groups())) < (0, 12, 247):
        raise SetupError("Requires Nebius CLI >=0.12.247; ask the user to update it.")
    # A version floor alone does not establish availability of donor flags.
    for operation in ("whoami", "get-access-token"):
        help_text = run(["nebius", "iam", operation, "--help"], env=env, timeout=10)
        if not all(flag in help_text for flag in (b"--no-browser", b"--auth-timeout", b"--timeout", b"--retries")):
            raise SetupError("Nebius CLI lacks required bounded authentication options.")
    run([layout.agent, "mcp", "add", "--help"], env=env, timeout=10)


def identity(layout, run, env):
    raw = run(["nebius", "iam", "whoami", "--profile", layout.profile,
               "--format", "json", "--auth-timeout", "120s", "--timeout", "20s", "--retries", "1"],
              env=env, timeout=150)
    try:
        value = json.loads(raw)
        user = value["user_profile"]["id"]
        if (not isinstance(user, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", user)
                or "service_account_profile" in value or "anonymous_profile" in value):
            raise ValueError
    except (ValueError, KeyError, TypeError) as exc:
        raise SetupError("The selected profile is not a validated human identity.") from exc
    expected = f"version=1\nprofile={layout.profile}\nuser_id={user}\n".encode()
    path = layout.state / "identity"
    if path.exists() or path.is_symlink():
        if read_bytes(path, private=True) != expected:
            raise SetupError("Human profile identity changed; existing binding was not replaced.")
    else:
        atomic_write(path, expected, layout.home)


def owned_receipt(layout):
    check_path(layout.receipt, layout.home, missing=True)
    if not layout.receipt.exists():
        return None
    receipt = json_read(layout.receipt, private=True)
    if (receipt.get("owner") != "nebius-grafana-mcp-install"
            or receipt.get("agent") != layout.agent or receipt.get("profile") != layout.profile
            or receipt.get("server") != layout.server
            or receipt.get("phase") not in {"prepared", "ready"}
            or not isinstance(receipt.get("entry"), dict)):
        raise SetupError("Invalid installer ownership receipt; refusing adoption.")
    return receipt


def save_receipt(layout, desired, phase, previous=None):
    value = {"owner": "nebius-grafana-mcp-install", "agent": layout.agent,
             "server": layout.server, "profile": layout.profile, "phase": phase, "entry": desired}
    if previous is not None:
        value["previous"] = previous
    old = read_bytes(layout.receipt, private=True) if layout.receipt.exists() else None
    new = json_bytes(value)
    if old != new:
        atomic_write(layout.receipt, new, layout.home, expected=old)


def partial_entry(agent, desired):
    value = dict(desired)
    if agent == "codex":
        value.pop("startup_timeout_sec", None)
    return value


def apply(layout, source, *, update=False, run=command, env=None, binary_provider=acquire_binary, workdir=None):
    supplied_origin = (os.environ if env is None else env).get("GRAFANA_URL")
    env = dict(env if env is not None else clean_env(layout.agent))
    if supplied_origin and canonical_origin(supplied_origin) != layout.grafana_url:
        raise SetupError("Ambient Grafana origin conflicts with the explicit setup destination.")
    client = Client(layout.agent, layout.server, layout.home, run=run, env=env, cwd=workdir or Path.cwd())
    before_raw, before_doc = client.snapshot()
    client.reject_shadowing(before_doc)
    existing = client.entry(before_doc)
    receipt = owned_receipt(layout)
    if receipt or (layout.state / "origin.json").exists():
        binding(layout.state, layout.home, layout.grafana_url)
    if existing is not None and receipt is None:
        raise SetupError("This name belongs to an existing installation; choose a different server name.")
    if receipt and existing not in (None, receipt["entry"], receipt.get("previous"), partial_entry(layout.agent, receipt["entry"])):
        raise SetupError("Existing registration changed outside this installer; nothing adopted.")
    preflight(layout, run, env)
    mkdir_private(layout.state, layout.home)
    mkdir_private(layout.root, layout.home)
    with lock(layout.state / ".setup.lock", layout.home, timeout=210):
        # Kernel-held setup locks protect first binding creation, unlike check-then-mv.
        # Serialize all registrations of one client, including different profiles.
        with lock(layout.client_state / ".config.lock", layout.home, timeout=210):
            binding(layout.state, layout.home, layout.grafana_url, create=True)
            current_raw, current_doc = client.snapshot()
            if current_raw != before_raw:
                raise SetupError("Client configuration changed while waiting for setup.")
            bundle = materialize(source, layout.root / "runtime", layout.home)
            with lock(layout.root / ".binary.lock", layout.home, timeout=210):
                binary = binary_provider(source, layout.root / "bin/1.4.0", layout.home)
            desired = client.desired(bundle / "run-nebius-grafana-mcp.sh", layout.environment(binary))
            if receipt and receipt["entry"] != desired and not update:
                raise SetupError("An owned runtime update requires explicit --apply --update.")
            identity(layout, run, env)
            try:
                if update:
                    raise SetupError("Explicit recovery requests credential renewal.")
                token_state.inspect(layout.state / "iam-token")
            except (SetupError, OSError):
                runtime_env = {**env, **layout.environment(binary)}
                run([str(bundle / "run-nebius-grafana-mcp.sh"), "--refresh-token-only"],
                    env=runtime_env, cwd=layout.home, timeout=240)
                token_state.inspect(layout.state / "iam-token")
            old_entry = client.entry(current_doc)
            if old_entry == desired:
                client.verify_native(desired)
                save_receipt(layout, desired, "ready")
                return
            pending_partial = partial_entry(layout.agent, desired)
            if receipt and old_entry == pending_partial:
                client.set_timeout(desired, current_raw, current_doc)
            else:
                save_receipt(layout, desired, "prepared", previous=old_entry)
                if old_entry is not None:
                    if not update:
                        raise SetupError("Replacing an owned entry requires --update.")
                    current_raw, current_doc = client.remove_owned(old_entry, current_raw, current_doc)
                client.add(desired, current_raw, current_doc)
            after_raw, after_doc = client.snapshot()
            if client.entry(after_doc) != desired:
                raise SetupError("Local registration verification failed; partial state retained.")
            client.verify_native(desired)
            save_receipt(layout, desired, "ready")


def check(layout, source, *, run=command, env=None, workdir=None):
    env = dict(env if env is not None else clean_env(layout.agent))
    client = Client(layout.agent, layout.server, layout.home, run=run, env=env, cwd=workdir or Path.cwd())
    _, document = client.snapshot()
    client.reject_shadowing(document)
    receipt = owned_receipt(layout)
    entry = client.entry(document)
    if entry and receipt is None:
        raise SetupError("Existing registration is not owned by this installer.")
    # Structural inspection never reads token contents, mints tokens or starts MCP.
    ready = bool(receipt and receipt["phase"] == "ready" and entry == receipt["entry"])
    for filename in ("origin.json", "identity", "iam-token", "iam-token.json"):
        path = layout.state / filename
        check_path(path, layout.home, private=True, missing=True)
        ready = ready and path.is_file()
    if ready:
        binding(layout.state, layout.home, layout.grafana_url)
        expected_bundle = layout.root / "runtime" / bundle_id(source_files(source))
        ready = entry.get("command") == str(expected_bundle / "run-nebius-grafana-mcp.sh")
        if ready:
            verify_bundle(expected_bundle, layout.home)
            client.verify_native(entry)
    print("registration: " + ("locally matches" if ready else "setup or repair needed"))
    print("runtime: not started; live readiness not verified")
    return 0 if ready else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect or explicitly configure one local Grafana MCP client.")
    parser.add_argument("--agent", choices=("codex", "claude"), required=True)
    parser.add_argument("--user-profile", required=True)
    parser.add_argument("--grafana-url", required=True, help="Trusted HTTPS Grafana origin; receives this human profile's credential.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Local inspection only (default).")
    group.add_argument("--apply", action="store_true", help="Human-run setup of the selected client and private credential runtime.")
    parser.add_argument("--mcp-server-name", default="grafana-nebius",
                        help="1-64 letters, digits, underscores or hyphens; start with a letter or digit.")
    parser.add_argument("--update", action="store_true", help="With --apply, renew credentials and update an exactly owned registration.")
    args = parser.parse_args(argv)
    if args.update and not args.apply:
        parser.error("--update requires --apply")
    try:
        layout = Layout(Path.home(), args.agent, args.user_profile, args.grafana_url, args.mcp_server_name)
        source = Path(__file__).resolve().parent
        if args.apply:
            apply(layout, source, update=args.update)
            print("Local setup verified; restart the selected client and run readiness checks.")
            if args.agent == "claude":
                print("Launch Claude Code with MCP_TIMEOUT=300000 for the bounded authentication startup window.")
            return 0
        return check(layout, source)
    except KeyboardInterrupt:
        print("Setup cancelled; owned command processes stopped.", file=sys.stderr)
        return 130
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print("Local setup failed; sensitive details withheld. Inspect the selected installation.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    def cancel(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, cancel)
    sys.exit(main())
