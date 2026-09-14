"""Private filesystem and subprocess primitives. Never return raw errors to users."""

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
import time


class SetupError(Exception):
    """A sanitized, user-actionable failure."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise SetupError("Invalid profile or server name.")
    return value


def check_path(path, home, *, directory=False, private=False, missing=False):
    """Check each component below the supplied user's home, without following links."""
    path, home = Path(path), Path(home)
    if not path.is_absolute() or ".." in path.parts:
        raise SetupError("Expected a normalized absolute path.")
    try:
        parts = path.relative_to(home).parts
    except ValueError as exc:
        raise SetupError("Managed paths must be inside the selected user's home.") from exc
    current = home
    for i, part in enumerate(("", *parts)):
        if part:
            current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                return
            raise SetupError("Required local state is missing.") from None
        leaf = i == len(parts)
        want_dir = not leaf or directory
        if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
            raise SetupError("Unsafe ownership or symlink in managed path.")
        if info.st_mode & 0o022:
            raise SetupError("Managed path is writable by another user.")
        if want_dir and not stat.S_ISDIR(info.st_mode):
            raise SetupError("Expected a directory in managed path.")
        if leaf and not directory and not stat.S_ISREG(info.st_mode):
            raise SetupError("Expected a regular state file.")
        if leaf and private and stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
            raise SetupError("Private directories/files require modes 0700/0600.")


def mkdir_private(path, home):
    check_path(path, home, directory=True, missing=True)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    check_path(path, home, directory=True, private=True)


def read_bytes(path, *, private=False, limit=4 * 1024 * 1024, system=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise SetupError("Unable to safely open local file.") from exc
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        owners = (0, os.getuid()) if system else (os.getuid(),)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in owners or info.st_mode & 0o022:
            raise SetupError("Unsafe local file type, owner or permissions.")
        if private and stat.S_IMODE(info.st_mode) != 0o600:
            raise SetupError("Private file requires mode 0600.")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise SetupError("Local file exceeds its size limit.")
        return data


def json_read(path, **kwargs):
    try:
        value = json.loads(read_bytes(path, **kwargs), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as exc:
        raise SetupError("Malformed local JSON; contents withheld.") from exc
    if not isinstance(value, dict):
        raise SetupError("Expected a local JSON object.")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def atomic_write(path, data, home, *, expected=None, mode=0o600):
    """Atomic publication for owned state; writers must hold the owning lock.

    Expected-byte checks detect drift but are not filesystem compare-and-swap.
    Never use this helper to edit shared client configuration.
    """
    check_path(path.parent, home, directory=True)
    check_path(path, home, missing=True)

    def unchanged():
        if path.exists() or path.is_symlink():
            return expected is not None and read_bytes(path) == expected
        return expected is None

    if not unchanged():
        raise SetupError("Local state changed concurrently; inspect and retry.")
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if not unchanged():
            raise SetupError("Local state changed concurrently; inspect and retry.")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


@contextlib.contextmanager
def lock(path, home, timeout=90):
    """Kernel-owned advisory lock; process exit releases it, with no stale-PID recovery."""
    check_path(path, home, missing=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise SetupError("Unsafe setup lock.")
        end = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= end:
                    raise SetupError("Timed out waiting for setup lock.") from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def clean_env(agent):
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("NEBIUS_", "GRAFANA_", "CODEX_NEBIUS_"))
        and k not in {"TOKEN", "IAM_TOKEN"}
    }
    env["AI_AGENT"] = os.environ.get("AI_AGENT") or agent
    return env


def stop_command_group(process):
    """Stop the caller-owned group on timeout or cancellation, then reap it."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # A descendant may ignore TERM after closing inherited pipes. Even when
    # communicate returns, terminate remaining members of this private group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.communicate()


def command(args, *, env=None, cwd=None, timeout=30):
    process = None
    try:
        process = subprocess.Popen(args, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # The wrapper may be waiting on a bounded CLI child. Terminate its whole
        # private process group, allowing traps to remove owned locks/temp files.
        stop_command_group(process)
        raise SetupError("Command timed out; its process group was stopped.") from exc
    except OSError as exc:
        raise SetupError("Command unavailable or timed out; raw output withheld.") from exc
    except BaseException:
        if process is not None:
            stop_command_group(process)
        raise
    if process.returncode or len(stdout) > 4 * 1024 * 1024:
        raise SetupError("Command failed; raw output withheld to protect credentials.")
    return stdout
