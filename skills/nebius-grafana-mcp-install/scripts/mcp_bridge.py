"""Supervise stock MCP plus a private credential proxy and framed stdio guard."""

import os

# Establish ownership before imports can delay startup and before any child or
# listener exists. The outer supervisor requires this private group.
if __name__ == "__main__" and os.getpgrp() != os.getpid():
    os.setsid()

from pathlib import Path
import selectors
import signal
import subprocess
import sys
import threading

from common import SetupError, check_path, json_read
from credential_proxy import Backend, MAX_RESPONSE, ProxyError, decode_json, serve
from runtime_contract import MCP_ARGS
import token_state

MAX_FRAME = MAX_RESPONSE


def checked_frame(frame, protected):
    if not frame or len(frame) > MAX_FRAME:
        raise SetupError("MCP frame size is invalid; output withheld.")
    try:
        message = decode_json(frame, protected)
    except ProxyError as exc:
        raise SetupError("MCP output rejected; credential contents withheld.") from exc
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise SetupError("Malformed MCP output withheld.")
    request = isinstance(message.get("method"), str)
    response = ("id" in message and ("result" in message) != ("error" in message))
    if request == response or (request and ("result" in message or "error" in message)):
        raise SetupError("Malformed MCP output withheld.")
    if "id" in message and message["id"] is not None and type(message["id"]) not in (int, str):
        raise SetupError("Malformed MCP identifier withheld.")
    return frame + b"\n"


def child_environment(local_url, local_token, inherited=None):
    inherited = os.environ if inherited is None else inherited
    env = {
        key: value for key, value in inherited.items()
        if not key.startswith(("NEBIUS_", "CODEX_NEBIUS_", "GRAFANA_", "OTEL_"))
        and key not in {"TOKEN", "IAM_TOKEN", "MCP_GRAFANA_SERVER_TOKEN"}
        and key.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    }
    env.update(GRAFANA_URL=local_url, GRAFANA_SERVICE_ACCOUNT_TOKEN=local_token,
               NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
    return env


def exchange(process, protected, proxy_thread, stdin_fd, stdout_fd):
    """Bound both directions and withhold entire unvalidated output frames."""
    child_in, child_out = process.stdin.fileno(), process.stdout.fileno()
    original = {fd: os.get_blocking(fd) for fd in (stdin_fd, stdout_fd)}
    for fd in (stdin_fd, stdout_fd, child_in, child_out):
        os.set_blocking(fd, False)
    partial_in, partial_out, to_child, to_agent = b"", b"", b"", b""
    input_open, output_open, child_input_open = True, True, True
    try:
        while output_open or to_agent:
            if not proxy_thread.is_alive():
                raise SetupError("Credential proxy stopped; MCP was stopped.")
            with selectors.DefaultSelector() as selector:
                if input_open and len(to_child) < MAX_FRAME:
                    selector.register(stdin_fd, selectors.EVENT_READ, "input")
                if output_open and len(to_agent) < MAX_FRAME:
                    selector.register(child_out, selectors.EVENT_READ, "output")
                if to_child and child_input_open:
                    selector.register(child_in, selectors.EVENT_WRITE, "child")
                if to_agent:
                    selector.register(stdout_fd, selectors.EVENT_WRITE, "agent")
                events = selector.select(0.2)
            for key, _ in events:
                if key.data in {"input", "output"}:
                    chunk = os.read(key.fd, 65536)
                    if key.data == "input":
                        if not chunk:
                            input_open = False
                            if partial_in:
                                raise SetupError("Incomplete MCP input frame.")
                        partial_in += chunk
                        while b"\n" in partial_in:
                            frame, partial_in = partial_in.split(b"\n", 1)
                            to_child += checked_frame(frame, protected)
                    else:
                        if not chunk:
                            output_open = False
                            if partial_out:
                                raise SetupError("Incomplete MCP output withheld.")
                        partial_out += chunk
                        while b"\n" in partial_out:
                            frame, partial_out = partial_out.split(b"\n", 1)
                            to_agent += checked_frame(frame, protected)
                elif key.data == "child":
                    to_child = to_child[os.write(child_in, to_child):]
                else:
                    to_agent = to_agent[os.write(stdout_fd, to_agent):]
            if max(len(partial_in), len(partial_out), len(to_child), len(to_agent)) > 2 * MAX_FRAME:
                raise SetupError("MCP buffering limit exceeded; output withheld.")
            if not input_open and not to_child and child_input_open:
                process.stdin.close()
                child_input_open = False
        return process.wait(timeout=5)
    finally:
        for fd, blocking in original.items():
            try:
                os.set_blocking(fd, blocking)
            except OSError:
                pass


def run(binary, backend, *, inherited=None, stdin_fd=0, stdout_fd=1):
    process = None
    with serve(backend) as (proxy, proxy_thread):
        local_url = "http://127.0.0.1:" + str(proxy.server_port) + "/"
        env = child_environment(local_url, proxy.local_token, inherited)
        protected = (backend.token, proxy.local_token)
        try:
            # Main owns a private process group. Keeping the child in that
            # group lets the outer supervisor clean up even if this process dies.
            process = subprocess.Popen([str(binary), *MCP_ARGS], env=env,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL)
            return exchange(process, protected, proxy_thread, stdin_fd, stdout_fd)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()


def main():
    from runtime_check import validate

    def cancel(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, cancel)
    try:
        validate(Path.home(), Path(__file__).resolve().parent, os.environ)
        path = Path(os.environ["GRAFANA_TOKEN_FILE"])
        generation = Path(os.environ["NEBIUS_GRAFANA_GENERATION_FILE"])
        if generation.parent != path.parent or not generation.name.startswith("iam-token.restart."):
            raise SetupError("Unexpected token generation binding.")
        from mcp_frontend import exchange as frontend_exchange, load_catalog
        catalog = load_catalog(Path(__file__).resolve().parent)
        backend_read, frontend_write = os.pipe()
        frontend_read, backend_write = os.pipe()
        stopped = threading.Event()
        cancel_worker = threading.Event()

        def prepare():
            try:
                while not generation.exists():
                    if cancel_worker.wait(0.05):
                        return
                    check_path(generation, Path.home(), private=True, missing=True)
                check_path(generation, Path.home(), private=True)
                token, metadata = token_state.snapshot(path)
                if metadata != json_read(generation, private=True):
                    raise SetupError("Token generation changed during startup; reconnect.")
                backend = Backend(os.environ["GRAFANA_URL"], token.decode("ascii"))
                if not cancel_worker.is_set():
                    run(Path(os.environ["NEBIUS_GRAFANA_MCP_BINARY"]), backend,
                        stdin_fd=backend_read, stdout_fd=backend_write)
            except (SetupError, ProxyError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                pass  # The front connection gets only a fixed failure.
            finally:
                stopped.set()
                os.close(backend_read)
                os.close(backend_write)

        worker = threading.Thread(target=prepare, daemon=True)
        worker.start()
        try:
            return frontend_exchange(catalog, frontend_write, frontend_read, stopped)
        finally:
            cancel_worker.set()
            os.close(frontend_write)
            os.close(frontend_read)
            worker.join(timeout=3)
    except KeyboardInterrupt:
        return 130
    except (SetupError, ProxyError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("MCP connection stopped; private runtime details withheld.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
