"""Agent setup contract with isolated homes, synthetic auth and local HTTP."""

import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock

from fixtures import FakeSystem, MCP, ORIGIN, SCRIPTS
from common import SetupError, json_bytes
import readiness
import setup
from test_proxy import TOKEN, upstream


class AgentSetupTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSystem()
        self.addCleanup(self.fake.close)

    def resolve(self, **kwargs):
        return setup.resolve_layout(self.fake.home, kwargs.pop("agent", "codex"),
                                    env=self.fake.env, run=self.fake.run, workdir=self.fake.home, **kwargs)

    def test_missing_inputs_are_bounded_json_without_side_effects(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "setup.py"), "--agent", "codex", "--apply"],
                                env=self.fake.env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["fields"], ["user_profile", "grafana_url"])
        self.assertEqual(result.stderr, b"")
        self.assertEqual(list(self.fake.home.iterdir()), [])
        self.assertEqual(self.fake.calls, [])

    def test_unique_owned_binding_reused_without_reading_credentials(self):
        layout = self.fake.apply()
        (layout.state / "iam-token").write_bytes(b"intentionally-invalid")
        (layout.state / "iam-token.json").write_bytes(b"not-json")
        self.fake.calls.clear()
        self.assertEqual(self.resolve(), layout)
        self.assertEqual(self.fake.calls, [])

    def test_ambiguity_requires_selection_and_explicit_inputs_narrow(self):
        first = self.fake.apply()
        second = self.fake.apply(self.fake.layout(server="second"))
        with self.assertRaises(setup.MissingInputs):
            self.resolve()
        self.assertEqual(self.resolve(server="second"), second)
        self.assertEqual(self.resolve(server=first.server), first)
        with self.assertRaisesRegex(SetupError, "origin conflicts"):
            self.resolve(profile=first.profile, grafana_url="https://different.example.test/")

    def test_prepared_binding_can_finish_without_reasking(self):
        self.fake.fail_after_add = True
        with self.assertRaises(SetupError):
            self.fake.apply()
        layout = self.resolve()
        self.fake.apply(layout)
        self.assertEqual(setup.owned_receipt(layout)["phase"], "ready")

    def test_profile_and_origin_select_unique_server_among_different_origins(self):
        first = self.fake.apply()
        other = setup.Layout(first.home, first.agent, first.profile, "https://other.example.test/", "other-server")
        self.fake.apply(other)
        self.assertEqual(self.resolve(profile=first.profile, grafana_url=first.grafana_url), first)
        self.assertEqual(self.resolve(profile=other.profile, grafana_url=other.grafana_url), other)

    def test_foreign_drifted_or_wrong_config_root_is_not_reused(self):
        layout = self.fake.apply()
        config = self.fake.read_config("codex")
        self.fake.write_config("codex", {**config, "mcp_servers": {}})
        with self.assertRaisesRegex(SetupError, "absent"):
            self.resolve()
        self.fake.write_config("codex", config)
        self.fake.env["CODEX_HOME"] = str(self.fake.home / "another-codex")
        with self.assertRaises(SetupError):
            self.resolve()
        self.fake.env.pop("CODEX_HOME")
        receipt = json.loads(layout.receipt.read_bytes())
        receipt["owner"] = "foreign-installer"
        layout.receipt.write_bytes(json_bytes(receipt))
        with self.assertRaisesRegex(SetupError, "ownership"):
            self.resolve()

    def test_symlinked_owned_binding_is_refused(self):
        layout = self.fake.apply()
        origin = layout.state / "origin.json"
        target = layout.state / "origin-copy.json"
        origin.rename(target)
        origin.symlink_to(target)
        with self.assertRaisesRegex(SetupError, "symlink"):
            self.resolve()

    def test_malformed_owned_environment_returns_sanitized_failure(self):
        layout = self.fake.apply()
        receipt = json.loads(layout.receipt.read_bytes())
        config = self.fake.read_config("codex")
        for value in ([], "invalid"):
            receipt["entry"]["env"] = value
            config["mcp_servers"][layout.server] = receipt["entry"]
            self.fake.write_config("codex", config)
            layout.receipt.write_bytes(json_bytes(receipt))
            with self.assertRaisesRegex(SetupError, "invalid runtime bindings"):
                self.resolve()

    def test_both_clients_run_private_readiness_and_cleanup(self):
        for agent in ("codex", "claude"):
            with self.subTest(agent=agent):
                protocol_log = self.fake.root / (agent + "-protocol.jsonl")
                self.fake.env["FAKE_PROTOCOL_LOG"] = str(protocol_log)
                layout = self.fake.apply(self.fake.layout(agent), verify=True)
                self.assertEqual(self.fake.result, {"registration": "ready", "runtime": "ready", "activation": "not checked"})
                messages = [json.loads(line) for line in protocol_log.read_text().splitlines()]
                self.assertEqual([x["method"] for x in messages],
                                 ["initialize", "notifications/initialized", "tools/list",
                                  "resources/list", "resources/templates/list", "tools/call"])
                self.assertEqual(messages[-1]["params"], {"name": "list_datasources", "arguments": {"limit": 1}})
                self.assertFalse(list(layout.state.glob("iam-token.generation.*")))
        events = [json.loads(line) for line in (self.fake.root / "mcp.jsonl").read_text().splitlines()]
        for event in events:
            with self.assertRaises(ProcessLookupError):
                os.kill(event["pid"], 0)

    def test_failed_runtime_retains_registration_and_hides_error_payload(self):
        self.fake.env["FAKE_MCP_MODE"] = "tool-error"
        with contextlib.redirect_stdout(io.StringIO()) as output:
            layout = self.fake.apply(verify=True)
        self.assertEqual(self.fake.result["registration"], "ready")
        self.assertEqual(self.fake.result["runtime"], "failed")
        self.assertEqual(setup.owned_receipt(layout)["phase"], "ready")
        self.assertNotIn("SENTINEL", output.getvalue() + str(self.fake.result))
        self.assertNotIn("login.example", output.getvalue() + str(self.fake.result))

    def test_browser_required_setup_resumes_with_only_sanitized_progress(self):
        marker = self.fake.root / "browser-completed"
        self.fake.env["FAKE_BROWSER_MARKER"] = str(marker)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = setup.apply(self.fake.layout(), self.fake.source, run=self.fake.run,
                                 env=self.fake.env, binary_provider=self.fake.binary, workdir=self.fake.home,
                                 progress=lambda stage: setup.emit({"stage": stage}))
        self.assertTrue(marker.exists())
        self.assertEqual(result["runtime"], "ready")
        self.assertIn("browser sign-in", output.getvalue())
        self.assertNotIn("SENTINEL", output.getvalue())
        self.assertNotIn("login.example", output.getvalue())


class ClaudeSettingsTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSystem()
        self.addCleanup(self.fake.close)
        self.path = self.fake.home / ".claude/settings.json"

    def write(self, value):
        self.path.parent.mkdir(mode=0o700, exist_ok=True)
        self.path.write_bytes(json_bytes(value))
        self.path.chmod(0o600)

    def test_setup_does_not_create_settings_or_timeout(self):
        self.fake.apply(self.fake.layout("claude"))
        self.assertFalse(self.path.exists())
        self.fake.apply(self.fake.layout("codex"))
        entry = self.fake.read_config("codex")["mcp_servers"]["grafana-nebius"]
        self.assertNotIn("startup_timeout_sec", entry)

    def test_existing_settings_are_byte_preserved(self):
        self.write({"env": {"MCP_TIMEOUT": "10", "UNCHANGED": "value"},
                    "permissions": {"deny": ["Bash(secret:*)"]}, "hooks": {"Stop": []}})
        before = self.path.read_bytes()
        self.fake.apply(self.fake.layout("claude"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_concurrent_settings_writer_is_never_overwritten(self):
        self.write({"env": {"KEEP": "before"}})
        run = self.fake.run

        def concurrent_writer(args, **kwargs):
            result = run(args, **kwargs)
            if args[:3] == ["claude", "mcp", "add"]:
                self.write({"env": {"KEEP": "concurrent"}})
            return result

        setup.apply(self.fake.layout("claude"), self.fake.source, run=concurrent_writer,
                    env=self.fake.env, binary_provider=self.fake.binary, verifier=lambda *args, **kwargs: None)
        self.assertEqual(json.loads(self.path.read_bytes()), {"env": {"KEEP": "concurrent"}})

    def test_settings_symlink_is_not_touched(self):
        self.write({"env": {"KEEP": "value"}})
        other = self.fake.home / "other.json"
        self.path.rename(other)
        self.path.symlink_to(other)
        before = other.read_bytes()
        self.fake.apply(self.fake.layout("claude"))
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(other.read_bytes(), before)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSystem()
        self.addCleanup(self.fake.close)

    def test_malformed_error_missing_tool_and_stalled_runtime_are_bounded(self):
        layout = self.fake.apply()
        entry = self.fake.read_config("codex")["mcp_servers"][layout.server]
        for mode in ("wrong-id", "protocol-error", "missing-tool", "oversized", "stall"):
            with self.subTest(mode=mode):
                started = time.monotonic()
                with self.assertRaises(readiness.ReadinessError) as error:
                    readiness.verify(entry, env={**self.fake.env, "FAKE_MCP_MODE": mode}, home=self.fake.home, timeout=2)
                self.assertLess(time.monotonic() - started, 15)
                self.assertNotIn("SENTINEL", str(error.exception))
        for event in map(json.loads, (self.fake.root / "mcp.jsonl").read_text().splitlines()):
            with self.assertRaises(ProcessLookupError):
                os.kill(event["pid"], 0)

    def test_private_readiness_traverses_stdio_proxy_and_http(self):
        # Declared fixture: bridge with a loopback transport adapter. The full
        # production wrapper is exercised separately by the both-client test.
        binary = self.fake.root / "http-mcp"
        binary.write_text(MCP)
        binary.chmod(0o700)
        driver = self.fake.root / "bridge-driver.py"
        with upstream() as (_, calls, server):
            driver.write_text(
                "import http.client, os, sys\n"
                f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
                "from credential_proxy import Backend\nfrom mcp_bridge import run\n"
                f"backend = Backend({ORIGIN!r}, {TOKEN!r}, connection_factory=lambda host, port, timeout: "
                f"http.client.HTTPConnection('127.0.0.1', {server.server_port}, timeout=timeout))\n"
                f"sys.exit(run({str(binary)!r}, backend, inherited=dict(os.environ)))\n"
            )
            entry = {"command": sys.executable, "args": [str(driver)], "env": {"FAKE_MCP_HTTP": "1"}}
            readiness.verify(entry, env=self.fake.env, home=self.fake.home, timeout=10)
            self.assertEqual([call[1] for call in calls], ["/api/datasources"])
            self.assertEqual(calls[0][2]["Authorization"], "Bearer " + TOKEN)

    def test_cli_failure_output_is_never_relayed(self):
        self.fake.env["FAKE_FAIL_MINT"] = "1"
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(SetupError) as error:
            self.fake.apply()
        self.assertNotIn("SENTINEL", output.getvalue() + str(error.exception))

    def test_keyboard_interrupt_stops_verification_process(self):
        self.fake.apply()
        entry = self.fake.read_config("codex")["mcp_servers"]["grafana-nebius"]
        with mock.patch.object(readiness.Conversation, "verify", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            readiness.verify(entry, env=self.fake.env, home=self.fake.home)

    def test_stopped_wrapper_is_resumed_to_clean_separate_bridge_group(self):
        self.fake.apply()
        entry = self.fake.read_config("codex")["mcp_servers"]["grafana-nebius"]
        groups = []
        protocol_log = self.fake.root / "stalled-protocol.jsonl"
        env = {**self.fake.env, "FAKE_MCP_MODE": "stall", "FAKE_PROTOCOL_LOG": str(protocol_log)}

        def pause(conversation):
            conversation.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            log = self.fake.root / "mcp.jsonl"
            deadline = time.monotonic() + 8
            while not protocol_log.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(protocol_log.exists())
            self.assertEqual(json.loads(protocol_log.read_text().splitlines()[0])["method"], "initialize")
            child = json.loads(log.read_text().splitlines()[0])["pid"]
            groups.append(os.getpgid(child))
            os.kill(conversation.process.pid, signal.SIGSTOP)
            raise readiness.ReadinessError("Synthetic cancellation after suspension.")

        try:
            with mock.patch.object(readiness.Conversation, "verify", pause), self.assertRaises(readiness.ReadinessError):
                readiness.verify(entry, env=env, home=self.fake.home, timeout=10)
            for group in groups:
                with self.assertRaises(ProcessLookupError):
                    os.killpg(group, 0)
        finally:
            for group in groups:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main()
