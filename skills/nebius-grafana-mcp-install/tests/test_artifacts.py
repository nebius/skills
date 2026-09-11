"""Verify pinned acquisition and interruption recovery without network access."""

import io
import tarfile
import unittest
from unittest import mock

from fixtures import FakeSystem
from common import SetupError, digest, json_bytes
import materialize


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSystem()
        self.addCleanup(self.fake.close)
        self.base = self.fake.home / "binary"

    def archive(self, kind="regular"):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            member = tarfile.TarInfo("mcp-grafana")
            if kind == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                archive.addfile(member)
            else:
                payload = b"#!/bin/sh\nexit 0\n"
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
        data = output.getvalue()
        catalog = {"version": "1.4.0", "archives": {"Linux-x86_64": {
            "name": "fixture.tar.gz", "sha256": digest(data)}}}
        (self.fake.source / "artifacts.json").write_bytes(json_bytes(catalog))
        return data

    def acquire(self, data):
        return materialize.acquire_binary(self.fake.source, self.base, self.fake.home,
                                          download=lambda url: data, candidate="/nonexistent-fixture",
                                          system="Linux-x86_64")

    def test_checksum_mismatch_publishes_nothing(self):
        self.archive()
        with self.assertRaisesRegex(SetupError, "checksum mismatch"):
            self.acquire(b"corrupt")
        self.assertFalse((self.base / "mcp-grafana").exists())
        self.assertFalse((self.base / "binary.json").exists())

    def test_archive_symlink_is_not_extracted(self):
        with self.assertRaisesRegex(SetupError, "regular MCP executable"):
            self.acquire(self.archive("symlink"))
        self.assertFalse((self.base / "mcp-grafana").exists())

    def test_receipt_interruption_recovers_only_exact_verified_binary(self):
        data = self.archive()
        write = materialize.atomic_write

        def interrupted(path, *args, **kwargs):
            if path.name == "binary.json":
                raise SetupError("Fixture interrupted receipt publication.")
            return write(path, *args, **kwargs)

        with mock.patch.object(materialize, "atomic_write", side_effect=interrupted):
            with self.assertRaisesRegex(SetupError, "interrupted"):
                self.acquire(data)
        binary = self.base / "mcp-grafana"
        self.assertEqual(binary.stat().st_mode & 0o777, 0o700)
        inode = binary.stat().st_ino
        receipt = self.acquire(data)
        self.assertEqual(binary.stat().st_ino, inode)
        self.assertEqual(receipt["sha256"], digest(binary.read_bytes()))
        with mock.patch.object(materialize, "fetch", side_effect=AssertionError("No network")):
            self.assertEqual(self.acquire(b"not downloaded"), receipt)
        (self.base / "binary.json").unlink()
        binary.write_bytes(b"unrecorded different executable")
        with self.assertRaisesRegex(SetupError, "differs from the verified"):
            self.acquire(data)

    def test_unknown_platform_fails_before_download(self):
        with self.assertRaisesRegex(SetupError, "Supported platforms"):
            materialize.acquire_binary(self.fake.source, self.base, self.fake.home,
                                       system="Unknown-platform",
                                       download=lambda url: self.fail("Unexpected download"))
