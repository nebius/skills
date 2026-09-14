"""Local MCP discovery and a bounded handoff to the authenticated backend."""

import json
import os
import selectors
import time

from common import SetupError, digest, json_read, read_bytes
from runtime_contract import MCP_ARGS

PROTOCOL = "2025-03-26"
PREPARE_SECONDS = 240
PREPARING = {"code": -32001, "message": "MCP runtime is preparing; retry shortly.",
             "data": {"state": "preparing", "retryable": True}}
DISCOVERY = {"tools/list": ("tools", "name"), "resources/list": ("resources", "uri"),
             "resources/templates/list": ("resourceTemplates", "uriTemplate")}
MAX_PENDING = 64


def ordered(values, key):
    if not isinstance(values, list) or any(not isinstance(v, dict) or not isinstance(v.get(key), str) for v in values):
        raise SetupError("Invalid discovery catalog.")
    if len({v[key] for v in values}) != len(values):
        raise SetupError("Duplicate discovery catalog item.")
    return sorted(values, key=lambda value: value[key])


def load_catalog(directory):
    catalog = json_read(directory / "catalog.json")
    if (set(catalog) != {"version", "args", "initialize", "artifacts_sha256", "tools", "resources", "resourceTemplates"}
            or catalog["version"] != "1.4.0" or catalog["args"] != list(MCP_ARGS)
            or catalog["artifacts_sha256"] != digest(read_bytes(directory / "artifacts.json"))):
        raise SetupError("Discovery catalog does not match the pinned runtime.")
    initial = catalog["initialize"]
    if (not isinstance(initial, dict) or initial.get("protocolVersion") != PROTOCOL
            or set(initial.get("capabilities", {})) != {"tools", "resources"}
            or initial.get("serverInfo", {}).get("version") != "1.4.0"):
        raise SetupError("Unsupported discovery capabilities.")
    for field, key in DISCOVERY.values():
        catalog[field] = ordered(catalog[field], key)
    return catalog


class Frontend:
    def __init__(self, catalog):
        self.catalog = catalog
        self.client_initialized = False
        self.client_notified = False
        self.ready = False
        self.next_id = 0
        self.pending = {}
        self.discovery_index = -1
        self.items = []
        self.cursors = set()
        self.pages = 0

    def request(self, method, params):
        self.next_id += 1
        return {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}

    def bootstrap(self):
        return self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                           "clientInfo": {"name": "nebius-grafana-bridge", "version": "1"}})

    def client(self, message):
        """Return (client responses, backend requests); never queue pending auth reads."""
        method, params = message.get("method"), message.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            raise SetupError("Invalid client protocol message.")
        if "id" not in message:
            if method == "notifications/initialized" and self.client_initialized:
                self.client_notified = True
            elif method == "notifications/cancelled":
                for internal, original in list(self.pending.items()):
                    if type(original) is type(params.get("requestId")) and original == params.get("requestId"):
                        del self.pending[internal]
                        return [], [{"jsonrpc": "2.0", "method": method, "params": {"requestId": internal}}]
            return [], []
        identifier = message["id"]

        def result(value):
            return [{"jsonrpc": "2.0", "id": identifier, "result": value}], []

        def error(code, text):
            return [{"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": text}}], []

        if method == "initialize" and not self.client_initialized:
            if not isinstance(params.get("protocolVersion"), str) or not isinstance(params.get("capabilities"), dict):
                return error(-32602, "Invalid initialization parameters.")
            self.client_initialized = True
            return result(self.catalog["initialize"])
        if method == "ping":
            return result({})
        if not self.client_notified:
            return error(-32600, "Initialize the MCP connection first.")
        if method in DISCOVERY:
            if params.get("cursor") is not None:
                return error(-32602, "Invalid discovery cursor.")
            return result({DISCOVERY[method][0]: self.catalog[DISCOVERY[method][0]]})
        if method not in {"tools/call", "resources/read"}:
            return error(-32601, "Unsupported MCP method.")
        if method == "tools/call" and params.get("name") not in {v["name"] for v in self.catalog["tools"]}:
            return error(-32602, "Unknown tool.")
        if not self.ready:
            return [{"jsonrpc": "2.0", "id": identifier, "error": PREPARING}], []
        if len(self.pending) >= MAX_PENDING:
            return error(-32000, "MCP request limit exceeded.")
        if any(type(v) is type(identifier) and v == identifier for v in self.pending.values()):
            return error(-32600, "Duplicate active request identifier.")
        request = self.request(method, params)
        self.pending[request["id"]] = identifier
        return [], [request]

    def backend(self, message):
        if "method" in message:
            if message["method"] == "ping" and "id" in message:
                return [], [{"jsonrpc": "2.0", "id": message["id"], "result": {}}]
            if message["method"] == "notifications/tools/list_changed":
                raise SetupError("Pinned backend catalog changed; connection stopped.")
            if "id" in message:
                raise SetupError("Backend requested an unnegotiated capability.")
            return ([message] if self.ready else []), []
        identifier = message.get("id")
        if type(identifier) is not int:
            raise SetupError("Unexpected backend response identifier.")
        if self.ready:
            if identifier not in self.pending:
                if 0 < identifier <= self.next_id:
                    return [], []  # A cancelled operation may finish after cancellation.
                raise SetupError("Unexpected backend response.")
            return [{**message, "id": self.pending.pop(identifier)}], []
        if identifier != self.next_id or "error" in message or not isinstance(message.get("result"), dict):
            raise SetupError("Backend initialization failed; details withheld.")
        value = message["result"]
        outbound = []
        if self.discovery_index == -1:
            if value != self.catalog["initialize"]:
                raise SetupError("Backend initialization differs from the pinned catalog.")
            outbound.append({"jsonrpc": "2.0", "method": "notifications/initialized"})
        else:
            method = list(DISCOVERY)[self.discovery_index]
            field, key = DISCOVERY[method]
            self.items.extend(ordered(value.get(field), key))
            self.pages += 1
            cursor = value.get("nextCursor")
            if cursor is not None:
                if not isinstance(cursor, str) or not 1 <= len(cursor) <= 1024 or cursor in self.cursors or self.pages >= 16:
                    raise SetupError("Backend discovery pagination exceeded its bound.")
                self.cursors.add(cursor)
                return [], [self.request(method, {"cursor": cursor})]
            if ordered(self.items, key) != self.catalog[field]:
                raise SetupError("Backend discovery differs from the pinned catalog.")
        self.discovery_index += 1
        self.items, self.cursors, self.pages = [], set(), 0
        if self.discovery_index == len(DISCOVERY):
            self.ready = True
        else:
            outbound.append(self.request(list(DISCOVERY)[self.discovery_index], {}))
        return [], outbound


