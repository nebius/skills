"""Finite, authenticated loopback reads to one operator-bound HTTPS origin.

No cloud credential reaches the MCP child. This is not an OS-user sandbox.
The injectable connection factory is an in-process test seam, never a CLI/env
setting; production always uses verified HTTPSConnection with no proxy lookup.
"""

from contextlib import contextmanager
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import socket
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, unquote

from common import unique_object
from origin import canonical_origin

MAX_BODY = 256 * 1024
MAX_RESPONSE = 8 * 1024 * 1024
MAX_TARGET = 16384
REQUEST_SECONDS = 30
UID = r"[A-Za-z0-9_-]{1,128}"
DATASOURCE_ROUTE = re.compile(
    rf"^(/api/datasources/(?:proxy/uid/({UID})|uid/({UID})/resources))(/.*)$"
)
PROM_READ = re.compile(r"^/api/v1/(?:query|query_range|labels|metadata|label/[A-Za-z0-9_:]+/values)$")
LOKI_READ = re.compile(r"^/loki/api/v1/(?:query|query_range|labels|index/stats|patterns|label/[A-Za-z0-9_]+/values)$")
TEMPO_READ = re.compile(
    r"^/api/(?:search|(?:v2/)?search/tags|(?:v2/)?search/tag/[A-Za-z0-9_.:-]+/values|v2/traces/[A-Fa-f0-9]{16,32})$"
)
QUERY_POSTS = {"/api/v1/query", "/api/v1/query_range", "/api/v1/labels"}
FORM_KEYS = {"query", "start", "end", "step", "time", "timeout", "limit", "match[]"}


class ProxyError(Exception):
    def __init__(self, status=502, code="upstream-read-failed"):
        self.status, self.code = status, code
        super().__init__(code)


