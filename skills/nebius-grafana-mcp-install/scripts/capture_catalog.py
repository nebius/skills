"""Maintainer-only: capture public discovery from a checksum-pinned release."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import threading

from binary_state import VERSION, artifact
from common import SetupError, digest, json_bytes, read_bytes
from materialize import fetch
from readiness import Conversation, PROTOCOL
from runtime_contract import MCP_ARGS


def capture(source):
    item, url = artifact(source)
    data = fetch(url)
    if digest(data) != item["sha256"]:
        raise SetupError("Official release checksum mismatch.")

    class Refuse(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"error":"catalog-capture-has-no-upstream"}'
            self.send_response_only(503)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Refuse)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="grafana-catalog-") as folder:
            root = Path(folder).resolve()
            root.chmod(0o700)
            binary = root / "mcp-grafana"
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                members = [m for m in archive.getmembers() if m.name == "mcp-grafana"]
                if len(members) != 1 or not members[0].isfile() or members[0].size > 256 * 1024 * 1024:
                    raise SetupError("Invalid release executable.")
                binary.write_bytes(archive.extractfile(members[0]).read())
            binary.chmod(0o700)
            env = {"HOME": str(root), "PATH": os.defpath,
                   "GRAFANA_URL": f"http://127.0.0.1:{server.server_port}/",
                   "GRAFANA_SERVICE_ACCOUNT_TOKEN": "synthetic-catalog-only"}
            process = subprocess.Popen([str(binary), *MCP_ARGS], env=env, cwd=root,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL)
            try:
                rpc = Conversation(process, 10)
                initialized = rpc.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                          "clientInfo": {"name": "catalog-capture", "version": "1"}})
                rpc.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                result = {"version": VERSION, "args": list(MCP_ARGS), "initialize": initialized,
                          "artifacts_sha256": digest(read_bytes(source / "artifacts.json"))}
                for method, field, key in (("tools/list", "tools", "name"),
                                           ("resources/list", "resources", "uri"),
                                           ("resources/templates/list", "resourceTemplates", "uriTemplate")):
                    values, params, cursors = [], {}, set()
                    for _ in range(16):
                        page = rpc.request(method, params)
                        values.extend(page[field])
                        cursor = page.get("nextCursor")
                        if cursor is None:
                            break
                        if not isinstance(cursor, str) or cursor in cursors:
                            raise SetupError("Invalid catalog pagination.")
                        cursors.add(cursor)
                        params = {"cursor": cursor}
                    else:
                        raise SetupError("Catalog pagination exceeded its bound.")
                    result[field] = sorted(values, key=lambda value: value[key])
                return result
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                process.stdout.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true", help="Compare the pinned catalog without rewriting it.")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    expected = json_bytes(capture(source))
    if args.check:
        if read_bytes(source / "catalog.json") != expected:
            raise SystemExit("Pinned catalog differs from the official executable.")
        print("Pinned discovery catalog matches the official executable.")
    else:
        (source / "catalog.json").write_bytes(expected)
        print("Captured public pinned discovery catalog.")
