"""Exercise installation using temporary directories only."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


INSTALL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install.py"
SPEC = importlib.util.spec_from_file_location("relay_skill_install", INSTALL_PATH)
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "repo" / "skills" / "relay-media"
        self.source.mkdir(parents=True)
        (self.source / "SKILL.md").write_text("---\nname: relay-media\ndescription: Generate media.\n---\n", encoding="utf-8")
        (self.source / "scripts").mkdir()
        (self.source / "scripts" / "generate.py").write_text("print('ready')\n", encoding="utf-8")
        self.destination = self.root / "codex" / "skills"

    def make_existing(self) -> Path:
        target = self.destination / "relay-media"
        target.mkdir(parents=True)
        (target / "personal.txt").write_text("keep this", encoding="utf-8")
        return target

    def test_install_copies_only_skill_resources(self) -> None:
        (self.source / "README.md").write_text("repository documentation", encoding="utf-8")
        (self.source / ".env").write_text("API_KEY=not-a-real-key", encoding="utf-8")
        (self.source / "scripts" / "credentials.json").write_text("{}", encoding="utf-8")
        (self.source / "scripts" / "__pycache__").mkdir()
        (self.source / "scripts" / "__pycache__" / "generate.pyc").write_bytes(b"cache")
        result = installer.install(self.source, self.destination)
        self.assertEqual(result.target, self.destination / "relay-media")
        self.assertEqual(set(result.files), {"SKILL.md", "scripts/generate.py"})
        self.assertEqual((result.target / "scripts" / "generate.py").read_text(encoding="utf-8"), "print('ready')\n")
        self.assertFalse((result.target / "README.md").exists())
        self.assertFalse((result.target / ".env").exists())
        self.assertFalse((result.target / "scripts" / "credentials.json").exists())
        self.assertFalse((result.target / "scripts" / "__pycache__").exists())
        self.assertEqual(list(self.destination.iterdir()), [result.target])

    def test_existing_skill_requires_force_and_is_untouched(self) -> None:
        target = self.make_existing()
        with self.assertRaisesRegex(installer.InstallError, "already exists.*--force"):
            installer.install(self.source, self.destination)
        self.assertEqual((target / "personal.txt").read_text(encoding="utf-8"), "keep this")
        self.assertEqual(list(self.destination.iterdir()), [target])

    def test_force_preserves_original_in_sibling_backup(self) -> None:
        target = self.make_existing()
        (target / ".env").write_text("PRIVATE=preserved-locally", encoding="utf-8")
        result = installer.install(self.source, self.destination, force=True)
        self.assertIsNotNone(result.backup)
        self.assertEqual(result.backup.parent, self.destination)
        self.assertEqual((result.backup / "personal.txt").read_text(encoding="utf-8"), "keep this")
        self.assertTrue((result.backup / ".env").is_file())
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertFalse((target / "personal.txt").exists())
        self.assertEqual(set(self.destination.iterdir()), {target, result.backup})

    def test_dry_run_does_not_create_missing_destination(self) -> None:
        result = installer.install(self.source, self.destination, dry_run=True)
        self.assertTrue(result.dry_run)
        self.assertIn("SKILL.md", result.files)
        self.assertFalse(self.destination.parent.exists())

    def test_force_dry_run_does_not_move_existing_skill(self) -> None:
        target = self.make_existing()
        result = installer.install(self.source, self.destination, force=True, dry_run=True)
        self.assertIsNone(result.backup)
        self.assertEqual((target / "personal.txt").read_text(encoding="utf-8"), "keep this")
        self.assertEqual(list(self.destination.iterdir()), [target])

    def test_rejects_equal_or_nested_source_and_target(self) -> None:
        for destination in (self.source.parent, self.source / "nested"):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(installer.InstallError, "same or nested"):
                    installer.install(self.source, destination, force=True)
        enclosing_destination = self.root / "enclosing"
        nested_source = enclosing_destination / "relay-media" / "source"
        nested_source.mkdir(parents=True)
        (nested_source / "SKILL.md").write_text("skill", encoding="utf-8")
        with self.assertRaisesRegex(installer.InstallError, "same or nested"):
            installer.install(nested_source, enclosing_destination, force=True)
        self.assertTrue((nested_source / "SKILL.md").is_file())

    def test_failed_publish_restores_original(self) -> None:
        target = self.make_existing()
        original_rename = Path.rename

        def fail_staging_rename(path: Path, destination: Path) -> Path:
            if path.name.startswith(".relay-media.staging-"):
                raise OSError("simulated publish failure")
            return original_rename(path, destination)

        with mock.patch.object(Path, "rename", new=fail_staging_rename):
            with self.assertRaisesRegex(installer.InstallError, "original skill was restored"):
                installer.install(self.source, self.destination, force=True)
        self.assertEqual((target / "personal.txt").read_text(encoding="utf-8"), "keep this")
        self.assertEqual(list(self.destination.iterdir()), [target])

    def test_failed_copy_keeps_original_and_removes_own_staging(self) -> None:
        target = self.make_existing()
        with mock.patch.object(installer.shutil, "copy2", side_effect=OSError("simulated copy failure")):
            with self.assertRaisesRegex(OSError, "simulated copy failure"):
                installer.install(self.source, self.destination, force=True)
        self.assertEqual((target / "personal.txt").read_text(encoding="utf-8"), "keep this")
        self.assertEqual(list(self.destination.iterdir()), [target])

    def test_rejects_link_target_and_destination_parent(self) -> None:
        real = self.root / "real"
        real.mkdir()
        linked = self.root / "linked"
        try:
            linked.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks is unavailable for this account")
        for destination in (linked / "skills", self.destination):
            with self.subTest(destination=destination):
                if destination == self.destination:
                    destination.mkdir(parents=True)
                    (destination / "relay-media").symlink_to(real, target_is_directory=True)
                with self.assertRaisesRegex(installer.InstallError, "symlink or junction"):
                    installer.install(self.source, destination, force=True)
        self.assertEqual(list(real.iterdir()), [])

    def test_default_destination_honors_environment(self) -> None:
        configured = self.root / "custom-codex"
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(configured)}):
            self.assertEqual(installer.default_destination(), configured / "skills")
        with mock.patch.dict(os.environ, {"CODEX_HOME": ""}), mock.patch.object(Path, "home", return_value=self.root):
            self.assertEqual(installer.default_destination(), self.root / ".codex" / "skills")


if __name__ == "__main__":
    unittest.main()