def contains_secret(value, protected):
    """Inspect decoded strings/keys, including JSON-escaped credential text."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any(secret and secret in item for secret in protected):
                return True
        elif isinstance(item, dict):
            pending.extend(item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return False


def decode_json(body, protected=()):
    try:
        value = json.loads(body, object_pairs_hook=unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if contains_secret(value, protected):
            raise ValueError
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProxyError(502, "upstream-response-rejected") from exc


class Backend:
    def __init__(self, origin, token, *, connection_factory=http.client.HTTPSConnection):
        self.origin = canonical_origin(origin)
        parsed = urlsplit(self.origin)
        self.host, self.port = parsed.hostname, parsed.port or 443
        self.token = token
        self.connection_factory = connection_factory

    def request(self, method, target, body=b"", *, deadline=None):
        deadline = deadline or time.monotonic() + REQUEST_SECONDS
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProxyError(504, "read-timeout")
        conn = self.connection_factory(self.host, self.port, timeout=remaining)
        timer = None
        try:
            conn.connect()
            active_socket = conn.sock

            def expire():
                try:
                    active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProxyError(504, "read-timeout")
            timer = threading.Timer(remaining, expire)
            timer.daemon = True
            timer.start()
            headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
            if method == "POST":
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            conn.request(method, target, body=body or None, headers=headers)
            response = conn.getresponse()
            if 300 <= response.status < 400:
                raise ProxyError(502, "upstream-redirect-refused")
            if not 200 <= response.status < 300:
                raise ProxyError(response.status if 400 <= response.status < 600 else 502,
                                 "upstream-read-rejected")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ProxyError(502, "encoded-response-refused")
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise ProxyError(502, "response-limit-exceeded")
            if time.monotonic() >= deadline:
                raise ProxyError(504, "read-timeout")
            decode_json(body, (self.token,))
            return body
        except ProxyError:
            raise
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise ProxyError() from exc
        finally:
            if timer is not None:
                timer.cancel()
            conn.close()


def parsed_target(target):
    if (not isinstance(target, str) or len(target) > MAX_TARGET or not target.isascii()
            or not target.startswith("/") or target.startswith("//")
            or re.search(r"[\x00-\x20\x7f\\#]", target)):
        raise ProxyError(400, "invalid-request-target")
    parsed = urlsplit(target)
    path = unquote(parsed.path, errors="strict")
    if (parsed.scheme or parsed.netloc or re.search(r"%(?:2f|5c|25)", parsed.path, re.I)
            or "%" in path or "\\" in path or "//" in path
            or any(part in (".", "..") for part in path.split("/"))
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise ProxyError(400, "invalid-request-target")
    try:
        params = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=128)
    except ValueError as exc:
        raise ProxyError(400, "invalid-query") from exc
    if any(key.lower() in {"watch", "stream", "follow"} for key, _ in params):
        raise ProxyError(403, "streaming-refused")
    return path, params


class ReadPolicy:
    def __init__(self, backend):
        self.backend = backend
        self.prometheus_routes = set()
        self.lock = threading.Lock()

    def datasource(self, uid, deadline):
        value = decode_json(self.backend.request("GET", "/api/datasources/uid/" + uid, deadline=deadline))
        if not isinstance(value, dict) or value.get("uid") != uid or not isinstance(value.get("type"), str):
            raise ProxyError(403, "datasource-not-verified")
        return value["type"]

    def prometheus(self, prefix, uid, kind, deadline):
        if kind in {"loki", "tempo"}:
            raise ProxyError(403, "datasource-protocol-mismatch")
        with self.lock:
            verified = prefix in self.prometheus_routes
        if not verified:
            # Custom plugin names do not establish protocol compatibility.
            value = decode_json(self.backend.request(
                "GET", prefix + "/api/v1/query?query=vector%281%29", deadline=deadline))
            data = value.get("data", {}) if isinstance(value, dict) else {}
            result = data.get("result") if isinstance(data, dict) else None
            if (not isinstance(value, dict) or value.get("status") != "success" or not isinstance(data, dict)
                    or data.get("resultType") != "vector" or not isinstance(result, list)
                    or len(result) != 1 or not isinstance(result[0], dict)
                    or not isinstance(result[0].get("value"), list)
                    or len(result[0]["value"]) != 2 or result[0]["value"][1] != "1"):
                raise ProxyError(403, "prometheus-route-not-verified")
            with self.lock:
                self.prometheus_routes.add(prefix)

    def request(self, method, target, body=b"", content_type=""):
        deadline = time.monotonic() + REQUEST_SECONDS
        path, params = parsed_target(target)
        if method not in {"GET", "POST"}:
            raise ProxyError(405, "method-refused")
        if method == "GET" and body:
            raise ProxyError(400, "get-body-refused")
        health = re.fullmatch(rf"/api/datasources/uid/({UID})/health", path)
        if health:
            if method != "GET" or "?" in target:
                raise ProxyError(403, "health-route-refused")
            # Resolve the exact UID through the bound Grafana before invoking
            # its plugin health handler. This is not an installation check.
            self.datasource(health.group(1), deadline)
            return self.backend.request("GET", path, deadline=deadline)
        simple = path in {"/api/frontend/settings", "/api/datasources", "/api/search"}
        simple = simple or bool(re.fullmatch(rf"/api/datasources/uid/{UID}|/api/dashboards/uid/{UID}", path))
        simple = simple or bool(re.fullmatch(r"/api/datasources/name/[^/]{1,256}", path))
        simple = simple or bool(re.fullmatch(
            rf"/apis/dashboard\.grafana\.app(?:/v\d+(?:(?:alpha|beta)\d+)?/namespaces/{UID}/dashboards/{UID})?/?", path))
        if simple and method == "GET":
            return self.backend.request(method, target, deadline=deadline)
        route = DATASOURCE_ROUTE.fullmatch(path)
        if not route:
            raise ProxyError(403, "route-refused")
        prefix, uid_a, uid_b, suffix = route.groups()
        uid = uid_a or uid_b
        if method == "POST":
            if suffix not in QUERY_POSTS or params or content_type != "application/x-www-form-urlencoded":
                raise ProxyError(403, "post-route-refused")
            try:
                fields = parse_qsl(body.decode("utf-8"), keep_blank_values=True, max_num_fields=128)
            except (ValueError, UnicodeError) as exc:
                raise ProxyError(400, "invalid-query-form") from exc
            if not fields or any(key not in FORM_KEYS for key, _ in fields):
                raise ProxyError(400, "invalid-query-form")
        elif not (PROM_READ.fullmatch(suffix) or LOKI_READ.fullmatch(suffix) or TEMPO_READ.fullmatch(suffix)):
            raise ProxyError(403, "route-refused")
        kind = self.datasource(uid, deadline)
        if PROM_READ.fullmatch(suffix):
            self.prometheus(prefix, uid, kind, deadline)
        elif LOKI_READ.fullmatch(suffix):
            if kind != "loki":
                raise ProxyError(403, "datasource-protocol-mismatch")
            # The generic GET tool must not bypass the native Loki result cap.
            if suffix in {"/loki/api/v1/query", "/loki/api/v1/query_range", "/loki/api/v1/patterns"}:
                limits = [value for key, value in params if key == "limit"]
                if len(limits) > 1 or any(not value.isdigit() or not 1 <= int(value) <= 20 for value in limits):
                    raise ProxyError(400, "loki-limit-exceeded")
                if not limits:
                    params.append(("limit", "20"))
                    target = urlsplit(target).path + "?" + urlencode(params)
        elif kind != "tempo":
            raise ProxyError(403, "datasource-protocol-mismatch")
        return self.backend.request(method, target, body, deadline=deadline)


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, policy, local_token):
        self.policy, self.local_token = policy, local_token
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(("127.0.0.1", 0), ProxyHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Never print exception details, headers or request targets.


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        self.request.settimeout(REQUEST_SECONDS)
        super().setup()
        def expire():
            try:
                self.request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.request_deadline = threading.Timer(REQUEST_SECONDS, expire)
        self.request_deadline.daemon = True
        self.request_deadline.start()

    def finish(self):
        self.request_deadline.cancel()
        super().finish()

    def handle_expect_100(self):
        self.send_error(400)
        return False

    def log_message(self, format, *args):
        pass

    def reply(self, status, body):
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def send_error(self, code, message=None, explain=None):
        self.reply(code, b'{"error":"request-rejected"}')

    def dispatch(self):
        try:
            auth = self.headers.get_all("Authorization", [])
            host = self.headers.get_all("Host", [])
            expected_host = "127.0.0.1:" + str(self.server.server_port)
            if (len(auth) != 1 or not hmac.compare_digest(auth[0], "Bearer " + self.server.local_token)
                    or host != [expected_host] or self.headers.get("Origin") is not None):
                raise ProxyError(401, "local-authentication-required")
            lengths = self.headers.get_all("Content-Length", [])
            if (len(lengths) > 1 or self.headers.get("Transfer-Encoding") is not None
                    or self.headers.get("Upgrade") is not None
                    or self.headers.get("Expect") is not None):
                raise ProxyError(400, "request-framing-refused")
            length = int(lengths[0]) if lengths else 0
            if not 0 <= length <= MAX_BODY:
                raise ProxyError(413, "request-limit-exceeded")
            body = self.rfile.read(length)
            if len(body) != length:
                raise ProxyError(400, "incomplete-request")
            result = self.server.policy.request(self.command, self.path, body,
                                                self.headers.get("Content-Type", ""))
            decode_json(result, (self.server.local_token,))
            self.reply(200, result)
        except ProxyError as exc:
            self.reply(exc.status, json.dumps({"error": exc.code}).encode())
        except (ValueError, OSError, TypeError, UnicodeError, RecursionError):
            self.reply(400, b'{"error":"request-rejected"}')

    do_GET = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_PATCH = dispatch
    do_DELETE = dispatch
    do_CONNECT = dispatch
    do_TRACE = dispatch
    do_HEAD = dispatch
    do_OPTIONS = dispatch


@contextmanager
def serve(backend):
    local_token = secrets.token_urlsafe(32)
    server = ProxyServer(ReadPolicy(backend), local_token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, thread
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
