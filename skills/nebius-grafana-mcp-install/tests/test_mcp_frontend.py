"""Protocol routing and bounded preparation, using public or synthetic data only."""

import copy
import json
import os
import selectors
import threading
import unittest

from fixtures import FakeSystem, SCRIPTS
from common import SetupError
from mcp_frontend import DISCOVERY, Frontend, PREPARING, PROTOCOL, exchange, load_catalog, project_catalog


class CatalogProjectionTests(unittest.TestCase):
    def setUp(self):
        self.raw = load_catalog(SCRIPTS)

    def test_only_reviewed_description_leaves_change_without_mutating_raw(self):
        before = copy.deepcopy(self.raw)
        public = project_catalog(self.raw)
        self.assertEqual(self.raw, before)
        descriptions = {
            "grafana_api_request", "get_dashboard_panel_queries",
            "list_loki_label_names", "list_loki_label_values", "query_loki_logs",
            "query_loki_stats", "query_loki_patterns", "list_prometheus_label_names",
            "list_prometheus_label_values", "list_prometheus_metric_names",
            "list_prometheus_metric_metadata", "query_prometheus", "query_prometheus_histogram",
        }
        parameters = {
            ("grafana_api_request", "endpoint"), ("grafana_api_request", "headers"),
            ("list_loki_label_names", "matcher"), ("list_loki_label_values", "matcher"),
            ("query_loki_logs", "limit"),
            *((tool, "projectName") for tool in descriptions if "prometheus" in tool),
        }
        self.assertNotEqual(public["initialize"]["instructions"], before["initialize"]["instructions"])
        public["initialize"]["instructions"] = before["initialize"]["instructions"]
        for tool, original in zip(public["tools"], before["tools"], strict=True):
            name = tool["name"]
            if name in descriptions:
                self.assertNotEqual(tool["description"], original["description"])
                tool["description"] = original["description"]
            for expected_name, parameter in parameters:
                if name == expected_name:
                    prop = tool["inputSchema"]["properties"][parameter]
                    original_prop = original["inputSchema"]["properties"][parameter]
                    self.assertNotEqual(prop["description"], original_prop["description"])
                    prop["description"] = original_prop["description"]
        self.assertEqual(public, before)
        public["tools"][0]["name"] = "modified-copy"
        self.assertEqual(self.raw, before)

    def test_client_guidance_matches_restricted_capabilities(self):
        public = project_catalog(self.raw)
        tools = {tool["name"]: tool for tool in public["tools"]}
        instructions = public["initialize"]["instructions"]
        self.assertIn("read-only", instructions)
        self.assertNotIn("update, and create", instructions)
        api = tools["grafana_api_request"]
        self.assertIn("allowlist", api["description"])
        self.assertNotIn("any Grafana API", api["description"])
        self.assertIn("/api/datasources", api["inputSchema"]["properties"]["endpoint"]["description"])
        self.assertNotIn("/api/org", json.dumps(api))
        self.assertIn("leave unset", api["inputSchema"]["properties"]["headers"]["description"])
        self.assertNotIn("run_panel_query", tools["get_dashboard_panel_queries"]["description"])
        for name, tool in tools.items():
            if "loki" in name:
                self.assertNotIn("VictoriaLogs", json.dumps(tool))
                self.assertNotIn("LogsQL", json.dumps(tool))
            if "prometheus" in name:
                self.assertIn("verified Prometheus HTTP routes", tool["description"])
                self.assertIn("unsupported", tool["inputSchema"]["properties"]["projectName"]["description"])
        self.assertIn("maximum 20", tools["query_loki_logs"]["inputSchema"]["properties"]["limit"]["description"])

    def test_missing_or_non_string_projection_targets_fail_closed(self):
        for target in ("initialize", "tool", "parameter"):
            for missing in (True, False):
                raw = copy.deepcopy(self.raw)
                api = next(t for t in raw["tools"] if t["name"] == "grafana_api_request")
                obj, key = {
                    "initialize": (raw["initialize"], "instructions"),
                    "tool": (api, "description"),
                    "parameter": (api["inputSchema"]["properties"]["endpoint"], "description"),
                }[target]
                if missing:
                    del obj[key]
                else:
                    obj[key] = 7
                with self.subTest(target=target, missing=missing), self.assertRaises(SetupError):
                    project_catalog(raw)

    def test_reduced_catalog_keeps_its_tools_and_schema(self):
        raw = copy.deepcopy(self.raw)
        raw["tools"] = [t for t in raw["tools"] if t["name"] == "list_datasources"]
        self.assertEqual(project_catalog(raw)["tools"], raw["tools"])


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(SCRIPTS)
        self.public = project_catalog(self.catalog)
        self.front = Frontend(self.catalog)

    def client(self, method, params=None, identifier=1):
        return self.front.client({"jsonrpc": "2.0", "id": identifier,
                                  "method": method, "params": params or {}})

    def initialize(self):
        replies, requests = self.client("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}})
        self.assertEqual(replies[0]["result"], self.public["initialize"])
        self.assertFalse(requests)
        self.front.client({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def bootstrap(self):
        request = self.front.bootstrap()
        values = [self.catalog["initialize"], *({field: self.catalog[field]} for field, _ in DISCOVERY.values())]
        for value in values:
            replies, requests = self.front.backend({"jsonrpc": "2.0", "id": request["id"], "result": value})
            self.assertFalse(replies)
            if requests:
                request = requests[-1]
        self.assertTrue(self.front.ready)

    def test_pinned_discovery_and_ping_need_no_backend(self):
        self.initialize()
        for method, (field, _) in DISCOVERY.items():
            replies, requests = self.client(method)
            self.assertEqual(replies[0]["result"], {field: self.public[field]})
            self.assertFalse(requests)
        self.assertEqual(self.client("ping")[0][0]["result"], {})
        self.assertFalse(self.front.ready)

    def test_ready_discovery_matches_preparation_discovery(self):
        self.initialize()
        before = {method: self.client(method)[0] for method in DISCOVERY}
        self.bootstrap()
        for method, replies in before.items():
            self.assertEqual(self.client(method), (replies, []))

    def test_projected_backend_metadata_cannot_mask_drift(self):
        request = self.front.bootstrap()
        with self.assertRaisesRegex(SetupError, "initialization differs"):
            self.front.backend({"id": request["id"], "result": self.public["initialize"]})
        self.assertFalse(self.front.ready)
        self.front = Frontend(self.catalog)
        request = self.front.bootstrap()
        _, requests = self.front.backend({"id": request["id"], "result": self.catalog["initialize"]})
        changed = copy.deepcopy(self.catalog["tools"])
        api = next(t for t in changed if t["name"] == "grafana_api_request")
        api["description"] = "Unexpected upstream description hidden by projection"
        with self.assertRaisesRegex(SetupError, "discovery differs"):
            self.front.backend({"id": requests[-1]["id"], "result": {"tools": changed}})
        self.assertFalse(self.front.ready)

    def test_preparing_operations_are_retryable_and_never_queued(self):
        self.initialize()
        for method, params in (("tools/call", {"name": "list_datasources", "arguments": {}}),
                               ("resources/read", {"uri": self.catalog["resources"][0]["uri"]})):
            replies, requests = self.client(method, params)
            self.assertEqual(replies[0]["error"], PREPARING)
            self.assertFalse(requests)
            self.assertFalse(self.front.pending)

    def test_catalog_mismatch_cannot_enable_operations(self):
        for field in ("initialize", "tools", "resources", "resourceTemplates"):
            with self.subTest(field=field):
                self.front = Frontend(copy.deepcopy(self.catalog))
                self.front.catalog[field] = {} if field == "initialize" else [{"mismatch": True}]
                with self.assertRaises(SetupError):
                    self.bootstrap()
                self.assertFalse(self.front.ready)

    def test_paginated_catalog_validates_all_pages(self):
        request = self.front.bootstrap()
        _, requests = self.front.backend({"id": request["id"], "result": self.catalog["initialize"]})
        request = requests[-1]
        _, requests = self.front.backend({"id": request["id"], "result": {
            "tools": self.catalog["tools"][:3], "nextCursor": "next"}})
        self.assertEqual(requests[0]["params"], {"cursor": "next"})
        _, requests = self.front.backend({"id": requests[0]["id"], "result": {"tools": self.catalog["tools"][3:]}})
        self.assertEqual(requests[0]["method"], "resources/list")
        self.assertFalse(self.front.ready)

    def test_id_mapping_concurrent_calls_cancellation_and_resource_reads(self):
        self.initialize()
        self.bootstrap()
        _, first = self.client("tools/call", {"name": "list_datasources", "arguments": {}}, identifier="user-id")
        _, second = self.client("resources/read", {"uri": self.catalog["resources"][0]["uri"]}, identifier=1)
        replies, _ = self.front.backend({"jsonrpc": "2.0", "id": second[0]["id"], "result": {"contents": []}})
        self.assertEqual(replies[0]["id"], 1)
        _, cancellation = self.front.client({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                              "params": {"requestId": "user-id"}})
        self.assertEqual(cancellation[0]["params"]["requestId"], first[0]["id"])
        self.assertEqual(self.front.backend({"id": first[0]["id"], "result": {}}), ([], []))
        self.assertFalse(self.front.pending)
        with self.assertRaises(SetupError):
            self.front.backend({"method": "notifications/tools/list_changed"})

    def test_invalid_client_negotiation_and_unknown_methods_are_bounded(self):
        self.assertEqual(self.client("initialize")[0][0]["error"]["code"], -32602)
        self.assertEqual(self.client("tools/list")[0][0]["error"]["code"], -32600)
        self.initialize()
        self.assertEqual(self.client("tools/list", {"cursor": "unknown"})[0][0]["error"]["code"], -32602)
        self.assertEqual(self.client("tools/call", {"name": "unknown"})[0][0]["error"]["code"], -32602)
        self.assertEqual(self.client("resources/subscribe")[0][0]["error"]["code"], -32601)

    def test_protocol_service_responds_while_backend_is_blocked_then_times_out(self):
        pairs = [os.pipe() for _ in range(4)]
        client_in, client_write = pairs[0]
        client_read, client_out = pairs[1]
        backend_read, backend_in = pairs[2]
        backend_out, backend_write = pairs[3]
        errors = []

        def serve():
            try:
                exchange(self.catalog, backend_in, backend_out, threading.Event(),
                         stdin_fd=client_in, stdout_fd=client_out, prepare_seconds=0.5)
            except SetupError as exc:
                errors.append(str(exc))

        worker = threading.Thread(target=serve)
        try:
            worker.start()
            os.write(client_write, b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{}}}\n')
            with selectors.DefaultSelector() as selector:
                selector.register(client_read, selectors.EVENT_READ)
                self.assertTrue(selector.select(0.4))
            response = json.loads(os.read(client_read, 65536))
            self.assertEqual(response["result"], self.public["initialize"])
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, ["MCP preparation timed out; invoke setup again."])
        finally:
            worker.join(2)
            for pair in pairs:
                for fd in pair:
                    os.close(fd)

    def test_catalog_is_bound_to_pinned_artifacts_and_capabilities(self):
        fake = FakeSystem()
        self.addCleanup(fake.close)
        path = fake.source / "artifacts.json"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(SetupError, "pinned runtime"):
            load_catalog(fake.source)
