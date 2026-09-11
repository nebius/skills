"""Complete-frame privacy and a real stdio -> proxy -> HTTP fixture exchange."""

import json
import os
from pathlib import Path
import selectors
import sys
import tempfile
import threading
import unittest

from fixtures import SCRIPTS
from common import SetupError
import mcp_bridge
from test_proxy import TOKEN, upstream


class BridgeTests(unittest.TestCase):
    def test_only_complete_valid_jsonrpc_frames_pass(self):
        frame = b'{"jsonrpc":"2.0","id":1,"result":{"content":[]}}'
        self.assertEqual(mcp_bridge.checked_frame(frame, (TOKEN,)), frame + b"\n")
        for bad in (b"diagnostic", b"[]", b'{"id":1,"result":{}}',
                    b'{"jsonrpc":"2.0","id":true,"result":{}}',
                    b'{"jsonrpc":"2.0","id":1,"result":{},"error":{}}',
                    b'{"jsonrpc":"2.0","method":"bad","result":{}}',
                    b"x" * (mcp_bridge.MAX_FRAME + 1)):
            with self.subTest(size=len(bad)), self.assertRaises(SetupError):
                mcp_bridge.checked_frame(bad, (TOKEN,))

    def test_nested_and_escaped_credentials_are_withheld(self):
        for secret in (TOKEN, "synthetic-local-credential"):
            frame = json.dumps({"jsonrpc": "2.0", "id": 1,
                                "error": {"message": json.dumps({"header": "Bearer " + secret})}}).encode()
            with self.assertRaises(SetupError):
                mcp_bridge.checked_frame(frame, (TOKEN, "synthetic-local-credential"))
            escaped = frame.replace(secret.encode(), "".join("\\u%04x" % ord(c) for c in secret).encode())
            with self.assertRaises(SetupError):
                mcp_bridge.checked_frame(escaped, (TOKEN, "synthetic-local-credential"))

    def test_child_environment_excludes_cloud_auth_and_telemetry(self):
        inherited = {"PATH": "/usr/bin", "GRAFANA_TOKEN_FILE": "/private/token",
                     "GRAFANA_SERVICE_ACCOUNT_TOKEN_FILE": "/private/token", "TOKEN": TOKEN,
                     "NEBIUS_IAM_TOKEN": TOKEN, "CODEX_NEBIUS_TOKEN_HELPER": "/private/helper",
                     "NEBIUS_GRAFANA_GENERATION_FILE": "/private/generation",
                     "GRAFANA_EXTRA_HEADERS": TOKEN, "OTEL_EXPORTER_OTLP_ENDPOINT": "http://unused.test",
                     "HTTPS_PROXY": "http://unused.test"}
        env = mcp_bridge.child_environment("http://127.0.0.1:1234/", "local-example", inherited)
        self.assertEqual(env["GRAFANA_SERVICE_ACCOUNT_TOKEN"], "local-example")
        self.assertEqual(env["GRAFANA_URL"], "http://127.0.0.1:1234/")
        self.assertNotIn(TOKEN, str(env))
        for key in inherited:
            if key != "PATH":
                self.assertNotIn(key, env)

    def run_exchange(self, script_body):
        with tempfile.TemporaryDirectory(prefix="mcp-bridge-test-") as directory:
            binary = Path(directory) / "mcp-fixture"
            binary.write_text("#!" + sys.executable + "\n" + script_body)
            binary.chmod(0o700)
            input_read, input_write = os.pipe()
            output_read, output_write = os.pipe()
            result = []
            with upstream() as (backend, calls, _):
                def worker():
                    try:
                        result.append(mcp_bridge.run(binary, backend, inherited={"PATH": os.defpath},
                                                     stdin_fd=input_read, stdout_fd=output_write))
                    except SetupError:
                        result.append("output-rejected")
                    finally:
                        os.close(output_write)

                thread = threading.Thread(target=worker)
                thread.start()
                try:
                    os.write(input_write, b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{}}\n')
                    os.close(input_write)
                    input_write = None
                    with selectors.DefaultSelector() as selector:
                        selector.register(output_read, selectors.EVENT_READ)
                        self.assertTrue(selector.select(5), "Bridge did not complete a response")
                    output = os.read(output_read, 65536)
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())
                    return output, result, list(calls)
                finally:
                    if input_write is not None:
                        os.close(input_write)
                    os.close(input_read)
                    os.close(output_read)

    def test_stdio_child_uses_local_credential_and_proxy_supplies_cloud_credential(self):
        output, result, calls = self.run_exchange('''import json, os, sys, urllib.request
assert not any(k.startswith(('NEBIUS_', 'CODEX_NEBIUS_')) for k in os.environ)
assert 'GRAFANA_SERVICE_ACCOUNT_TOKEN_FILE' not in os.environ
assert 'GRAFANA_TOKEN_FILE' not in os.environ
for line in sys.stdin:
    message = json.loads(line)
    request = urllib.request.Request(os.environ['GRAFANA_URL'] + 'api/datasources',
        headers={'Authorization': 'Bearer ' + os.environ['GRAFANA_SERVICE_ACCOUNT_TOKEN']})
    with urllib.request.urlopen(request, timeout=3) as response:
        text = response.read().decode()
    print(json.dumps({'jsonrpc': '2.0', 'id': message['id'],
                     'result': {'content': [{'type': 'text', 'text': text}]}}), flush=True)
''')
        self.assertEqual(result, [0])
        self.assertEqual(json.loads(output)["id"], 1)
        self.assertEqual(calls[0][2]["Authorization"], "Bearer " + TOKEN)
        self.assertNotIn(TOKEN.encode(), output)

    def test_reflected_local_credential_never_reaches_agent_pipe(self):
        output, result, calls = self.run_exchange('''import json, os
print(json.dumps({'jsonrpc': '2.0', 'id': 1,
                  'result': {'text': os.environ['GRAFANA_SERVICE_ACCOUNT_TOKEN']}}), flush=True)
''')
        self.assertEqual(output, b"")
        self.assertEqual(result, ["output-rejected"])
        self.assertEqual(calls, [])

    def test_guard_is_in_immutable_runtime_inventory(self):
        from runtime_contract import FILES
        self.assertIn("mcp_bridge.py", FILES)
        self.assertIn("credential_proxy.py", FILES)
        self.assertNotIn("policy.py", FILES)
        self.assertTrue(all((SCRIPTS / name).is_file() for name in FILES))


if __name__ == "__main__":
    unittest.main()
