import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interlock.cli import _write


class ArtifactWriteTests(unittest.TestCase):
    def test_failed_flush_preserves_old_artifact_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "witness.json"
            destination.write_text("previous witness")
            with patch("interlock.cli.os.fsync", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    _write(str(destination), {"new": "witness"}, force=True)
            self.assertEqual(destination.read_text(), "previous witness")
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_failed_publish_preserves_old_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            destination.write_text("previous report")
            with patch("interlock.cli.os.replace", side_effect=OSError("cannot replace")):
                with self.assertRaises(OSError):
                    _write(str(destination), {"new": "report"}, force=True)
            self.assertEqual(destination.read_text(), "previous report")
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_concurrent_destination_is_not_overwritten_without_force(self):
        original_link = os.link
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"

            def publish_after_competing_writer(source, target):
                destination.write_text("other writer")
                original_link(source, target)

            with patch("interlock.cli.os.link", side_effect=publish_after_competing_writer):
                with self.assertRaises(FileExistsError):
                    _write(str(destination), {"our": "report"})
            self.assertEqual(destination.read_text(), "other writer")
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_atomic_replace_does_not_modify_other_hardlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            destination, alias = Path(directory) / "report.json", Path(directory) / "old.json"
            destination.write_text("old contents")
            alias.hardlink_to(destination)
            _write(str(destination), {"new": "report"}, force=True)
            self.assertEqual(json.loads(destination.read_text()), {"new": "report"})
            self.assertEqual(alias.read_text(), "old contents")

    def test_forced_symlink_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target, link = Path(directory) / "target.json", Path(directory) / "report.json"
            target.write_text("keep")
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                _write(str(link), {"new": "report"}, force=True)
            self.assertEqual(target.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
