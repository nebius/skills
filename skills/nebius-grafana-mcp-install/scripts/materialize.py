"""Stage immutable runtime bundles and verified official binary releases."""

import io
import os
from pathlib import Path
import platform
import shutil
import tarfile
import tempfile
import urllib.request

from runtime_contract import FILES

from common import (SetupError, atomic_write, check_path, digest, json_bytes,
                    json_read, lock, mkdir_private, read_bytes)

VERSION = "1.4.0"


def source_files(source):
    # The user must already trust the installed skill. Resolving a source symlink
    # is allowed; every actual source ancestor must be owned and non-writable.
    source = source.resolve(strict=True)
    for directory in (source, *source.parents):
        info = directory.stat()
        if info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
            # A sticky system temporary root is only an ancestor of isolated
            # test/package fixtures, not permission to accept a writable source.
            if directory in (Path("/tmp"), Path("/private/tmp")) and info.st_mode & 0o1000:
                continue
            raise SetupError("Runtime source has an unsafe ancestor.")
    return {filename: read_bytes(source / filename) for filename in FILES}


def bundle_id(files):
    return digest(json_bytes({key: digest(value) for key, value in files.items()}))


def verify_bundle(path, home):
    check_path(path, home, directory=True, private=True)
    manifest = json_read(path / "manifest.json", private=True)
    if set(manifest) != set(FILES) or set(p.name for p in path.iterdir()) != {*FILES, "manifest.json"}:
        raise SetupError("Runtime bundle has unexpected or missing files.")
    files = {filename: read_bytes(path / filename) for filename in FILES}
    if manifest != {key: digest(value) for key, value in files.items()} or path.name != bundle_id(files):
        raise SetupError("Runtime bundle integrity check failed.")


def materialize(source, root, home):
    files = source_files(source)
    destination = root / bundle_id(files)
    mkdir_private(root, home)
    with lock(root / ".materialize.lock", home):
        if destination.exists() or destination.is_symlink():
            verify_bundle(destination, home)
            return destination
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
        try:
            for filename, data in files.items():
                atomic_write(stage / filename, data, home, mode=0o700 if filename.endswith(".sh") else 0o600)
            atomic_write(stage / "manifest.json", json_bytes({k: digest(v) for k, v in files.items()}), home)
            if source_files(source) != files:
                raise SetupError("Runtime source changed while staging; nothing registered.")
            os.rename(stage, destination)
            verify_bundle(destination, home)
            return destination
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def binary_hash(path):
    # Resolve package-manager symlinks, then check the complete physical ancestry.
    path = path.resolve(strict=True)
    for directory in path.parents:
        info = directory.stat()
        if info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
            if directory in (Path("/tmp"), Path("/private/tmp")) and info.st_mode & 0o1000:
                continue
            raise SetupError("Binary has an unsafe ancestor.")
    return digest(read_bytes(path, system=True, limit=256 * 1024 * 1024))


def homebrew_binary(candidate):
    """Package metadata identifies bottles whose --version reports '(devel)'."""
    path = candidate.resolve(strict=True)
    if path.parts[-4:] != ("mcp-grafana", VERSION, "bin", "mcp-grafana"):
        return None
    cellar = path.parent.parent
    receipt = json_read(cellar / "INSTALL_RECEIPT.json", system=True)
    source = receipt.get("source", {})
    if source.get("tap") != "homebrew/core" or source.get("versions", {}).get("stable") != VERSION:
        return None
    formula = read_bytes(cellar / ".brew/mcp-grafana.rb", system=True)
    if f'https://github.com/grafana/mcp-grafana/archive/refs/tags/v{VERSION}.tar.gz'.encode() not in formula:
        return None
    return {"path": str(path), "sha256": binary_hash(path), "version": VERSION, "source": "homebrew/core"}


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(128 * 1024 * 1024 + 1)
    if len(data) > 128 * 1024 * 1024:
        raise SetupError("Release archive exceeds the download limit.")
    return data


def acquire_binary(source, base, home, *, download=fetch, candidate=None, system=None):
    system = system or f"{platform.system()}-{platform.machine()}"
    system = system.replace("aarch64", "arm64")
    catalog = json_read(source / "artifacts.json")
    archive = catalog["archives"].get(system)
    if not archive or catalog["version"] != VERSION:
        raise SetupError("Supported platforms are macOS/Linux on arm64 or x86_64.")
    receipt_path = base / "binary.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        receipt = json_read(receipt_path, private=True)
        if receipt.get("version") != VERSION or receipt.get("sha256") != binary_hash(Path(receipt["path"])):
            raise SetupError("Managed binary provenance changed; refusing reuse.")
        return receipt
    candidate = candidate or shutil.which("mcp-grafana")
    receipt = None
    if candidate:
        try:
            receipt = homebrew_binary(Path(candidate))
        except (SetupError, OSError, KeyError, TypeError, AttributeError):
            receipt = None
    mkdir_private(base, home)
    if receipt is None:
        url = f"https://github.com/grafana/mcp-grafana/releases/download/v{VERSION}/{archive['name']}"
        data = download(url)
        if digest(data) != archive["sha256"]:
            raise SetupError("Official release checksum mismatch; binary not installed.")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            members = [member for member in tar.getmembers() if member.name == "mcp-grafana"]
            if len(members) != 1 or not members[0].isfile() or members[0].size > 256 * 1024 * 1024:
                raise SetupError("Release archive does not contain one regular MCP executable.")
            stream = tar.extractfile(members[0])
            if stream is None:
                raise SetupError("Release executable is missing.")
            executable = stream.read()
        target = base / "mcp-grafana"
        if target.exists() or target.is_symlink():
            # Recover a crash after binary publication but before its receipt.
            # Never adopt or overwrite an unknown executable.
            check_path(target, home, directory=False)
            if target.stat().st_mode & 0o777 != 0o700 or read_bytes(target, limit=256 * 1024 * 1024) != executable:
                raise SetupError("Unrecorded binary differs from the verified release.")
        else:
            atomic_write(target, executable, home, mode=0o700)
        receipt = {"path": str(target), "sha256": digest(executable), "version": VERSION, "source": url}
    atomic_write(receipt_path, json_bytes(receipt), home)
    return receipt
