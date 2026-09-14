"""Synthetic systems only. No real CLI, configuration or network is used."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import SetupError, atomic_write, command, digest, json_bytes, mkdir_private  # noqa: E402
import setup  # noqa: E402

ORIGIN = "https://grafana.example.test/"

NEBIUS = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
log = pathlib.Path(os.environ['FAKE_COMMAND_LOG'])
with log.open('a') as f:
    f.write(json.dumps(args) + '\n')
if args == ['version']:
    print('0.12.300')
elif '--help' in args:
    print('--no-browser --auth-timeout --timeout --retries')
elif args[:2] == ['iam', 'whoami']:
    assert '--profile' in args
    assert not os.environ.get('NEBIUS_IAM_TOKEN')
    assert not os.environ.get('NEBIUS_PROFILE')
    if os.environ.get('FAKE_BROWSER_MARKER'):
        marker = pathlib.Path(os.environ['FAKE_BROWSER_MARKER'])
        if not marker.exists():
            assert '--no-browser' not in args
            print('SENTINEL-LOGIN https://login.example.test/?secret=synthetic', file=sys.stderr)
            marker.write_text('synthetic sign-in completed')
    user = 'user-example'
    if os.environ.get('FAKE_CHANGED_ID'):
        user = 'changed-example'
    print(json.dumps({'user_profile': {'id': user}}))
elif args[:2] == ['iam', 'get-access-token']:
    time.sleep(float(os.environ.get('FAKE_MINT_DELAY', '0')))
    if os.environ.get('FAKE_FAIL_MINT'):
        print('SENTINEL-SECRET-DO-NOT-PRINT', file=sys.stderr)
        sys.exit(9)
    counter = pathlib.Path(os.environ['FAKE_COUNTER'])
    count = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(count))
    print('synthetic-token-' + ('1' if os.environ.get('FAKE_SAME_TOKEN') else str(count)))
else:
    sys.exit(8)
'''

MCP = r'''#!/usr/bin/env python3
import hashlib, json, os, pathlib, sys, time, urllib.request
assert sys.argv[1:] == ['--transport', 'stdio', '--disable-write', '--disable-proxied', '--enabled-tools', 'search,datasource,dashboard,prometheus,loki,api', '--max-loki-log-limit', '20']
assert not os.environ.get('NEBIUS_IAM_TOKEN')
assert os.environ['GRAFANA_URL'].startswith('http://127.0.0.1:')
assert not os.environ.get('GRAFANA_SERVICE_ACCOUNT_TOKEN_FILE')
assert not os.environ.get('GRAFANA_TOKEN_FILE')
assert not os.environ.get('GRAFANA_EXTRA_HEADERS')
token = os.environ['GRAFANA_SERVICE_ACCOUNT_TOKEN'].encode()
assert b'synthetic-token' not in token
event = {'pid': os.getpid(), 'generation': hashlib.sha256(token).hexdigest()}
with pathlib.Path(os.environ['FAKE_MCP_LOG']).open('a') as f:
    f.write(json.dumps(event) + '\n')
for line in sys.stdin:
    request = json.loads(line)
    if os.environ.get('FAKE_PROTOCOL_LOG'):
        with pathlib.Path(os.environ['FAKE_PROTOCOL_LOG']).open('a') as f:
            f.write(json.dumps(request) + '\n')
    if 'id' not in request:
        continue
    if request.get('method') == 'initialize':
        result = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'fixture', 'version': '1'}}
    elif request.get('method') == 'tools/list':
        result = {'tools': [{'name': 'list_datasources', 'inputSchema': {'type': 'object'}}]}
    else:
        data = {'datasources': [], 'total': 0, 'hasMore': False}
        if os.environ.get('FAKE_MCP_HTTP'):
            req = urllib.request.Request(os.environ['GRAFANA_URL'] + 'api/datasources',
                headers={'Authorization': 'Bearer ' + os.environ['GRAFANA_SERVICE_ACCOUNT_TOKEN']})
            with urllib.request.urlopen(req, timeout=3) as response:
                sources = json.load(response)
            data = {'datasources': sources[:1], 'total': len(sources), 'hasMore': len(sources) > 1}
        result = {'content': [{'type': 'text', 'text': json.dumps(data)}]}
    mode = os.environ.get('FAKE_MCP_MODE')
    if mode == 'stall':
        time.sleep(30)
    if mode == 'wrong-id':
        request['id'] = 1000
    if mode == 'missing-tool' and request['method'] == 'tools/list':
        result = {'tools': []}
    if mode == 'tool-error' and request['method'] == 'tools/call':
        result = {'isError': True, 'content': [{'type': 'text', 'text': 'SENTINEL-SECRET https://login.example.test/?secret=sentinel'}]}
    if mode == 'oversized':
        print('x' * (9 * 1024 * 1024), flush=True)
    if mode == 'protocol-error':
        print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -1, 'message': 'SENTINEL-SECRET'}}), flush=True)
        continue
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
'''


def toml_bytes(document):
    lines = ["# fixture configuration"]

    def emit(obj, path=()):
        for key, value in obj.items():
            if not isinstance(value, dict):
                lines.append(f"{key} = {json.dumps(value)}")
        for key, value in obj.items():
            if isinstance(value, dict):
                child = (*path, key)
                lines.append("\n[" + ".".join(child) + "]")
                emit(value, child)

    emit(document)
    return ("\n".join(lines) + "\n").encode()


class FakeSystem:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="grafana-skill-test-")
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir(mode=0o700)
        self.bin = self.root / "fake-bin"
        self.bin.mkdir(mode=0o700)
        # Versioned Python installations do not always expose a python3 alias.
        (self.bin / "python3").symlink_to(sys.executable)
        (self.bin / "nebius").write_text(NEBIUS)
        (self.bin / "nebius").chmod(0o700)
        self.source = self.root / "source"
        shutil.copytree(SCRIPTS, self.source, ignore=shutil.ignore_patterns("__pycache__"))
        self.env = {
            "PATH": str(self.bin) + os.pathsep + str(Path(sys.executable).parent) + os.pathsep + os.defpath,
            # The spawned fixture process represents a synthetic user; the
            # agent process and its actual HOME/CODEX_HOME are never modified.
            "HOME": str(self.home),
            "FAKE_COMMAND_LOG": str(self.root / "commands.jsonl"),
            "FAKE_COUNTER": str(self.root / "counter"),
            "FAKE_MCP_LOG": str(self.root / "mcp.jsonl"),
            "AI_AGENT": "test-harness",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        self.calls = []
        self.fail_after_add = False
        self.add_unrelated_drift = False

    def close(self):
        self.temp.cleanup()

    def layout(self, agent="codex", profile="testing-human", server="grafana-nebius"):
        return setup.Layout(self.home, agent, profile, ORIGIN, server)

    def path(self, agent):
        return self.home / (".codex/config.toml" if agent == "codex" else ".claude.json")

    def read_config(self, agent):
        path = self.path(agent)
        if not path.exists():
            return {}
        raw = path.read_bytes()
        return tomllib.loads(raw.decode()) if agent == "codex" else json.loads(raw)

    def write_config(self, agent, document):
        path = self.path(agent)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(toml_bytes(document) if agent == "codex" else json_bytes(document))
        path.chmod(0o600)

    def binary(self, source, base, home):
        mkdir_private(base, home)
        executable = base / "mcp-grafana"
        receipt = {"path": str(executable), "sha256": digest(MCP.encode()), "version": "1.4.0", "source": "synthetic-fixture"}
        if not executable.exists():
            atomic_write(executable, MCP.encode(), home, mode=0o700)
            atomic_write(base / "binary.json", json_bytes(receipt), home)
        return receipt

    def run(self, args, *, env=None, cwd=None, timeout=30):
        self.calls.append(list(args))
        if args[0] == "nebius" or args[0].endswith("run-nebius-grafana-mcp.sh"):
            return command(args, env=env, cwd=cwd, timeout=timeout)
        if args[0] not in {"codex", "claude"}:
            raise AssertionError("Fixture refused unexpected executable")
        agent = args[0]
        if args[-1] == "--help":
            return b"mcp add --scope --transport --env"
        group = "mcp_servers" if agent == "codex" else "mcpServers"
        document = self.read_config(agent)
        action = args[2]
        if action == "get":
            assert agent == "codex"  # Claude get must never be called.
            entry = document[group][args[3]]
            return json_bytes({"enabled": True, "startup_timeout_sec": entry.get("startup_timeout_sec"),
                               "transport": {"type": "stdio", **{k: v for k, v in entry.items() if k != "startup_timeout_sec"}}})
        if action == "remove":
            document[group].pop(args[3])
            if not document[group]:
                document.pop(group)
        elif action == "add":
            index = 3
            if agent == "claude":
                assert args[3:7] == ["--scope", "user", "--transport", "stdio"]
                index = 7
            server = args[index]
            index += 1
            environ = {}
            while args[index] == "--env":
                key, value = args[index + 1].split("=", 1)
                environ[key] = value
                index += 2
            assert args[index] == "--"
            entry = {"command": args[index + 1], "args": args[index + 2:], "env": environ}
            if agent == "claude":
                entry["type"] = "stdio"
            document.setdefault(group, {})[server] = entry
            if self.add_unrelated_drift:
                document["concurrent_setting"] = "preserve-me"
        else:
            raise AssertionError("Unexpected fixture client operation")
        self.write_config(agent, document)
        if self.fail_after_add and action == "add":
            self.fail_after_add = False
            raise SetupError("Injected interruption after native add.")
        return b""

    def apply(self, layout=None, update=False, verify=False):
        layout = layout or self.layout()
        # Existing runtime tests need registration as fixture setup. New installer
        # tests explicitly exercise the production verifier, including HTTP.
        self.result = setup.apply(layout, self.source, update=update, run=self.run, env=self.env,
                                  binary_provider=self.binary, workdir=self.home,
                                  verifier=setup.readiness.verify if verify else lambda *args, **kwargs: None)
        return layout

    def runtime_command(self, layout=None):
        layout = layout or self.layout()
        group = "mcp_servers" if layout.agent == "codex" else "mcpServers"
        entry = self.read_config(layout.agent)[group][layout.server]
        return [entry["command"], *entry["args"]], {**self.env, **entry["env"]}
