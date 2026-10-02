"""Actual loopback HTTP fixtures; cloud credentials and endpoints are synthetic."""

from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time
import unittest
from unittest import mock

from fixtures import ORIGIN  # Also exposes the skill's scripts on sys.path.
import credential_proxy as proxy

TOKEN = "synthetic-upstream-credential"
VECTOR = {"status": "success", "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1, "1"]}]}}


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


@contextmanager
def upstream(responder=None):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_read(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append((self.command, self.path, dict(self.headers), body))
            if responder:
                status, value, headers = responder(self.command, self.path, body)
            elif self.path.startswith("/api/datasources/uid/") and "/resources/" not in self.path:
                uid = self.path.rsplit("/", 1)[-1]
                kind = {"logs": "loki", "traces": "tempo"}.get(uid, "custom-prometheus-example")
                status, value, headers = 200, {"uid": uid, "type": kind}, {}
            elif "query=vector%281%29" in self.path:
                status, value, headers = 200, VECTOR, {}
            elif self.path == "/api/datasources":
                status, value, headers = 200, [{"uid": "metrics", "type": "custom-prometheus-example"}], {}
            else:
                status, value, headers = 200, {"status": "success", "data": {}}, {}
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        do_GET = handle_read
        do_POST = handle_read

    server = FixtureServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def connection(host, port, *, timeout):
        if host != "grafana.example.test" or port != 443:
            raise AssertionError("Credential destination changed")
        return http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=timeout)

    try:
        yield proxy.Backend(ORIGIN, TOKEN, connection_factory=connection), calls, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def local_request(server, method="GET", target="/api/datasources", body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    supplied = {"Authorization": "Bearer " + server.local_token}
    supplied.update(headers or {})
    try:
        conn.request(method, target, body=body, headers=supplied)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


class ProxyTests(unittest.TestCase):
    def test_catalog_api_example_and_unsupported_backends_keep_route_boundary(self):
        with upstream() as (backend, calls, _):
            policy = proxy.ReadPolicy(backend)
            self.assertEqual(json.loads(policy.request("GET", "/api/datasources"))[0]["uid"], "metrics")
            self.assertEqual(len(calls), 1)
            for method, path in (
                ("GET", "/api/org"),
                ("POST", "/api/ds/query"),
                ("GET", "/api/datasources/proxy/uid/logs/select/logsql/query"),
            ):
                with self.subTest(path=path), self.assertRaises(proxy.ProxyError) as error:
                    policy.request(method, path)
                self.assertEqual(error.exception.status, 403)
                self.assertEqual(error.exception.code, "route-refused")
            self.assertEqual(len(calls), 1)

    def test_datasource_health_verifies_uid_and_preserves_status(self):
        for status, result in ((200, {"status": "OK"}), (200, {"status": "ERROR"}),
                               (501, {"message": "plugin has no health handler"})):
            def respond(method, path, body):
                if path == "/api/datasources/uid/metrics":
                    return 200, {"uid": "metrics", "type": "custom-plugin"}, {}
                return status, result, {}

            with self.subTest(status=status, result=result), upstream(respond) as (backend, calls, _):
                policy = proxy.ReadPolicy(backend)
                if status == 200:
                    self.assertEqual(json.loads(policy.request("GET", "/api/datasources/uid/metrics/health")), result)
                else:
                    with self.assertRaises(proxy.ProxyError) as error:
                        policy.request("GET", "/api/datasources/uid/metrics/health")
                    self.assertEqual(error.exception.status, status)
                self.assertEqual([call[1] for call in calls],
                                 ["/api/datasources/uid/metrics", "/api/datasources/uid/metrics/health"])

    def test_health_rejects_query_body_method_neighbors_and_unknown_uid(self):
        with upstream(lambda *args: (200, {"uid": "different", "type": "prometheus"}, {})) as (backend, calls, _):
            policy = proxy.ReadPolicy(backend)
            for method, path, body in (
                ("POST", "/api/datasources/uid/metrics/health", b""),
                ("GET", "/api/datasources/uid/metrics/health?", b""),
                ("GET", "/api/datasources/uid/metrics/health?x=1", b""),
                ("GET", "/api/datasources/uid/metrics/health", b"payload"),
                ("GET", "/api/datasources/uid/metrics/health/", b""),
                ("GET", "/api/datasources/uid/metrics/health/extra", b""),
                ("GET", "/api/datasources/uid/metrics/healthcheck", b""),
            ):
                with self.subTest(method=method, path=path), self.assertRaises(proxy.ProxyError):
                    policy.request(method, path, body)
            self.assertEqual(calls, [])
            with self.assertRaises(proxy.ProxyError):
                policy.request("GET", "/api/datasources/uid/metrics/health")
            self.assertEqual(len(calls), 1)

    def test_local_auth_and_header_replacement(self):
        with upstream() as (backend, calls, _), proxy.serve(backend) as (server, thread):
            self.assertEqual(server.server_address[0], "127.0.0.1")
            for headers in ({"Authorization": "Bearer wrong"}, {"Host": "other.example.test"},
                            {"Origin": "https://other.example.test"}):
                self.assertEqual(local_request(server, headers=headers)[0], 401)
            self.assertEqual(calls, [])
            status, body = local_request(server, headers={"Cookie": "private-cookie", "X-Grafana-Org-Id": "999"})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)[0]["uid"], "metrics")
            headers = {key.lower(): value for key, value in calls[0][2].items()}
            self.assertEqual(headers["authorization"], "Bearer " + TOKEN)
            self.assertNotIn("cookie", headers)
            self.assertNotIn("x-grafana-org-id", headers)
            self.assertNotIn(server.local_token, str(headers))
            self.assertNotIn(TOKEN.encode(), body)
            self.assertTrue(thread.is_alive())
        self.assertFalse(thread.is_alive())

    def test_redirect_never_contacts_second_server_or_emits_location(self):
        with upstream() as (_, other_calls, other):
            location = "http://127.0.0.1:" + str(other.server_port) + "/collect"
            with upstream(lambda *_: (302, {}, {"Location": location})) as (backend, calls, _):
                with proxy.serve(backend) as (server, _):
                    status, body = local_request(server)
                self.assertEqual(status, 502)
                self.assertIn(b"redirect-refused", body)
                self.assertNotIn(location.encode(), body)
                self.assertEqual(len(calls), 1)
                self.assertEqual(other_calls, [])

    def test_plain_and_json_escaped_reflection_is_withheld(self):
        for response in ({"token": TOKEN}, {TOKEN: "value"},
                         ('{"token":"' + "".join("\\u%04x" % ord(c) for c in TOKEN) + '"}').encode()):
            with self.subTest(response_type=type(response).__name__):
                with upstream(lambda *_: (200, response, {})) as (backend, _, _):
                    with proxy.serve(backend) as (server, _):
                        status, body = local_request(server)
                    self.assertEqual(status, 502)
                    self.assertNotIn(TOKEN.encode(), body)
                    self.assertIn(b"response-rejected", body)

    def test_auth_failures_withhold_raw_body(self):
        for code in (401, 403, 500):
            with upstream(lambda *_: (code, {"error": TOKEN}, {})) as (backend, _, _):
                with proxy.serve(backend) as (server, _):
                    status, body = local_request(server)
                self.assertEqual(status, code)
                self.assertNotIn(TOKEN.encode(), body)

    def test_only_fixed_read_paths_and_methods_reach_upstream(self):
        with upstream() as (backend, calls, _), proxy.serve(backend) as (server, _):
            cases = [(method, "/api/datasources") for method in ("PUT", "PATCH", "DELETE", "CONNECT", "TRACE", "OPTIONS")]
            cases += [("POST", "/api/ds/query"), ("GET", "/api/admin/settings"),
                      ("GET", "/api/datasources/proxy/uid/traces/api/mcp"),
                      ("GET", "/api/datasources/proxy/uid/logs/loki/api/v1/tail"),
                      ("GET", "/api/search?watch=true"), ("GET", "/api/search?follow=false")]
            for method, target in cases:
                with self.subTest(method=method, target=target):
                    self.assertIn(local_request(server, method, target)[0], (403, 405))
            self.assertEqual(calls, [])

    def test_ambiguous_targets_are_rejected_before_network(self):
        with upstream() as (backend, calls, _):
            policy = proxy.ReadPolicy(backend)
            for target in ("https://other.example.test/api/search", "//other.example.test/api/search",
                           "/api/../api/search", "/api/%2e%2e/api/search", "/api/%252e%252e/api/search",
                           "/api/datasources/proxy/uid/a%2fb/api/v1/query", "/api/search#fragment",
                           "/api/\\search", "/api/%0asearch", "/api/search?" + "a" * proxy.MAX_TARGET):
                with self.subTest(target=target[:80]), self.assertRaises(proxy.ProxyError):
                    policy.request("GET", target)
            self.assertEqual(calls, [])

    def test_custom_prometheus_type_is_verified_before_query_post(self):
        with upstream() as (backend, calls, _), proxy.serve(backend) as (server, _):
            path = "/api/datasources/uid/metrics/resources/api/v1/query"
            status, _ = local_request(server, "POST", path, "query=up", {"Content-Type": "application/x-www-form-urlencoded"})
            self.assertEqual(status, 200)
            self.assertEqual([(c[0], c[1]) for c in calls], [
                ("GET", "/api/datasources/uid/metrics"),
                ("GET", "/api/datasources/uid/metrics/resources/api/v1/query?query=vector%281%29"),
                ("POST", path)])
            self.assertEqual(calls[-1][3], b"query=up")
            self.assertEqual(local_request(server, "POST", path, "query=up", {"Content-Type": "application/json"})[0], 403)
            self.assertEqual(local_request(server, "POST", path, "delete=true", {"Content-Type": "application/x-www-form-urlencoded"})[0], 400)

    def test_unverified_uid_and_non_prometheus_protocol_fail_closed(self):
        def wrong_uid(*_):
            return 200, {"uid": "different", "type": "prometheus"}, {}
        with upstream(wrong_uid) as (backend, calls, _), proxy.serve(backend) as (server, _):
            self.assertEqual(local_request(server, target="/api/datasources/proxy/uid/metrics/api/v1/query?query=up")[0], 403)
            self.assertEqual(len(calls), 1)
        with upstream() as (backend, calls, _), proxy.serve(backend) as (server, _):
            self.assertEqual(local_request(server, target="/api/datasources/proxy/uid/traces/api/v1/query?query=up")[0], 403)
            self.assertEqual(len(calls), 1)

    def test_malformed_prometheus_probe_data_returns_sanitized_refusal(self):
        for data in (None, [], "invalid", 1, True):
            def responder(method, path, body):
                if path == "/api/datasources/uid/metrics":
                    return 200, {"uid": "metrics", "type": "custom-prometheus-example"}, {}
                return 200, {"status": "success", "data": data}, {}
            with self.subTest(data_type=type(data).__name__):
                with upstream(responder) as (backend, calls, _), proxy.serve(backend) as (server, _):
                    status, body = local_request(server, "POST",
                        "/api/datasources/uid/metrics/resources/api/v1/query", "query=up",
                        {"Content-Type": "application/x-www-form-urlencoded"})
                    self.assertEqual(status, 403)
                    self.assertEqual(json.loads(body), {"error": "prometheus-route-not-verified"})
                    self.assertEqual([call[0] for call in calls], ["GET", "GET"])

    def test_loki_get_limit_and_finite_tempo_routes(self):
        with upstream() as (backend, calls, _), proxy.serve(backend) as (server, _):
            target = "/api/datasources/proxy/uid/logs/loki/api/v1/query_range?query=test"
            self.assertEqual(local_request(server, target=target)[0], 200)
            self.assertIn("limit=20", calls[-1][1])
            self.assertEqual(local_request(server, target=target + "&limit=21")[0], 400)
            for suffix in ("/api/search", "/api/search/tags", "/api/v2/search/tag/service.name/values",
                           "/api/v2/traces/0123456789abcdef"):
                self.assertEqual(local_request(server, target="/api/datasources/proxy/uid/traces" + suffix)[0], 200)

    def test_malformed_duplicate_and_oversized_responses_are_rejected(self):
        for value in (b"not json", b'{"a":1,"a":2}', b'{"n":NaN}', b'"' + b"a" * 2048 + b'"'):
            with upstream(lambda *_: (200, value, {})) as (backend, _, _):
                with mock.patch.object(proxy, "MAX_RESPONSE", 1024), proxy.serve(backend) as (server, _):
                    self.assertEqual(local_request(server)[0], 502)

    def test_ambient_proxies_are_ignored_and_tls_factory_is_default(self):
        self.assertIs(proxy.Backend(ORIGIN, TOKEN).connection_factory, http.client.HTTPSConnection)
        with mock.patch.dict("os.environ", {"HTTPS_PROXY": "http://unused.example.test:9"}):
            with upstream() as (backend, calls, _):
                self.assertIsInstance(json.loads(backend.request("GET", "/api/datasources")), list)
                self.assertEqual(len(calls), 1)

    def test_request_framing_and_absolute_connection_deadline(self):
        with upstream() as (backend, calls, _):
            with mock.patch.object(proxy, "REQUEST_SECONDS", 0.2), proxy.serve(backend) as (server, _):
                status, _ = local_request(server, headers={"Transfer-Encoding": "chunked"})
                self.assertEqual(status, 400)
                sock = socket.create_connection(server.server_address, timeout=2)
                try:
                    sock.sendall(b"GET /api/datasources HTTP/1.1\r\n")
                    started = time.monotonic()
                    self.assertEqual(sock.recv(1), b"")
                    self.assertLess(time.monotonic() - started, 1)
                finally:
                    sock.close()
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
