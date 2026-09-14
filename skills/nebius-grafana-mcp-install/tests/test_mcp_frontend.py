"""Protocol routing and bounded preparation, using public or synthetic data only."""

import copy
import json
import os
import selectors
import threading
import unittest

from fixtures import FakeSystem, SCRIPTS
from common import SetupError
from mcp_frontend import DISCOVERY, Frontend, PREPARING, PROTOCOL, exchange, load_catalog


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(SCRIPTS)
        self.front = Frontend(self.catalog)

    def client(self, method, params=None, identifier=1):
        return self.front.client({"jsonrpc": "2.0", "id": identifier,
                                  "method": method, "params": params or {}})

    def initialize(self):
        replies, requests = self.client("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}})
        self.assertEqual(replies[0]["result"], self.catalog["initialize"])
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
            self.assertEqual(replies[0]["result"], {field: self.catalog[field]})
            self.assertFalse(requests)
        self.assertEqual(self.client("ping")[0][0]["result"], {})
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
            self.assertEqual(response["result"], self.catalog["initialize"])
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
