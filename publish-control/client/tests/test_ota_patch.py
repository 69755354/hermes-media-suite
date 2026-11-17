"""tools/ota_patch.py: OTA patches are built from git and proven complete.

A throw-away git repo with the real layout (publish-control/client/...) and
three releases is enough to exercise every gate: an incomplete patch for an
older install (the 1.2.218 failure), a patch that is complete but does not
start, signing with the matching key, and byte-stable builds.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
sys.path.insert(0, str(CLIENT / "agent"))

import devsign  # noqa: E402
import ota_patch  # noqa: E402

MAIN_OK = "import argparse\nfrom winport import mod_a%s\nargparse.ArgumentParser().parse_args()\n"


@unittest.skipIf(shutil.which("git") is None, "git not installed")
class OtaPatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        self.client = self.repo / "publish-control" / "client"
        (self.client / "agent" / "winport").mkdir(parents=True)
        (self.client / "config").mkdir()
        self.seed = bytes(range(32))
        (self.client / "config" / "vendor_pubkey.hex").write_text(
            devsign.publickey(self.seed).hex() + "\n", encoding="utf-8")
        self._git("init", "-q")
        self._git("config", "user.email", "t@example.test")
        self._git("config", "user.name", "t")
        self.out = Path(tmp.name) / "out"
        # 1.0.1: base.  1.0.2: adds mod_b and imports it.  1.0.3: edits mod_a.
        self._release("1.0.1", {"agent/winport/__init__.py": "",
                                "agent/winport/mod_a.py": "A = 1\n",
                                "agent/winport/__main__.py": MAIN_OK % ""})
        self._release("1.0.2", {"agent/winport/mod_b.py": "B = 1\n",
                                "agent/winport/__main__.py": MAIN_OK % ", mod_b"})
        self._release("1.0.3", {"agent/winport/mod_a.py": "A = 2\n",
                                "tests/test_x.py": "# dev only\n"})

    def _git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                       capture_output=True)

    def _release(self, version, files):
        for rel, text in files.items():
            path = self.client / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.client / "VERSION").write_text(version + "\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", version)

    def _build(self, min_version, out=None, **kw):
        return ota_patch.build(self.repo, "HEAD", min_version, out or self.out,
                               url_base="https://example.test/u", notes="t",
                               sign_seed=self.seed, **kw)

    def _check(self, **kw):
        return ota_patch.check(self.repo, "HEAD", self.out / "manifest.json",
                               self.out / "patch-1.0.3.zip", **kw)

    def test_release_points_come_from_version_history(self):
        points = ota_patch.release_points(self.repo, "HEAD")
        self.assertEqual(sorted(points), ["1.0.1", "1.0.2", "1.0.3"])

    def test_patch_covers_every_release_point_and_starts(self):
        manifest = self._build("1.0.1")
        paths = sorted(f["path"] for f in manifest["files"])
        self.assertEqual(paths, ["agent/winport/__main__.py", "agent/winport/mod_a.py",
                                 "agent/winport/mod_b.py"])          # tests/ not shipped
        report = self._check(simulate=True)
        self.assertTrue(report["ok"], report["fails"])
        self.assertEqual({v: r["status"] for v, r in report["per_version"].items()},
                         {"1.0.1": "OK", "1.0.2": "OK"})

    def test_min_version_lower_than_the_patch_covers_is_caught(self):
        # The 1.2.218 shape: patch built for >= 1.0.2, manifest claims 1.0.1.
        self._build("1.0.2")
        mpath = self.out / "manifest.json"
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        self.assertEqual([f["path"] for f in manifest["files"]], ["agent/winport/mod_a.py"])
        manifest["min_version"] = "1.0.1"
        manifest.pop("signature")
        mpath.write_text(json.dumps(manifest), encoding="utf-8")
        report = self._check(require_signature=False)
        self.assertFalse(report["ok"])
        self.assertEqual(report["per_version"]["1.0.1"]["missing"],
                         ["agent/winport/__main__.py", "agent/winport/mod_b.py"])

    def test_complete_but_broken_patch_fails_the_start_simulation(self):
        self._release("1.0.4", {"agent/winport/__main__.py": "import winport.nope\n"})
        ota_patch.build(self.repo, "HEAD", "1.0.3", self.out, url_base="",
                        notes="", sign_seed=self.seed)
        report = ota_patch.check(self.repo, "HEAD", self.out / "manifest.json",
                                 self.out / "patch-1.0.4.zip", simulate=True)
        self.assertFalse(report["ok"])
        self.assertEqual(report["per_version"]["1.0.3"]["status"], "START_FAIL")

    def test_signature_and_tamper(self):
        self._build("1.0.1")
        self.assertTrue(self._check()["ok"])
        mpath = self.out / "manifest.json"
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        manifest["notes"] += "x"
        mpath.write_text(json.dumps(manifest), encoding="utf-8")
        report = self._check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("signature" in f for f in report["fails"]))

    def test_zip_must_match_target_source(self):
        import zipfile
        self._build("1.0.1")
        zpath = self.out / "patch-1.0.3.zip"
        with zipfile.ZipFile(zpath, "a") as zf:
            zf.writestr("agent/winport/extra.py", "X = 1\n")
        report = self._check()
        self.assertFalse(report["ok"])
        self.assertTrue(any("sha256" in f for f in report["fails"]))
        self.assertTrue(any("zip entries" in f for f in report["fails"]))

    def test_builds_are_byte_stable(self):
        m1 = self._build("1.0.1", released_at="2026-01-01T00:00:00+00:00")
        m2 = self._build("1.0.1", out=self.out.with_name("out2"),
                         released_at="2026-01-01T00:00:00+00:00")
        self.assertEqual(m1["patch_zip_sha256"], m2["patch_zip_sha256"])
        self.assertEqual(m1["signature"], m2["signature"])

    def test_min_version_without_git_source_is_refused(self):
        with self.assertRaises(SystemExit):
            self._build("1.0.0")


if __name__ == "__main__":
    unittest.main()
