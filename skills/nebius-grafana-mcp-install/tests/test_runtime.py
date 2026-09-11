"""Exercise the actual stdio supervisor against synthetic local executables."""

import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import time
import unittest

from fixtures import FakeSystem
import token_state


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSystem()
        self.processes = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
        self.fake.close()

    def start(self, **updates):
        args, env = self.fake.runtime_command()
        env.update(updates)
        process = subprocess.Popen(args, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        self.processes.append(process)
        return process

    def start_refresh(self, **updates):
        args, env = self.fake.runtime_command()
        process = subprocess.Popen([args[0], "--refresh-token-only"], env={**env, **updates},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        self.processes.append(process)
        return process

    def wait_for_file(self, path, process=None):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if path.exists():
                return
            if process is not None and process.poll() is not None:
                self.fail("Fixture process exited before its synchronization marker")
            time.sleep(0.02)
        self.fail("Fixture synchronization marker timed out")

    def intercept_pid_capture(self, *, kill_writer=False):
        # Cover the old file-backed probe and the replacement exec-based probe.
        # Only this temporary fixture PATH is changed; every other call execs
        # its real interpreter, retaining the original process relationship.
        marker = self.fake.root / "writer-pid"
        for name, executable in (("sh", shutil.which("sh", path=os.defpath)), ("python3", sys.executable)):
            path = self.fake.bin / name
            if path.exists():
                path.unlink()
            path.write_text(
                f"#!{sys.executable}\n"
                "import os, pathlib, signal, sys\n"
                "args = sys.argv[1:]\n"
                f"capture = (args == ['-c', 'printf \"%s\\\\n\" \"$PPID\"'] if {name!r} == 'sh' "
                "else args == ['-B', '-c', 'import os; print(os.getppid())'])\n"
                "if capture:\n"
                "    writer = os.getppid()\n"
                f"    pathlib.Path({str(marker)!r}).write_text(str(writer))\n"
                "    print(writer, flush=True)\n"
                f"    if {kill_writer!r}: os.kill(writer, signal.SIGKILL)\n"
                "    sys.exit(0)\n"
                f"os.execv({executable!r}, [{executable!r}, *args])\n"
            )
            path.chmod(0o700)
        return marker

    def add_lock_wait_marker(self):
        # Instrument the copied fixture before immutable bundle staging. No
        # test hooks or environment overrides enter the production script.
        path = self.fake.source / "run-nebius-grafana-mcp.sh"
        source = path.read_text()
        anchor = '    sleep 1\n    waited=$((waited + 1))\n  done\n'
        self.assertEqual(source.count(anchor), 1)
        marker = ('    if [ -n "${FAKE_LOCK_WAIT_MARKER:-}" ]; then\n'
                  '      : >"$FAKE_LOCK_WAIT_MARKER"\n'
                  '    fi\n')
        path.write_text(source.replace(anchor, anchor.replace('  done\n', marker + '  done\n')))

    def hold_refresh_lock(self, layout):
        holder = subprocess.Popen(["sleep", "30"], start_new_session=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(holder)
        lock = layout.state / "iam-token.lock"
        lock.mkdir(mode=0o700)
        started = subprocess.check_output(["ps", "-o", "lstart=", "-p", str(holder.pid)], text=True).strip()
        owner = lock / "owner"
        owner.write_text(f"version=1\npid={holder.pid}\nstarted_at_epoch={int(time.time())}\nprocess_started_at={started}\n")
        owner.chmod(0o600)
        return holder, lock

    def rpc(self, process, method, request_id):
        process.stdin.write((json.dumps({"jsonrpc": "2.0", "id": request_id,
                                        "method": method, "params": {}}) + "\n").encode())
        process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(timeout=10), "MCP response timed out")
        line = process.stdout.readline()
        self.assertTrue(line, "MCP exited before responding")
        return json.loads(line)["result"]

    def events(self):
        return [json.loads(line) for line in (self.fake.root / "mcp.jsonl").read_text().splitlines()]

    def watchdog(self, process):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            rows = subprocess.check_output(["ps", "-axo", "pid=,ppid=,args="], text=True)
            for row in rows.splitlines():
                fields = row.strip().split(None, 2)
                if len(fields) == 3 and fields[1] == str(process.pid) and "token_state.py watch" in fields[2]:
                    return int(fields[0])
            time.sleep(0.05)
        self.fail("Runtime did not start its deadline watchdog")

    def assert_clean(self, layout):
        self.assertFalse(list(layout.state.glob("iam-token.restart.*")))
        self.assertFalse(list(layout.state.glob("iam-token.tmp.*")))
        self.assertFalse((layout.state / "iam-token.lock").exists())
        for event in self.events():
            with self.assertRaises(ProcessLookupError):
                os.kill(event["pid"], 0)

    def test_gnu_stat_supports_refresh_and_mcp_startup(self):
        executable = shutil.which("gstat") or shutil.which("stat")
        if not executable or b"GNU coreutils" not in subprocess.run(
            [executable, "--version"], capture_output=True, timeout=5
        ).stdout:
            self.skipTest("GNU stat is not installed")
        layout = self.fake.apply()
        (self.fake.bin / "stat").symlink_to(executable)
        args, env = self.fake.runtime_command()
        result = subprocess.run([args[0], "--refresh-token-only"], env=env,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual((self.fake.root / "counter").read_text(), "2")
        process = self.start()
        self.assertEqual(self.rpc(process, "initialize", 1)["serverInfo"]["name"], "fixture")
        process.terminate()
        process.communicate(timeout=10)
        self.assert_clean(layout)

    def test_stdio_rotation_requires_new_connection_and_loads_new_generation(self):
        layout = self.fake.apply()
        process = self.start(NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS="2",
                             NEBIUS_IAM_TOKEN="SENTINEL-AMBIENT",
                             GRAFANA_SERVICE_ACCOUNT_TOKEN="SENTINEL-AMBIENT",
                             GRAFANA_EXTRA_HEADERS="SENTINEL-AMBIENT")
        self.assertEqual(self.rpc(process, "initialize", 1)["serverInfo"]["name"], "fixture")
        self.assertEqual(self.rpc(process, "tools/list", 2)["tools"][0]["name"], "list_datasources")
        self.assertEqual(self.rpc(process, "tools/call", 3)["content"][0]["text"], "[]")
        process.wait(timeout=15)
        stdout, stderr = process.communicate()
        self.assertEqual(process.returncode, 75, stderr.decode())
        self.assertNotIn(b"SENTINEL", stdout + stderr)
        self.assertNotIn(b"synthetic-token", stdout + stderr)
        self.assertEqual((self.fake.root / "counter").read_text(), "2")
        first = self.events()[0]
        process = self.start()
        self.rpc(process, "initialize", 4)
        second = self.events()[1]
        self.assertNotEqual(first["pid"], second["pid"])
        self.assertNotEqual(first["generation"], second["generation"])
        process.terminate()
        process.communicate(timeout=10)
        self.assert_clean(layout)

    def test_repeated_token_preserves_observation_and_does_not_request_reconnect(self):
        layout = self.fake.apply()
        before = (layout.state / "iam-token.json").read_bytes()
        process = self.start(NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS="1", FAKE_SAME_TOKEN="1")
        self.rpc(process, "initialize", 1)
        process.wait(timeout=15)
        stdout, stderr = process.communicate()
        self.assertEqual(process.returncode, 1)
        self.assertEqual((layout.state / "iam-token.json").read_bytes(), before)
        self.assertNotIn(b"synthetic-token", stdout + stderr)
        self.assert_clean(layout)

    def test_unsafe_flags_or_origin_fail_before_stale_token_mint(self):
        layout = self.fake.apply()
        (layout.state / "iam-token.json").unlink()
        before = (self.fake.root / "counter").read_bytes()
        args, env = self.fake.runtime_command()
        for flags, origin in ((["--allow-write"], env["GRAFANA_URL"]),
                              (args[1:], "https://unapproved.example.test/")):
            result = subprocess.run([args[0], *flags], env={**env, "GRAFANA_URL": origin},
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.fake.root / "counter").read_bytes(), before)
        self.assertFalse((self.fake.root / "mcp.jsonl").exists())

    def test_delayed_group_creation_stops_before_mcp_or_proxy_can_start(self):
        source = self.fake.source / "mcp_bridge.py"
        source.write_text(source.read_text().replace("    os.setsid()", "    __import__('time').sleep(5)\n    os.setsid()"))
        layout = self.fake.apply()
        process = self.start()
        process.wait(timeout=10)
        _, stderr = process.communicate()
        self.assertEqual(process.returncode, 1)
        self.assertIn(b"process-group ownership", stderr)
        time.sleep(3)
        self.assertFalse((self.fake.root / "mcp.jsonl").exists())
        self.assertFalse(list(layout.state.glob("iam-token.restart.*")))

    def test_failed_renewal_stops_mcp_and_redacts_cli_stderr(self):
        layout = self.fake.apply()
        process = self.start(NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS="1",
                             NEBIUS_GRAFANA_TOKEN_REFRESH_RETRY_SECONDS="0 0 0",
                             FAKE_FAIL_MINT="1")
        self.rpc(process, "initialize", 1)
        process.wait(timeout=20)
        stdout, stderr = process.communicate()
        self.assertEqual(process.returncode, 1)
        self.assertIn(b"refresh exhausted", stderr)
        self.assertNotIn(b"SENTINEL", stdout + stderr)
        self.assert_clean(layout)

    def test_stopped_watchdog_stops_mcp_without_hanging_cleanup(self):
        layout = self.fake.apply()
        process = self.start()
        self.rpc(process, "initialize", 1)
        watchdog = self.watchdog(process)
        os.kill(watchdog, signal.SIGSTOP)
        process.wait(timeout=10)
        process.communicate()
        self.assertEqual(process.returncode, 1)
        with self.assertRaises(ProcessLookupError):
            os.kill(watchdog, 0)
        self.assert_clean(layout)

    def test_loaded_deadline_is_not_extended_by_peer_token_replacement(self):
        # Accelerate only the copied fixture's source-owned deadline, before
        # staging/hash verification. Production code has no override for this.
        source = self.fake.source / "token_state.py"
        source.write_text(source.read_text().replace("STOP_AGE = 39600", "STOP_AGE = 5"))
        layout = self.fake.apply()
        process = self.start()
        self.rpc(process, "initialize", 1)
        args, env = self.fake.runtime_command()
        time.sleep(1)
        result = subprocess.run([args[0], "--refresh-token-only"], env=env,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        process.wait(timeout=10)
        process.communicate()
        self.assertEqual(process.returncode, 1)
        self.assertEqual(len(self.events()), 1)
        self.assert_clean(layout)

    def test_concurrent_refreshers_share_one_new_token_generation(self):
        layout = self.fake.apply()
        args, env = self.fake.runtime_command()
        env["FAKE_MINT_DELAY"] = "2"
        workers = [subprocess.Popen([args[0], "--refresh-token-only"], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    start_new_session=True) for _ in range(2)]
        self.processes.extend(workers)
        for worker in workers:
            _, stderr = worker.communicate(timeout=15)
            self.assertEqual(worker.returncode, 0, stderr.decode())
        self.assertEqual((self.fake.root / "counter").read_text(), "2")
        self.assertFalse((layout.state / "iam-token.lock").exists())
        self.assertFalse(list(layout.state.glob("iam-token.tmp.*")))

    def assert_pid_capture_crash_is_recoverable(self, *, background):
        layout = self.fake.apply()
        marker = self.intercept_pid_capture(kill_writer=True)
        process = self.start(NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS="1") if background else self.start_refresh()
        self.wait_for_file(marker, process)
        process.wait(timeout=10)
        stdout, stderr = process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        self.assertNotIn(b"synthetic-token", stdout + stderr)
        self.assertFalse((layout.state / "iam-token.lock").exists(), "PID capture left a blocking lock")
        self.intercept_pid_capture()
        next_refresh = self.start_refresh()
        _, stderr = next_refresh.communicate(timeout=10)
        self.assertEqual(next_refresh.returncode, 0, stderr.decode())
        self.assertEqual((self.fake.root / "counter").read_text(), "2")
        token_state.snapshot(layout.state / "iam-token")
        self.assertFalse((layout.state / "iam-token.lock").exists())
        if background:
            self.assert_clean(layout)

    def test_foreground_pid_capture_crash_leaves_no_blocking_artifact(self):
        self.assert_pid_capture_crash_is_recoverable(background=False)

    def test_background_pid_capture_crash_leaves_no_blocking_artifact(self):
        self.assert_pid_capture_crash_is_recoverable(background=True)

    def assert_writer_identity(self, *, background):
        layout = self.fake.apply()
        marker = self.intercept_pid_capture()
        # Hold the synthetic CLI after complete owner publication until the
        # test has inspected that live identity, rather than racing a sleep.
        nebius = self.fake.bin / "nebius"
        source = nebius.read_text()
        anchor = "    time.sleep(float(os.environ.get('FAKE_MINT_DELAY', '0')))\n"
        self.assertEqual(source.count(anchor), 1)
        barrier = (
            "    barrier = pathlib.Path(os.environ['FAKE_MINT_BARRIER'])\n"
            "    barrier.touch()\n"
            "    deadline = time.monotonic() + 10\n"
            "    while not barrier.with_suffix('.release').exists():\n"
            "        if time.monotonic() >= deadline: sys.exit(7)\n"
            "        time.sleep(0.02)\n"
        )
        nebius.write_text(source.replace(anchor, barrier + anchor))
        mint_marker = self.fake.root / "mint-barrier"
        updates = {"FAKE_MINT_BARRIER": str(mint_marker)}
        process = (self.start(**updates, NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS="1")
                   if background else self.start_refresh(**updates))
        self.wait_for_file(marker, process)
        self.wait_for_file(mint_marker, process)
        owner = dict(line.split("=", 1) for line in (layout.state / "iam-token.lock" / "owner").read_text().splitlines())
        writer = int(owner["pid"])
        self.assertEqual(writer, int(marker.read_text()))
        if background:
            self.assertNotEqual(writer, process.pid)
            self.assertEqual(int(subprocess.check_output(["ps", "-o", "ppid=", "-p", str(writer)])), process.pid)
        else:
            self.assertEqual(writer, process.pid)
        self.assertEqual(owner["process_started_at"], subprocess.check_output(
            ["ps", "-o", "lstart=", "-p", str(writer)], text=True).strip())
        mint_marker.with_suffix('.release').touch()
        process.wait(timeout=10)
        _, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 75 if background else 0, stderr.decode())
        self.assertFalse((layout.state / "iam-token.lock").exists())
        if background:
            self.assert_clean(layout)

    def test_foreground_writer_identity_matches_owning_shell(self):
        self.assert_writer_identity(background=False)

    def test_background_writer_identity_matches_owning_shell(self):
        self.assert_writer_identity(background=True)

    def assert_incomplete_concurrent_publication(self, *, background):
        self.add_lock_wait_marker()
        layout = self.fake.apply()
        metadata = layout.state / "iam-token.json"
        before = metadata.read_bytes()
        holder, lock = self.hold_refresh_lock(layout)
        marker = self.fake.root / "lock-waited"
        updates = {"FAKE_LOCK_WAIT_MARKER": str(marker), "NEBIUS_GRAFANA_STARTUP_LOCK_WAIT_SECONDS": "5"}
        process = (self.start(**updates, NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS="1",
                              NEBIUS_GRAFANA_TOKEN_REFRESH_RETRY_SECONDS="0 0 0")
                   if background else self.start_refresh(**updates))
        self.wait_for_file(marker, process)
        # Model a writer dying after token rename, before metadata publication.
        replacement = layout.state / "interrupted-token"
        replacement.write_bytes(b"synthetic-interrupted-generation\n")
        replacement.chmod(0o600)
        replacement.replace(layout.state / "iam-token")
        holder.terminate()
        holder.communicate(timeout=5)
        process.wait(timeout=15)
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 75 if background else 1, stderr.decode())
        self.assertNotIn(b"reused the fresh", stderr)
        self.assertNotIn(b"synthetic-", stdout + stderr)
        self.assertFalse(lock.exists())
        if background:
            self.assertIn(b"retrying", stderr)
            self.assertEqual((self.fake.root / "counter").read_text(), "2")
            token_state.snapshot(layout.state / "iam-token")
            self.assert_clean(layout)
        else:
            self.assertEqual(metadata.read_bytes(), before)
            self.assertEqual((self.fake.root / "counter").read_text(), "1")
            self.assertEqual((layout.state / "iam-token").read_bytes(), b"synthetic-interrupted-generation\n")

    def test_foreground_rejects_incomplete_concurrent_publication(self):
        self.assert_incomplete_concurrent_publication(background=False)

    def test_background_retries_incomplete_concurrent_publication(self):
        self.assert_incomplete_concurrent_publication(background=True)

    def test_pre_fix_pid_residue_is_preserved_for_human_recovery(self):
        layout = self.fake.apply()
        lock = layout.state / "iam-token.lock"
        lock.mkdir(mode=0o700)
        residue = lock / "owner-pid.tmp"
        residue.write_text("12345\n")
        residue.chmod(0o600)
        os.utime(lock, (time.time() - 1000,) * 2)
        process = self.start_refresh(NEBIUS_GRAFANA_STARTUP_LOCK_WAIT_SECONDS="1")
        _, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 1, stderr.decode())
        self.assertEqual(residue.read_text(), "12345\n")
        self.assertEqual((self.fake.root / "counter").read_text(), "1")