def exchange(catalog, backend_in, backend_out, stopped, *, stdin_fd=0, stdout_fd=1,
             prepare_seconds=PREPARE_SECONDS):
    from mcp_bridge import checked_frame, MAX_FRAME

    frontend = Frontend(catalog)
    buffers = {stdin_fd: b"", backend_out: b""}
    pending = {stdout_fd: b"", backend_in: b""}
    original = {fd: os.get_blocking(fd) for fd in (stdin_fd, stdout_fd, backend_in, backend_out)}
    deadline = time.monotonic() + prepare_seconds

    def enqueue(fd, messages):
        for message in messages:
            pending[fd] += checked_frame(json.dumps(message).encode(), ())
        if len(pending[fd]) > 2 * MAX_FRAME:
            raise SetupError("MCP buffering limit exceeded.")

    enqueue(backend_in, [frontend.bootstrap()])
    for fd in original:
        os.set_blocking(fd, False)
    try:
        while True:
            if stopped.is_set():
                raise SetupError("Authenticated backend stopped; connection closed.")
            if not frontend.ready and time.monotonic() >= deadline:
                raise SetupError("MCP preparation timed out; invoke setup again.")
            with selectors.DefaultSelector() as selector:
                for fd in buffers:
                    if max(map(len, pending.values())) < MAX_FRAME:
                        selector.register(fd, selectors.EVENT_READ)
                for fd, data in pending.items():
                    if data:
                        selector.register(fd, selectors.EVENT_WRITE)
                events = selector.select(0.05)
            for key, event in events:
                fd = key.fd
                if event == selectors.EVENT_WRITE:
                    pending[fd] = pending[fd][os.write(fd, pending[fd]):]
                    continue
                chunk = os.read(fd, 65536)
                if not chunk:
                    if buffers[fd]:
                        raise SetupError("Incomplete MCP frame.")
                    if fd == stdin_fd:
                        return 0
                    raise SetupError("Backend ended before the connection closed.")
                buffers[fd] += chunk
                while b"\n" in buffers[fd]:
                    frame, buffers[fd] = buffers[fd].split(b"\n", 1)
                    checked_frame(frame, ())
                    responses, requests = (frontend.client if fd == stdin_fd else frontend.backend)(json.loads(frame))
                    enqueue(stdout_fd, responses)
                    enqueue(backend_in, requests)
                if len(buffers[fd]) > MAX_FRAME:
                    raise SetupError("MCP frame size exceeded.")
    finally:
        for fd, blocking in original.items():
            os.set_blocking(fd, blocking)
