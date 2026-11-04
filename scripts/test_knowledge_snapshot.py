"""Snapshot safety and portability checks, using only temporary fixture notes."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("knowledge_snapshot", Path(__file__).with_name("knowledge-snapshot.py"))
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "export"

    def note(self, relative, content=b"# Note\n"):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def export(self, **kwargs):
        return snapshot.create_snapshot(self.source, self.output, source_kind="directory", **kwargs)

    def test_preserves_bytes_and_paths_and_survives_source_going_offline(self):
        raw = "---\r\ntitle: Decisão\r\n---\r\n# Olá\r\n[[Outra]]\r\n".encode()
        note = self.note("Research/Decisão.md", raw)
        before = note.stat().st_mtime_ns
        result = self.export()
        self.assertEqual(result["notes_copied"], 1)
        self.assertEqual(note.read_bytes(), raw)
        self.assertEqual(note.stat().st_mtime_ns, before)
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertTrue(manifest["complete"])
        self.assertFalse(manifest["affine_import_verified"])
        self.assertFalse(manifest["media_included"])
        record = manifest["files"][0]
        self.assertEqual(record["original_relative_path"], "Research/Decisão.md")
        self.assertEqual(record["sha256"], snapshot.hashlib.sha256(raw).hexdigest())
        shutil.move(str(self.source), str(self.root / "offline-source"))
        self.assertEqual((self.output / "vault" / record["snapshot_path"]).read_bytes(), raw)
        with zipfile.ZipFile(self.output / "affine-pilot.zip") as archive:
            self.assertEqual(archive.read("vault/Research/Decisão.md"), raw)
            self.assertTrue(all(name.startswith("vault/") for name in archive.namelist()))
            self.assertNotIn("manifest.json", archive.namelist())

    def test_empty_source_fails_without_creating_output(self):
        with self.assertRaisesRegex(snapshot.SnapshotError, "empty pilot"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.note("A.md")
        self.output.mkdir()
        marker = self.output / "keep"
        marker.write_text("original")
        with self.assertRaisesRegex(snapshot.SnapshotError, "already exists"):
            self.export()
        self.assertEqual(marker.read_text(), "original")

    def test_export_inside_source_is_rejected(self):
        self.note("A.md")
        with self.assertRaisesRegex(snapshot.SnapshotError, "outside"):
            snapshot.create_snapshot(self.source, self.source / "export", source_kind="directory")

    @patch.object(snapshot.subprocess, "run")
    def test_unmounted_local_directory_cannot_be_mistaken_for_live_vault(self, run):
        self.note("A.md")
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps({
            "filesystems": [{"source": "/dev/root", "target": "/", "fstype": "ext4"}]}), "")
        with self.assertRaisesRegex(snapshot.SnapshotError, "not mounted"):
            snapshot.create_snapshot(self.source, self.output)
        self.assertFalse(self.output.exists())

    @patch.object(snapshot.subprocess, "run")
    def test_wrong_mount_identity_is_rejected(self, run):
        self.note("A.md")
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps({
            "filesystems": [{"source": "some-other-vault", "target": str(self.source), "fstype": "fuse.sshfs"}]}), "")
        with self.assertRaisesRegex(snapshot.SnapshotError, "identity differs"):
            snapshot.create_snapshot(self.source, self.output)

    def test_hidden_configuration_generated_files_and_symlinks_are_excluded(self):
        self.note("A.md")
        self.note(".obsidian/private.md", b"secret configuration")
        self.note(".trash/Deleted.md")
        self.note("_AgentKnowledge/Old projection.md")
        self.note(".hidden.md")
        outside = self.root / "outside.md"
        outside.write_bytes(b"external private content")
        (self.source / "linked.md").symlink_to(outside)
        external_dir = self.root / "external-dir"
        external_dir.mkdir()
        (external_dir / "B.md").write_bytes(b"outside directory")
        (self.source / "linked-dir").symlink_to(external_dir, target_is_directory=True)
        self.export()
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual([entry["original_relative_path"] for entry in manifest["files"]], ["A.md"])

    def test_limit_is_deterministic_and_index_does_not_overwrite_a_note(self):
        self.note("Z.md")
        self.note("A.md")
        self.note("Knowledge Pilot Index.md", b"original note")
        result = self.export(limit=2)
        self.assertEqual(result["notes_available"], 3)
        self.assertEqual(result["notes_copied"], 2)
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(manifest["generated_index"]["path"], "Knowledge Pilot Index 2.md")
        self.assertEqual((self.output / "vault/Knowledge Pilot Index.md").read_bytes(), b"original note")

    def test_case_collisions_fail_before_output_is_created(self):
        self.note("A.md")
        # Model the Linux source's distinct paths even on a case-insensitive Mac.
        paths = [self.source.resolve() / "A.md", self.source.resolve() / "a.MD"]
        with patch.object(snapshot, "markdown_files", return_value=paths):
            with self.assertRaisesRegex(snapshot.SnapshotError, "collide"):
                self.export()
        self.assertFalse(self.output.exists())

    def test_note_changed_during_read_is_rejected(self):
        note = self.note("A.md", b"original")
        original_fstat = os.fstat
        old_stat = note.stat()
        calls = 0

        def changing_stat(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                os.utime(note, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000_000))
            return original_fstat(fd)

        with patch.object(snapshot.os, "fstat", side_effect=changing_stat):
            with self.assertRaisesRegex(snapshot.SnapshotError, "changed during capture"):
                self.export()
        self.assertFalse(self.output.exists())

    def test_entry_and_total_limits_fail_without_partial_export(self):
        self.note("A.md", b"123456")
        with patch.object(snapshot, "MAX_ENTRY_BYTES", 5):
            with self.assertRaises(snapshot.SnapshotError):
                self.export()
        self.assertFalse(self.output.exists())
        with patch.object(snapshot, "MAX_TOTAL_BYTES", 5):
            with self.assertRaises(snapshot.SnapshotError):
                self.export()
        self.assertFalse(self.output.exists())

    def test_failed_archive_creation_cleans_up_only_new_export(self):
        original = self.note("A.md", b"original")
        with patch.object(snapshot.zipfile, "ZipFile", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.export()
        self.assertFalse(self.output.exists())
        self.assertEqual(original.read_bytes(), b"original")

    def test_non_utf8_note_is_reported(self):
        self.note("A.md", b"\xff\xfeinvalid")
        with self.assertRaisesRegex(snapshot.SnapshotError, "UTF-8"):
            self.export()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
