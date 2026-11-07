"""The public /update/ endpoint: name whitelist, no traversal, chunked send.

The manifest that customers verify is Ed25519-signed, so serving these files
publicly is by design; the risk here is the file-serving surface itself.
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server


class _Handler:
    """Minimal stand-in for BaseHTTPRequestHandler with a real write stream."""

    def __init__(self):
        self.wfile = io.BytesIO()
        self.status = None
        self.headers = {}
        self.body = None

    def send_response(self, code):
        self.status = code

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass

    def _send(self, code, payload):
        self.status = code
        self.body = payload


class UpdateEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="update-ep-")
        self.blob = os.urandom(700 * 1024)  # larger than one 256KB chunk
        Path(self.tmp, "patch-1.2.189.zip").write_bytes(self.blob)
        Path(self.tmp, "manifest.json").write_text('{"version":"1.2.189"}')
        self.env = mock.patch.dict(os.environ, {"CONTROL_UPDATE_DIR": self.tmp})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def _serve(self, name):
        h = _Handler()
        server.H._send_update_file(h, name)
        return h

    def test_serves_known_patch_with_length_and_bytes(self):
        h = self._serve("patch-1.2.189.zip")
        self.assertEqual(h.status, 200)
        self.assertEqual(h.headers["Content-Length"], str(len(self.blob)))
        self.assertEqual(h.headers["Content-Type"], "application/zip")
        self.assertEqual(h.wfile.getvalue(), self.blob)

    def test_manifest_is_json(self):
        h = self._serve("manifest.json")
        self.assertEqual(h.status, 200)
        self.assertIn("application/json", h.headers["Content-Type"])

    def test_traversal_and_odd_names_are_404(self):
        for name in ["../control.db", "..%2fcontrol.db", "sub/patch.zip",
                     "patch-1.2.189.zip/../../x", ".hidden", "",
                     "patch-1.2.189.exe", "a" * 90 + ".zip", "patch 1.zip"]:
            with self.subTest(name=name):
                h = self._serve(name)
                self.assertEqual(h.status, 404, name)

    def test_missing_file_is_404(self):
        self.assertEqual(self._serve("patch-9.9.9.zip").status, 404)


if __name__ == "__main__":
    unittest.main()
