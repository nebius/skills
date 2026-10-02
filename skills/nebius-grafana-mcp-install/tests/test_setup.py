import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import time
import unittest
from unittest import mock

from fixtures import FakeSystem, SCRIPTS
from common import SetupError, clean_env, command, digest, json_bytes, read_bytes
import materialize
import runtime_check
import setup
import token_state


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSystem()
        self.addCleanup(self.fake.close)

    def test_missing_required_inputs_refuse_before_side_effects(self):
        for args in (
            [str(SCRIPTS / "ensure-local-config.sh"), "--agent", "codex", "--user-profile", "testing-human", "--apply"],
            [str(SCRIPTS / "run-nebius-grafana-mcp.sh")],
            [str(SCRIPTS / "run-nebius-grafana-mcp.sh"), "--refresh-token-only"],
        ):
            result = subprocess.run(args, env=self.fake.env, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0, result.stderr.decode())
        self.assertFalse((self.fake.root / "commands.jsonl").exists())
        self.assertEqual(list(self.fake.home.iterdir()), [])

    def test_help_does_not_inspect_or_create_state(self):
        for filename in ("ensure-local-config.sh", "run-nebius-grafana-mcp.sh"):
            result = subprocess.run([str(SCRIPTS / filename), "--help"], env=self.fake.env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(list(self.fake.home.iterdir()), [])
        self.assertFalse((self.fake.root / "commands.jsonl").exists())

    def test_check_is_local_only(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            status = setup.check(self.fake.layout(), self.fake.source, run=self.fake.run,
                                 env=self.fake.env, workdir=self.fake.home)
        self.assertEqual(status, 3)
        self.assertIn("not started", output.getvalue())
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(list(self.fake.home.iterdir()), [])

    def test_missing_owned_binary_is_discoverable_and_repaired_by_normal_apply(self):
        layout = self.fake.apply()
        entry = self.fake.read_config("codex")["mcp_servers"][layout.server]
        binary = Path(entry["env"]["NEBIUS_GRAFANA_MCP_BINARY"])
        binary.unlink()
        self.fake.calls.clear()
        self.assertEqual(setup.resolve_layout(self.fake.home, "codex", env=self.fake.env,
                                              run=self.fake.run, workdir=self.fake.home), layout)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(setup.check(layout, self.fake.source, run=self.fake.run,
                                         env=self.fake.env, workdir=self.fake.home), 3)
        self.assertTrue(json.loads(output.getvalue())["update_required"])
        self.assertFalse(binary.exists())
        self.assertEqual(self.fake.calls, [["codex", "mcp", "get", layout.server, "--json"]])
        self.fake.apply(layout, update=True)
        self.assertTrue(binary.exists())
        self.assertTrue(runtime_check.validate(layout.home, Path(entry["command"]).parent, entry["env"]))

    def test_repeated_token_does_not_receive_a_later_observation_time(self):
        layout = self.fake.apply()
        token = layout.state / "iam-token"
        original = json.loads(Path(str(token) + ".json").read_bytes())
        token.write_bytes(token.read_bytes().rstrip(b"\n"))
        token_state.record(token, time.time(), self.fake.home)
        self.assertEqual(json.loads(Path(str(token) + ".json").read_bytes()), original)

    def test_check_after_source_update_reports_setup_needed_without_staging(self):
        layouts = [self.fake.apply(self.fake.layout(agent)) for agent in ("codex", "claude")]
        source = self.fake.source / "common.py"
        source.write_bytes(source.read_bytes() + b"\n# synthetic skill update\n")
        before = {p.relative_to(self.fake.home): p.read_bytes()
                  for p in self.fake.home.rglob("*") if p.is_file()}
        self.fake.calls.clear()
        for layout in layouts:
            with self.subTest(agent=layout.agent), contextlib.redirect_stdout(io.StringIO()) as output:
                status = setup.check(layout, self.fake.source, run=self.fake.run,
                                     env=self.fake.env, workdir=self.fake.home)
                self.assertEqual(status, 3)
                self.assertIn("setup or repair needed", output.getvalue())
                self.assertNotIn("locally matches", output.getvalue())
        self.assertEqual(self.fake.calls, [])
        after = {p.relative_to(self.fake.home): p.read_bytes()
                 for p in self.fake.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_check_rejects_corruption_of_the_expected_installed_bundle(self):
        layout = self.fake.apply()
        args, _ = self.fake.runtime_command(layout)
        source = Path(args[0]).parent / "common.py"
        source.write_bytes(source.read_bytes() + b"\n# synthetic corruption\n")
        self.fake.calls.clear()
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(SetupError, "integrity"):
            setup.check(layout, self.fake.source, run=self.fake.run,
                        env=self.fake.env, workdir=self.fake.home)
        self.assertEqual(self.fake.calls, [])

    def test_explicit_update_renews_even_a_recent_cached_token(self):
        layout = self.fake.apply()
        self.fake.apply(layout)
        self.assertEqual((self.fake.root / "counter").read_text(), "1")
        self.fake.apply(layout, update=True)
        self.assertEqual((self.fake.root / "counter").read_text(), "2")

    def test_origin_binding_cannot_be_changed_by_update(self):
        layout = self.fake.apply()
        self.fake.calls.clear()
        other = setup.Layout(layout.home, layout.agent, layout.profile, "https://other.example.test/")
        with self.assertRaises(SetupError):
            self.fake.apply(other, update=True)
        self.assertEqual(self.fake.calls, [])

    def test_malformed_origin_fails_before_any_setup(self):
        for origin in ("", "http://grafana.example.test", "https://user@grafana.example.test",
                       "https://127.0.0.1", "https://grafana.example.test/api",
                       "https://grafana.example.test/?token=synthetic"):
            with self.assertRaises(SetupError):
                setup.Layout(self.fake.home, "codex", "testing-human", origin)
        self.assertEqual(list(self.fake.home.iterdir()), [])
        self.assertEqual(self.fake.calls, [])

    def test_ready_check_does_not_read_credential_payload_or_metadata(self):
        layout = self.fake.apply()
        (layout.state / "iam-token").write_bytes(b"invalid synthetic token")
        (layout.state / "iam-token.json").write_bytes(b"invalid metadata")
        self.fake.calls.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            status = setup.check(layout, self.fake.source, run=self.fake.run,
                                 env=self.fake.env, workdir=self.fake.home)
        self.assertEqual(status, 0)
        self.assertEqual([args[:3] for args in self.fake.calls], [["codex", "mcp", "get"]])

    def test_invalid_observation_metadata_fails_closed(self):
        layout = self.fake.apply()
        path = layout.state / "iam-token"
        metadata = layout.state / "iam-token.json"
        original = json.loads(metadata.read_bytes())
        for value in ("yesterday", True, None, -1, time.time() + 100, float("nan"), float("inf")):
            metadata.write_bytes(json_bytes({**original, "observed_at": value}))
            with self.assertRaises(SetupError):
                token_state.inspect(path)
        metadata.write_bytes(json_bytes({**original, "version": 1}))
        with self.assertRaises(SetupError):
            token_state.inspect(path)

    def test_cancellation_stops_isolated_command_descendants(self):
        script = self.fake.root / "caller.py"
        child = self.fake.root / "child.py"
        marker = self.fake.root / "child-started"
        late_write = self.fake.root / "must-not-exist"
        child.write_text(
            "import pathlib, time\n"
            f"pathlib.Path({str(marker)!r}).write_text('started')\n"
            "time.sleep(3)\n"
            f"pathlib.Path({str(late_write)!r}).write_text('survived')\n"
        )
        script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
            "from common import command\n"
            "try:\n"
            f"    command([{sys.executable!r}, '-B', {str(child)!r}], timeout=20)\n"
            "except KeyboardInterrupt:\n"
            "    sys.exit(130)\n"
        )
        process = subprocess.Popen([sys.executable, "-B", str(script)], env=self.fake.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            process.send_signal(signal.SIGINT)
            _, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 130, stderr.decode())
            time.sleep(3)
            self.assertFalse(late_write.exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_each_client_apply_is_idempotent_and_preserves_unrelated_settings(self):
        for agent in ("codex", "claude"):
            with self.subTest(agent=agent):
                group = "mcp_servers" if agent == "codex" else "mcpServers"
                original = {"model": "fixture", group: {"unrelated": {"command": "unrelated", "env": {"API_KEY": "SENTINEL-SECRET"}}}}
                self.fake.write_config(agent, original)
                layout = self.fake.apply(self.fake.layout(agent))
                first_config = self.fake.path(agent).read_bytes()
                first_token = (layout.state / "iam-token").read_bytes()
                self.fake.calls.clear()
                self.fake.apply(layout)
                self.assertEqual(self.fake.path(agent).read_bytes(), first_config)
                self.assertEqual((layout.state / "iam-token").read_bytes(), first_token)
                self.assertEqual(self.fake.read_config(agent)[group]["unrelated"], original[group]["unrelated"])
                self.assertFalse(any(call[1:3] in (["mcp", "add"], ["mcp", "remove"]) and "--help" not in call for call in self.fake.calls))
                self.assertFalse(any(call[:3] == ["claude", "mcp", "get"] for call in self.fake.calls))
        self.assertNotEqual(self.fake.layout("codex").state, self.fake.layout("claude").state)
        codex = self.fake.read_config("codex")["mcp_servers"]["grafana-nebius"]
        claude = self.fake.read_config("claude")["mcpServers"]["grafana-nebius"]
        self.assertEqual(codex["command"], claude["command"])
        self.assertNotEqual(codex["env"]["GRAFANA_TOKEN_FILE"], claude["env"]["GRAFANA_TOKEN_FILE"])

    def test_unowned_collision_fails_before_auth_or_state_creation(self):
        for agent in ("codex", "claude"):
            group = "mcp_servers" if agent == "codex" else "mcpServers"
            self.fake.write_config(agent, {group: {"grafana-nebius": {"command": "/donor/wrapper"}}})
            before = self.fake.path(agent).read_bytes()
            with self.assertRaisesRegex(SetupError, "existing installation"):
                self.fake.apply(self.fake.layout(agent))
            self.assertEqual(self.fake.path(agent).read_bytes(), before)
        self.assertEqual(self.fake.calls, [])
        self.assertFalse((self.fake.home / ".config").exists())

    def test_partial_codex_add_recovers_without_readding_or_deleting(self):
        self.fake.fail_after_add = True
        with self.assertRaisesRegex(SetupError, "Injected interruption"):
            self.fake.apply()
        entry = self.fake.read_config("codex")["mcp_servers"]["grafana-nebius"]
        self.assertNotIn("startup_timeout_sec", entry)
        self.fake.calls.clear()
        self.fake.apply()
        self.assertNotIn("startup_timeout_sec", self.fake.read_config("codex")["mcp_servers"]["grafana-nebius"])
        self.assertFalse(any(call[1:3] == ["mcp", "remove"] for call in self.fake.calls))
        self.assertEqual(json.loads(self.fake.layout().receipt.read_bytes())["phase"], "ready")

    def test_explicit_owned_update_and_unknown_drift_refusal(self):
        layout = self.fake.apply()
        old_command = self.fake.read_config("codex")["mcp_servers"][layout.server]["command"]
        with (self.fake.source / "common.py").open("a") as output:
            output.write("\n# fixture version two\n")
        with self.assertRaisesRegex(SetupError, "--apply --update"):
            self.fake.apply(layout)
        self.fake.apply(layout, update=True)
        document = self.fake.read_config("codex")
        self.assertNotEqual(document["mcp_servers"][layout.server]["command"], old_command)
        document["mcp_servers"][layout.server]["env"]["UNEXPECTED"] = "SENTINEL-SECRET"
        self.fake.write_config("codex", document)
        with self.assertRaisesRegex(SetupError, "changed outside"):
            self.fake.apply(layout, update=True)

    def test_concurrent_configuration_drift_is_retained_and_reported(self):
        self.fake.add_unrelated_drift = True
        with self.assertRaisesRegex(SetupError, "Unrelated configuration changed"):
            self.fake.apply()
        self.assertEqual(self.fake.read_config("codex")["concurrent_setting"], "preserve-me")

    def test_claude_native_initialization_metadata_only_allowed_for_missing_config(self):
        original_run = self.fake.run
        def native_initialization(args, **kwargs):
            result = original_run(args, **kwargs)
            if args[:3] == ["claude", "mcp", "add"] and "--help" not in args:
                doc = self.fake.read_config("claude")
                doc["migrationVersion"] = 1
                self.fake.write_config("claude", doc)
            return result
        self.fake.run = native_initialization
        self.fake.apply(self.fake.layout("claude"))
        self.assertEqual(self.fake.read_config("claude")["migrationVersion"], 1)
        # A second registration cannot silently change established metadata.
        doc = self.fake.read_config("claude")
        doc["migrationVersion"] = 2
        self.fake.write_config("claude", doc)
        with self.assertRaisesRegex(SetupError, "Unrelated configuration changed"):
            self.fake.apply(self.fake.layout("claude", server="second-server"))

    def test_identity_change_does_not_replace_binding(self):
        layout = self.fake.apply()
        before = (layout.state / "identity").read_bytes()
        self.fake.env["FAKE_CHANGED_ID"] = "1"
        with self.assertRaisesRegex(SetupError, "identity changed"):
            self.fake.apply(layout)
        self.assertEqual((layout.state / "identity").read_bytes(), before)

    def test_malformed_json_and_shadowing_never_disclose_secrets(self):
        path = self.fake.path("claude")
        path.write_text('{"secret": "SENTINEL-SECRET", invalid')
        path.chmod(0o600)
        with self.assertRaises(SetupError) as caught:
            self.fake.apply(self.fake.layout("claude"))
        self.assertNotIn("SENTINEL", str(caught.exception))
        self.fake.write_config("claude", {"projects": {"fixture": {"mcpServers": {"grafana-nebius": {"command": "other"}}}}})
        with self.assertRaisesRegex(SetupError, "local-scope"):
            self.fake.apply(self.fake.layout("claude"))
        self.assertEqual(self.fake.calls, [])

    def test_secret_cli_errors_are_sanitized(self):
        self.fake.env["FAKE_FAIL_MINT"] = "1"
        with self.assertRaises(SetupError) as caught:
            self.fake.apply()
        self.assertNotIn("SENTINEL", str(caught.exception))
        self.assertFalse(self.fake.path("codex").exists())

    def test_environment_sanitization_preserves_harness_attribution(self):
        with mock.patch.dict(os.environ, {"NEBIUS_IAM_TOKEN": "secret", "GRAFANA_EXTRA_HEADERS": "secret", "AI_AGENT": "harness"}):
            env = clean_env("claude")
        self.assertNotIn("NEBIUS_IAM_TOKEN", env)
        self.assertNotIn("GRAFANA_EXTRA_HEADERS", env)
        self.assertEqual(env["AI_AGENT"], "harness")

    def test_unsafe_names_and_paths_are_rejected(self):
        for server in ("dot.name", "colon:name", "../escape", "a\nname"):
            with self.assertRaises(SetupError):
                self.fake.layout(server=server)
        (self.fake.home / ".config").symlink_to(self.fake.root)
        with self.assertRaises(SetupError):
            self.fake.apply()

    def test_invalid_server_names_fail_before_commands_or_state_changes(self):
        for agent in ("codex", "claude"):
            for server in ("--help", "_monitoring"):
                for action in ("--check", "--apply"):
                    with self.subTest(agent=agent, server=server, action=action):
                        fake = FakeSystem()
                        self.addCleanup(fake.close)
                        result = subprocess.run(
                            [sys.executable, "-B", str(SCRIPTS / "setup.py"),
                             "--agent", agent, "--user-profile", "testing-human",
                             "--grafana-url", "https://grafana.example.test",
                             "--mcp-server-name=" + server, action],
                            env=fake.env, capture_output=True, timeout=10,
                        )
                        self.assertEqual(result.returncode, 1, result.stderr.decode())
                        self.assertFalse((fake.root / "commands.jsonl").exists())
                        self.assertEqual(list(fake.home.iterdir()), [])

    def test_supported_custom_names_keep_both_clients_operational(self):
        for agent in ("codex", "claude"):
            with self.subTest(agent=agent):
                layout = self.fake.apply(self.fake.layout(agent, server="g-1_monitoring"))
                self.fake.apply(layout)
                args, env = self.fake.runtime_command(layout)
                runtime_check.validate(self.fake.home, Path(args[0]).parent, env)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(setup.check(layout, self.fake.source, run=self.fake.run,
                                                 env=self.fake.env, workdir=self.fake.home), 0)

    def test_symlink_source_is_staged_and_tampered_bundle_is_rejected(self):
        link = self.fake.root / "installed-skill-scripts"
        link.symlink_to(self.fake.source, target_is_directory=True)
        root = self.fake.home / "runtime"
        bundle = materialize.materialize(link, root, self.fake.home)
        self.assertFalse(bundle.is_symlink())
        self.assertEqual(bundle.name, materialize.bundle_id(materialize.source_files(self.fake.source)))
        with (bundle / "common.py").open("a") as stream:
            stream.write("\n# tampered\n")
        with self.assertRaisesRegex(SetupError, "integrity"):
            materialize.materialize(link, root, self.fake.home)

    def test_runtime_attestation_checks_aggregate_digest_and_binary_ancestors(self):
        layout = self.fake.apply()
        args, env = self.fake.runtime_command(layout)
        directory = Path(args[0]).parent
        runtime_check.validate(self.fake.home, directory, env)
        binary_parent = Path(env["NEBIUS_GRAFANA_MCP_BINARY"]).parent
        binary_parent.chmod(0o777)
        with self.assertRaises(SetupError):
            runtime_check.validate(self.fake.home, directory, env)
        binary_parent.chmod(0o700)
        runtime_file = directory / "common.py"
        runtime_file.write_bytes(runtime_file.read_bytes() + b"\n# changed\n")
        manifest_file = directory / "manifest.json"
        manifest = json.loads(manifest_file.read_bytes())
        manifest["common.py"] = digest(runtime_file.read_bytes())
        manifest_file.write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(SetupError, "identity or location"):
            runtime_check.validate(self.fake.home, directory, env)

    def test_token_freshness_uses_observation_not_mtime(self):
        layout = self.fake.apply()
        path = layout.state / "iam-token"
        observed = token_state.inspect(path)
        os.utime(path, (time.time() + 10000, time.time() + 10000))
        self.assertEqual(token_state.inspect(path), observed)
        with self.assertRaises(SetupError):
            token_state.inspect(path, now=observed + 3601)
        path.write_text("different-synthetic-token\n")
        with self.assertRaises(SetupError):
            token_state.inspect(path)

    def test_deadline_cannot_be_extended_by_clock_rollback_or_peer_rotation(self):
        observed, start_wall, start_mono = 1000, 1200, 10
        original = token_state.remaining(observed, start_wall, start_mono, 2000, 810)
        rollback = token_state.remaining(observed, start_wall, start_mono, 1500, 810)
        self.assertEqual(original, rollback)
        self.assertLessEqual(token_state.remaining(observed, start_wall, start_mono, 100000, 20), 0)
        self.assertLessEqual(token_state.remaining(observed, start_wall, start_mono, 1000, 50000), 0)

    def test_fifo_read_is_nonblocking_and_refused(self):
        fifo = self.fake.home / "fifo"
        os.mkfifo(fifo, 0o600)
        start = time.monotonic()
        with self.assertRaises(SetupError):
            read_bytes(fifo)
        self.assertLess(time.monotonic() - start, 1)

    def test_command_timeout_stops_descendant_and_allows_cleanup(self):
        marker = self.fake.root / "child-pid"
        script = self.fake.root / "group.sh"
        script.write_text('#!/bin/bash\ntrap \'kill "$child" 2>/dev/null; wait "$child" 2>/dev/null; exit 1\' TERM\nsleep 60 &\nchild=$!\nprintf "%s" "$child" > "$1"\nwait "$child"\n')
        with self.assertRaisesRegex(SetupError, "timed out"):
            command(["bash", str(script), str(marker)], env=self.fake.env, timeout=0.3)
        child_pid = int(marker.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)


class FrozenGenerationTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSystem()
        self.addCleanup(self.fake.close)
        self.observed = 1000000.75
        self.token = self.fake.home / "iam-token"
        self.token.write_bytes(b"synthetic-generation-token\n")
        self.token.chmod(0o600)
        self.metadata = {"version": 2, "sha256": digest(token_state.token_bytes(self.token)),
                         "observed_at": self.observed}
        self.token.with_suffix(".json").write_bytes(json_bytes(self.metadata))
        self.token.with_suffix(".json").chmod(0o600)
        self.generation = self.fake.home / "iam-token.restart.fixture.generation"
        with mock.patch.object(token_state.time, "time", return_value=self.observed + 3599):
            self.assertEqual(token_state.freeze(self.token, self.generation, self.fake.home), self.observed)

    def generation_observed(self, now):
        with (mock.patch.object(token_state.time, "time", return_value=now),
              mock.patch.object(sys, "argv", ["token_state.py", "generation-observed", str(self.generation)]),
              contextlib.redirect_stdout(io.StringIO()) as output,
              contextlib.redirect_stderr(io.StringIO()) as error):
            status = token_state.main()
        return status, output.getvalue(), error.getvalue()

    def test_watchdog_attachment_accepts_generation_after_startup_boundary(self):
        before = self.generation.read_bytes()
        self.assertEqual(self.generation_observed(self.observed + 3601),
                         (0, f"{int(self.observed)}\n", ""))
        self.assertEqual(self.generation.read_bytes(), before)
        self.assertEqual(self.fake.calls, [])
        with self.assertRaises(SetupError):
            token_state.snapshot(self.token, now=self.observed + 3601)
        rejected = self.fake.home / "rejected-generation"
        with mock.patch.object(token_state.time, "time", return_value=self.observed + 3601):
            with self.assertRaises(SetupError):
                token_state.freeze(self.token, rejected, self.fake.home)
        self.assertFalse(rejected.exists())

    def test_watchdog_reader_enforces_original_operational_age_boundary(self):
        for age, expected in ((0, 0), (3600, 0), (3601, 0), (token_state.STOP_AGE - 0.5, 0),
                              (token_state.STOP_AGE, 1), (token_state.STOP_AGE + 1, 1), (-1, 1)):
            with self.subTest(age=age):
                status, output, error = self.generation_observed(self.observed + age)
                self.assertEqual(status, expected)
                if expected:
                    self.assertEqual(output, "")
                    self.assertEqual(error, "Token state validation failed; credential contents withheld.\n")

    def test_watchdog_reader_rejects_malformed_generation(self):
        invalid = [{**self.metadata, "observed_at": value}
                   for value in (True, False, None, "1000000", float("nan"), float("inf"), -float("inf"))]
        invalid += [{**self.metadata, "sha256": value} for value in (None, [], "not-a-hash", "A" * 64)]
        invalid += [{**self.metadata, "version": 1}, {**self.metadata, "extra": 1},
                    {"version": 2, "sha256": self.metadata["sha256"]}, []]
        for index, value in enumerate(invalid):
            with self.subTest(case=index):
                self.generation.write_bytes(json_bytes(value))
                status, output, error = self.generation_observed(self.observed + 100)
                self.assertEqual((status, output), (1, ""))
                self.assertEqual(error, "Token state validation failed; credential contents withheld.\n")

    def test_watchdog_reader_rejects_unsafe_private_file(self):
        self.generation.chmod(0o644)
        self.assertEqual(self.generation_observed(self.observed + 100)[0:2], (1, ""))
        self.generation.chmod(0o600)
        other = self.fake.home / "generation-copy"
        self.generation.rename(other)
        self.generation.symlink_to(other)
        self.assertEqual(self.generation_observed(self.observed + 100)[0:2], (1, ""))

    def test_delayed_watchdog_attachment_keeps_original_deadline(self):
        start_wall, start_mono = self.observed + 3601, 10
        remaining = token_state.remaining(self.observed, start_wall, start_mono, start_wall, start_mono)
        self.assertEqual(remaining, token_state.STOP_AGE - 3601)
        self.assertEqual(token_state.remaining(self.observed, start_wall, start_mono,
                                               self.observed + token_state.STOP_AGE, start_mono + remaining), 0)


if __name__ == "__main__":
    unittest.main()
