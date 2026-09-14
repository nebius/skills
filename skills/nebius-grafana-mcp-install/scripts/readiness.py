"""Bounded private MCP conversation. No protocol payload leaves this helper."""

import json
import os
import selectors
import signal
import subprocess
import time

from common import SetupError, unique_object

MAX_FRAME = 8 * 1024 * 1024
PROTOCOL = "2025-03-26"


class ReadinessError(SetupError):
    """Fixed, credential-free readiness failure."""


class Conversation:
    def __init__(self, process, timeout):
        self.process = process
        self.deadline = time.monotonic() + timeout
        self.buffer = b""
        self.total = 0
        self.identifier = 0
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stdin.fileno(), False)

    def wait(self, stream, event):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ReadinessError("Runtime verification timed out; invoke the skill again after checking access.")
        with selectors.DefaultSelector() as selector:
            selector.register(stream, event)
            if not selector.select(remaining):
                raise ReadinessError("Runtime verification timed out; invoke the skill again after checking access.")

    def send(self, value):
        raw = (json.dumps(value) + "\n").encode()
        while raw:
            self.wait(self.process.stdin, selectors.EVENT_WRITE)
            try:
                written = os.write(self.process.stdin.fileno(), raw)
            except BlockingIOError:
                continue
            raw = raw[written:]

    def receive(self):
        while b"\n" not in self.buffer:
            self.wait(self.process.stdout, selectors.EVENT_READ)
            try:
                chunk = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError:
                continue
            if not chunk:
                raise ReadinessError("Runtime ended before verification completed; invoke the skill again.")
            self.buffer += chunk
            self.total += len(chunk)
            if len(self.buffer) > MAX_FRAME or self.total > 2 * MAX_FRAME:
                raise ReadinessError("Runtime verification exceeded its response limit; output withheld.")
        line, self.buffer = self.buffer.split(b"\n", 1)
        value = json.loads(line, object_pairs_hook=unique_object)
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            raise ValueError
        return value

    def request(self, method, params):
        self.identifier += 1
        self.send({"jsonrpc": "2.0", "id": self.identifier, "method": method, "params": params})
        for _ in range(128):
            value = self.receive()
            if "id" not in value and isinstance(value.get("method"), str) and "result" not in value and "error" not in value:
                continue
            if type(value.get("id")) is not int or value["id"] != self.identifier or "method" in value:
                raise ValueError
            if "error" in value:
                raise ReadinessError("Runtime verification returned an error; sensitive details withheld.")
            result = value.get("result")
            if not isinstance(result, dict):
                raise ValueError
            return result
        raise ReadinessError("Runtime verification exceeded its notification limit; output withheld.")

    def verify(self):
        result = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                            "clientInfo": {"name": "nebius-grafana-setup", "version": "1"}})
        capabilities = result.get("capabilities")
        if (result.get("protocolVersion") != PROTOCOL or not isinstance(capabilities, dict)
                or not isinstance(capabilities.get("tools"), dict) or not isinstance(result.get("serverInfo"), dict)):
            raise ValueError
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        params, seen, found = {}, set(), False
        for _ in range(16):
            result = self.request("tools/list", params)
            tool_list = result.get("tools")
            if not isinstance(tool_list, list):
                raise ValueError
            for tool in tool_list:
                if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                    raise ValueError
                if tool["name"] == "list_datasources":
                    schema = tool.get("inputSchema")
                    if not isinstance(schema, dict) or schema.get("type") != "object":
                        raise ValueError
                    found = True
            cursor = result.get("nextCursor")
            if cursor is None:
                break
            if not isinstance(cursor, str) or not 1 <= len(cursor) <= 1024 or cursor in seen:
                raise ValueError
            seen.add(cursor)
            params = {"cursor": cursor}
        else:
            raise ValueError
        if not found:
            raise ReadinessError("The runtime did not advertise datasource discovery; invoke the skill to update it.")
        result = self.request("tools/call", {"name": "list_datasources", "arguments": {"limit": 1}})
        if result.get("isError", False) is not False:
            raise ReadinessError("Datasource discovery failed; registration is retained. Check Grafana access and invoke the skill again.")
        content = result.get("content")
        if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict) or content[0].get("type") != "text":
            raise ValueError
        data = json.loads(content[0]["text"], object_pairs_hook=unique_object)
        # This is the pinned MCP list_datasources result, including empty lists.
        if (not isinstance(data, dict) or not isinstance(data.get("datasources"), list)
                or type(data.get("total")) is not int or data["total"] < 0
                or type(data.get("hasMore")) is not bool):
            raise ValueError


def stop(process):
    """Give the wrapper time to run its trap and stop its separate bridge group."""
    process.stdin.close()
    process.stdout.close()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        # Signal the wrapper first: it owns the bridge's independent session.
        # A suspended wrapper cannot execute its cleanup trap until resumed.
        process.send_signal(signal.SIGCONT)
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def verify(entry, *, env, home, timeout=300):
    process = None
    try:
        process = subprocess.Popen([entry["command"], *entry["args"]], cwd=home,
                                   env={**env, **entry["env"]}, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   start_new_session=True, bufsize=0)
        Conversation(process, timeout).verify()
    except ReadinessError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ReadinessError("Runtime verification failed; raw output withheld. Registration is retained for another skill invocation.") from exc
    finally:
        if process is not None:
            stop(process)
