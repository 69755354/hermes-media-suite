"""bootstrap_py._purge_leftover_dirs deletes directories on customer machines.

Every rule that keeps something alive gets a case: the current install, a
newer install (rollback), the running installer and its data, symlinks,
folders that only *look* like ours, and vendor app-1.x dirs outside the vendor
root.  Processes are not touched here (_stop_processes_in_dir is stubbed).
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "client" / "scripts" / "bootstrap_py.py"


def _load():
    spec = importlib.util.spec_from_file_location("bootstrap_py_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._stop_processes_in_dir = lambda root, log: 0
    return mod


def _product(path: Path, version=None, bat=True):
    path.mkdir(parents=True)
    if bat:
        (path / "bootstrap.bat").write_text("@echo off", encoding="utf-8")
    if version is not None:
        (path / "MANIFEST.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (path / "agent.bin").write_bytes(b"x" * 10)
    return path


class PurgeLeftoverDirsTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "Desktop"
        self.root.mkdir()
        self.logs = []

    def _purge(self, current="1.2.189", keep=(), protected=(), roots=None):
        keep = {os.path.normcase(os.path.abspath(str(k))) for k in keep}
        return self.mod._purge_leftover_dirs(roots or [self.root], keep, current, self.logs.append,
                                             protected=tuple(protected))

    def test_removes_an_older_install(self):
        old = _product(self.root / "manju-publish-assistant-1.2.100-win64", "1.2.100")
        self.assertEqual(self._purge(), 1)
        self.assertFalse(old.exists())

    def test_keeps_current_and_newer(self):
        cur = _product(self.root / "manju-publish-assistant-1.2.189-win64", "1.2.189")
        new = _product(self.root / "manju-publish-assistant-1.2.200-win64", "1.2.200")
        self.assertEqual(self._purge(), 0)
        self.assertTrue(cur.exists() and new.exists())

    def test_keeps_a_newer_install_with_a_revision_suffix(self):
        # Rollback: an older installer must not delete "1.2.174-r2".
        new = _product(self.root / "manju-publish-assistant-1.2.174-r2", "1.2.174-r2")
        self.assertEqual(self._purge(current="1.2.170"), 0)
        self.assertTrue(new.exists())

    def test_unparseable_version_is_kept(self):
        odd = _product(self.root / "publish-assistant-nightly", "nightly-build")
        self.assertEqual(self._purge(), 0)
        self.assertTrue(odd.exists())

    def test_version_from_folder_name_when_manifest_missing(self):
        old = _product(self.root / "publish-assistant-1.2.49")
        self.assertEqual(self._purge(), 1)
        self.assertFalse(old.exists())

    def test_keep_and_protected_paths(self):
        kept = _product(self.root / "publish-worker-1.2.10", "1.2.10")
        running = _product(self.root / "huolong-publish-1.2.11", "1.2.11")
        self.assertEqual(self._purge(keep=[kept], protected=[running / "agent"]), 0)
        self.assertTrue(kept.exists() and running.exists())

    def test_lookalike_without_bootstrap_is_kept(self):
        notes = self.root / "publish-assistant-notes-1.0.0"
        notes.mkdir()
        (notes / "my.docx").write_bytes(b"user data")
        self.assertEqual(self._purge(), 0)
        self.assertTrue((notes / "my.docx").exists())

    @unittest.skipIf(os.name == "nt", "symlink creation needs privileges on Windows")
    def test_symlink_named_like_a_product_is_never_followed(self):
        precious = _product(Path(self.root.parent) / "precious", "1.2.1")
        link = self.root / "publish-worker-1.2.1"
        link.symlink_to(precious, target_is_directory=True)
        self.assertEqual(self._purge(), 0)
        self.assertTrue((precious / "agent.bin").exists())

    def test_vendor_app_dirs_only_under_the_vendor_root(self):
        loose = _product(self.root / "app-1.2.118", "1.2.118")
        vendor = Path(self.root.parent) / "HuolongAgent"
        inside = _product(vendor / "app-1.2.118", "1.2.118")
        self.assertEqual(self._purge(roots=[self.root, vendor]), 1)
        self.assertTrue(loose.exists())
        self.assertFalse(inside.exists())

    def test_nested_container_is_cleaned_and_removed_when_empty(self):
        box = self.root / "manju-publish-assistant-1"
        _product(box / "manju-publish-assistant-1.2.100-win64", "1.2.100")
        self.assertEqual(self._purge(), 1)
        self.assertFalse(box.exists())

    def test_container_with_user_files_survives(self):
        box = self.root / "manju-publish-assistant-1"
        _product(box / "manju-publish-assistant-1.2.100-win64", "1.2.100")
        (box / "客户素材.mp4").write_bytes(b"video")
        self._purge()
        self.assertTrue((box / "客户素材.mp4").exists())


class VersionTupleTests(unittest.TestCase):
    def test_suffixes_compare_by_their_numbers(self):
        vt = _load()._version_tuple
        self.assertEqual(vt("1.2.174-r2"), (1, 2, 174))
        self.assertGreater(vt("1.2.174-r2"), vt("1.2.170"))
        self.assertEqual(vt("1.2.189"), (1, 2, 189))
        self.assertIsNone(vt("nightly"))
        self.assertIsNone(vt(""))


if __name__ == "__main__":
    unittest.main()
