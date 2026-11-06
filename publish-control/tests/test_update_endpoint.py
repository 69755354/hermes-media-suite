"""/update/<file>: public, read-only distribution of signed update artefacts.

Trust comes from the Ed25519-signed manifest the client verifies, so the
endpoint itself only has to (1) never serve anything outside the update
directory and (2) not hold whole packages in memory.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


class UpdateEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server_mod = server
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.updates = base / "updates"
        cls.updates.mkdir()
        (base / "secret.json").write_text('{"token":"must-not-leak"}', encoding="utf-8")
        cls.old_db, cls.old_env = server.DB, os.environ.get("CONTROL_UPDATE_DIR")
        server.DB = str(base / "control.db")
        server._initialized.clear()
        server.init()
        os.environ["CONTROL_UPDATE_DIR"] = str(cls.updates)
        cls.old_chunk = server.UPDATE_CHUNK_BYTES
        server.UPDATE_CHUNK_BYTES = 4096  # force many chunks on a small file
        cls.manifest = b'{"version":"1.2.189","signature":"x"}'
        (cls.updates / "manifest-1.2.189.json").write_bytes(cls.manifest)
        cls.blob = os.urandom(3 * 4096 + 17)
        (cls.updates / "patch-1.2.189.zip").write_bytes(cls.blob)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        cls.base_url = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server_mod.DB = cls.old_db
        cls.server_mod._initialized.clear()
        cls.server_mod.UPDATE_CHUNK_BYTES = cls.old_chunk
        if cls.old_env is None:
            os.environ.pop("CONTROL_UPDATE_DIR", None)
        else:
            os.environ["CONTROL_UPDATE_DIR"] = cls.old_env
        cls.tmp.cleanup()

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_manifest_served_as_json(self):
        status, headers, body = self._get("/update/manifest-1.2.189.json")
        self.assertEqual(status, 200)
        self.assertEqual(body, self.manifest)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_zip_streamed_intact_across_chunks(self):
        status, headers, body = self._get("/update/patch-1.2.189.zip")
        self.assertEqual(status, 200)
        self.assertEqual(int(headers["Content-Length"]), len(self.blob))
        self.assertEqual(hashlib.sha256(body).hexdigest(), hashlib.sha256(self.blob).hexdigest())

    def test_nothing_outside_the_update_dir(self):
        for path in ("/update/../secret.json", "/update/..%2Fsecret.json", "/update/%2e%2e/secret.json",
                     "/update/.hidden.json", "/update/manifest-1.2.189.txt", "/update/", "/update/a/b.json",
                     "/update/missing.zip"):
            status, _, body = self._get(path)
            self.assertIn(status, (400, 404), path)
            self.assertNotIn(b"must-not-leak", body, path)


if __name__ == "__main__":
    unittest.main()
