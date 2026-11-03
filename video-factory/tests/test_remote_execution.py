"""跨机执行通道的无费用契约测试。"""
# > 执行者：codex

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import httpx

from app.remote_execution import RemoteExecutionClient, RemoteExecutionError


class RemoteExecutionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.key = Path(self.temp.name) / "id_ed25519"
        self.key.write_text("test-only", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def client(self, handler) -> RemoteExecutionClient:
        return RemoteExecutionClient(
            "http://execution.test",
            ssh_host="sg.test",
            ssh_user="ubuntu",
            ssh_key=self.key,
            transport=httpx.MockTransport(handler),
        )

    def test_ping_and_persistent_job_status_contract(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/ping":
                return httpx.Response(200, json={"status": "alive"})
            if request.url.path == "/job/status":
                return httpx.Response(200, json={"id": "abc123", "status": "running"})
            return httpx.Response(404, json={"error": "not found"})

        client = self.client(handler)
        try:
            self.assertTrue(client.ping())
            self.assertEqual(client.status("abc123")["status"], "running")
        finally:
            client.close()

    def test_oral_content_cannot_be_misrouted_to_seedance(self) -> None:
        client = self.client(lambda _: httpx.Response(500))
        try:
            with self.assertRaisesRegex(RemoteExecutionError, "婵镜"):
                client.submit("prj_test", "测试", [], content_type="oral")
        finally:
            client.close()

    def test_result_path_must_stay_in_singapore_cache(self) -> None:
        client = self.client(lambda _: httpx.Response(500))
        try:
            with self.assertRaisesRegex(RemoteExecutionError, "允许目录"):
                client.download("/tmp/escape.mp4", Path(self.temp.name) / "out.mp4")
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
