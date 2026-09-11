"""Codex and Claude Code adapters. All captured configuration stays in-process."""

import copy
import json
from pathlib import Path
import re
import tomllib

from common import SetupError, atomic_write, check_path, command, json_read, read_bytes, unique_object
from runtime_contract import MCP_ARGS


def without_server(document, group, server):
    result = copy.deepcopy(document)
    result.setdefault(group, {}).pop(server, None)
    if not result[group]:
        result.pop(group)
    return result


class Client:
    def __init__(self, agent, server, home, *, run=command, env=None, cwd=None):
        self.agent, self.server, self.home = agent, server, home
        self.run, self.env = run, env
        self.cwd = cwd or home
        if agent == "codex":
            # An existing CODEX_HOME is honored; it is never changed by the installer.
            directory = Path((env or {}).get("CODEX_HOME") or home / ".codex")
            self.path, self.group = directory / "config.toml", "mcp_servers"
        else:
            custom = (env or {}).get("CLAUDE_CONFIG_DIR")
            if custom:
                raise SetupError("Custom Claude config directories are outside v1 support; nothing changed.")
            self.path, self.group = home / ".claude.json", "mcpServers"

    def snapshot(self):
        check_path(self.path, self.home, missing=True)
        if not self.path.exists():
            return None, {}
        raw = read_bytes(self.path)
        try:
            value = (tomllib.loads(raw.decode()) if self.agent == "codex"
                     else json.loads(raw, object_pairs_hook=unique_object))
        except (ValueError, UnicodeError) as exc:
            raise SetupError("Client configuration is malformed; contents withheld.") from exc
        if not isinstance(value, dict) or not isinstance(value.get(self.group, {}), dict):
            raise SetupError("Unsupported client configuration shape.")
        return raw, value

    def entry(self, document):
        value = document.get(self.group, {}).get(self.server)
        if value is not None and not isinstance(value, dict):
            raise SetupError("Unsupported MCP registration shape.")
        return value

    def reject_shadowing(self, document):
        if self.agent == "claude":
            projects = document.get("projects", {})
            if not isinstance(projects, dict):
                raise SetupError("Unsupported Claude project configuration.")
            for project in projects.values():
                if not isinstance(project, dict):
                    raise SetupError("Unsupported Claude project configuration.")
                servers = project.get("mcpServers", {})
                if not isinstance(servers, dict):
                    raise SetupError("Unsupported Claude project MCP configuration.")
                if self.server in servers:
                    raise SetupError("A Claude local-scope registration uses this name; choose a distinct name.")
            for parent in (self.cwd, *self.cwd.parents):
                project_file = parent / ".mcp.json"
                if project_file.exists() or project_file.is_symlink():
                    project = json_read(project_file)
                    servers = project.get("mcpServers", {})
                    if not isinstance(servers, dict) or self.server in servers:
                        raise SetupError("A project MCP configuration conflicts with this name.")
        else:
            for parent in (self.cwd, *self.cwd.parents):
                project_file = parent / ".codex/config.toml"
                if project_file == self.path:
                    continue
                if project_file.exists() or project_file.is_symlink():
                    try:
                        project = tomllib.loads(read_bytes(project_file).decode())
                    except (ValueError, UnicodeError) as exc:
                        raise SetupError("Project Codex configuration is malformed.") from exc
                    servers = project.get("mcp_servers", {})
                    if not isinstance(servers, dict) or self.server in servers:
                        raise SetupError("A project Codex MCP configuration conflicts with this name.")

    def desired(self, wrapper, env):
        entry = {"command": str(wrapper), "args": list(MCP_ARGS), "env": env}
        if self.agent == "codex":
            entry["startup_timeout_sec"] = 300.0
        else:
            entry["type"] = "stdio"
        return entry

    def verify_native(self, desired):
        if self.agent == "claude":
            # `claude mcp get` has no JSON mode and can connect to the server.
            return
        raw = self.run(["codex", "mcp", "get", self.server, "--json"],
                       env=self.env, cwd=self.home)
        try:
            data = json.loads(raw)
            transport = data["transport"]
            match = (data.get("enabled", True) is True and transport.get("type") == "stdio"
                     and transport.get("command") == desired["command"]
                     and transport.get("args") == desired["args"]
                     and transport.get("env") == desired["env"]
                     and data.get("startup_timeout_sec") == 300)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SetupError("Codex structured inspection failed; output withheld.") from exc
        if not match:
            raise SetupError("Effective Codex registration differs from the requested configuration.")

    def add(self, desired, before_raw, before_doc):
        if self.snapshot()[0] != before_raw:
            raise SetupError("Client configuration changed before registration.")
        args = [self.agent, "mcp", "add"]
        if self.agent == "claude":
            args += ["--scope", "user", "--transport", "stdio"]
        args += [self.server]
        for key, value in desired["env"].items():
            args += ["--env", f"{key}={value}"]
        args += ["--", desired["command"], *desired["args"]]
        self.run(args, env=self.env, cwd=self.home)
        raw, document = self.snapshot()
        # On its first config write Claude also creates its own machine and
        # migration metadata. No existing values can be overwritten in this
        # case; still reject any additional MCP registration. For every
        # existing config, require exact preservation of unrelated fields.
        fresh_claude = (self.agent == "claude" and before_raw is None
                        and set(document.get(self.group, {})) == {self.server})
        if (not fresh_claude
                and without_server(document, self.group, self.server) != without_server(before_doc, self.group, self.server)):
            raise SetupError("Unrelated configuration changed during registration; inspect partial state.")
        partial = dict(desired)
        partial.pop("startup_timeout_sec", None)
        if self.entry(document) not in (desired, partial):
            raise SetupError("Native registration did not match; partial state retained for inspection.")
        if self.agent == "codex":
            self.set_timeout(desired, raw, document)

    def set_timeout(self, desired, raw, document):
        if self.entry(document) == desired:
            return
        partial = dict(desired)
        partial.pop("startup_timeout_sec")
        if self.entry(document) != partial or raw is None:
            raise SetupError("Only an exact owned partial registration can receive a timeout repair.")
        # Only support the simple table generated by `codex mcp add`.
        text = raw.decode()
        header = re.compile(r"(?m)^\[mcp_servers\." + re.escape(self.server) + r"\][ \t]*\r?$")
        matches = list(header.finditer(text))
        if len(matches) != 1:
            raise SetupError("Unsupported Codex table layout; timeout left unchanged.")
        end = matches[0].end()
        updated = text[:end] + "\nstartup_timeout_sec = 300.0" + text[end:]
        parsed = tomllib.loads(updated)
        expected_doc = copy.deepcopy(document)
        expected_doc[self.group][self.server] = desired
        if parsed != expected_doc:
            raise SetupError("Timeout repair would change unrelated configuration.")
        atomic_write(self.path, updated.encode(), self.home, expected=raw)

    def remove_owned(self, expected, before_raw, before_doc):
        if self.entry(before_doc) != expected or self.snapshot()[0] != before_raw:
            raise SetupError("Owned registration changed before update.")
        args = [self.agent, "mcp", "remove", self.server]
        if self.agent == "claude":
            args += ["--scope", "user"]
        self.run(args, env=self.env, cwd=self.home)
        raw, document = self.snapshot()
        if document != without_server(before_doc, self.group, self.server):
            # Some clients retain an empty mcpServers/mcp_servers object.
            if self.entry(document) is not None or without_server(document, self.group, self.server) != without_server(before_doc, self.group, self.server):
                raise SetupError("Configuration changed during removal; partial state retained.")
        return raw, document
