from __future__ import annotations
# > 执行者：codex

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient


os.environ.setdefault("XG_FACTORY_OPS_PASSWORD", "ops-test-password")
os.environ.setdefault("XG_FACTORY_SESSION_SECRET", "test-session-secret-must-be-at-least-32-bytes")
os.environ.setdefault("XG_FACTORY_DB", "/tmp/factory-prefix-import.sqlite3")
os.environ.setdefault("XG_FACTORY_PROJECTS_DIR", "/tmp/factory-prefix-import-projects")

from app.main import create_app
from tests.test_p1_platform import FakeBillingClient, drama_payload, minimal_hotpot_payload, oral_payload


APP_ROOT = Path(__file__).resolve().parents[1]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for attribute in ("href", "src"):
            value = values.get(attribute)
            if value:
                self.urls.append((attribute, value))


@contextmanager
def configured_root_path(value: str):
    previous = os.environ.get("XG_FACTORY_ROOT_PATH")
    if value:
        os.environ["XG_FACTORY_ROOT_PATH"] = value
    else:
        os.environ.pop("XG_FACTORY_ROOT_PATH", None)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("XG_FACTORY_ROOT_PATH", None)
        else:
            os.environ["XG_FACTORY_ROOT_PATH"] = previous


class FactoryPrefixTests(unittest.TestCase):
    def _run_mode(self, prefix: str) -> None:
        with configured_root_path(prefix), tempfile.TemporaryDirectory(prefix="factory-prefix-") as temporary:
            runtime = Path(temporary)
            billing = FakeBillingClient()
            app = create_app(runtime / "platform.sqlite3", runtime / "projects", start_worker=False, billing_client=billing)
            client = TestClient(app)
            route = lambda path: f"{prefix}{path}"

            anonymous_home = client.get(route("/"), follow_redirects=False)
            self.assertEqual(anonymous_home.status_code, 303, anonymous_home.text)
            self.assertEqual(anonymous_home.headers["location"], route("/access"))

            client_login = client.post(
                route("/api/v1/billing/access"), json={"customer_id": "101"}
            )
            self.assertEqual(client_login.status_code, 200, client_login.text)
            expected_client_next = route("/projects")
            self.assertEqual(client_login.json()["next"], expected_client_next)
            client_csrf = client_login.json()["csrf"]
            authenticated_home = client.get(route("/"), follow_redirects=False)
            self.assertEqual(authenticated_home.status_code, 303, authenticated_home.text)
            self.assertEqual(authenticated_home.headers["location"], route("/projects"))

            ops_login = client.post(
                route("/api/v1/auth/login"),
                json={"account": "审核员", "password": "ops-test-password", "role": "ops"},
            )
            self.assertEqual(ops_login.status_code, 200, ops_login.text)
            self.assertEqual(ops_login.json()["next"], route("/ops"))
            ops_csrf = ops_login.json()["csrf"]

            if prefix:
                set_cookie = client_login.headers.get_list("set-cookie")
                self.assertTrue(any("Path=/factory/" in value for value in set_cookie), set_cookie)
                self.assertTrue(any("Path=/;" in value and "Max-Age=0" in value for value in set_cookie), set_cookie)
            else:
                self.assertIn("Path=/;", client_login.headers["set-cookie"])

            created = client.post(
                route("/api/v1/projects"),
                json=minimal_hotpot_payload(),
                headers={"X-CSRF-Token": client_csrf, "Idempotency-Key": "factory-prefix-create"},
            )
            self.assertEqual(created.status_code, 201, created.text)
            project_id = created.json()["project_id"]
            project = app.state.store.get_project(project_id)
            project_dir = Path(project["project_dir"])
            brief = json.loads((project_dir / "BRIEF.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["content_type"], "store_visit")
            self.assertEqual(brief["customer_type"], "physical_store")
            for index, payload in enumerate((drama_payload(), oral_payload()), 1):
                branch_created = client.post(
                    route("/api/v1/projects"),
                    json=payload,
                    headers={"X-CSRF-Token": client_csrf, "Idempotency-Key": f"factory-branch-create-{index}"},
                )
                self.assertEqual(branch_created.status_code, 201, branch_created.text)
                branch_project = app.state.store.get_project(branch_created.json()["project_id"])
                branch_brief = json.loads((Path(branch_project["project_dir"]) / "BRIEF.json").read_text(encoding="utf-8"))
                self.assertEqual(branch_brief["content_type"], payload["content_type"])
                self.assertEqual(branch_brief["offers"], [])
            piece_id = project["piece"]["id"]
            cycle_id = project["cycle"]["id"]
            app.state.store.create_confirmation(project_id, "C1", piece_id, target_artifact_ids=["A_STORE_FACTS"])
            app.state.store.create_confirmation(project_id, "C2", piece_id, target_artifact_ids=["A_VIDEO_MASTER"])

            video = project_dir / "delivery" / "master.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"prefix-test-video")
            video_digest = hashlib.sha256(video.read_bytes()).hexdigest()
            app.state.store.add_artifact(
                project_id, "A_VIDEO_MASTER", video, video_digest,
                cycle_id=cycle_id, piece_id=piece_id,
            )
            view = project_dir / "client_views" / "D_CYCLE_MEDIA.html"
            view.parent.mkdir(parents=True, exist_ok=True)
            view.write_text("<p>成片预览</p>", encoding="utf-8")
            app.state.store.add_artifact(
                project_id, "D_CYCLE_MEDIA", view, hashlib.sha256(view.read_bytes()).hexdigest(),
                "D_CYCLE_MEDIA", cycle_id, piece_id,
            )
            bundle = project_dir / "delivery" / f"{project_id}_交付资料包.zip"
            bundle.write_bytes(b"PK\x03\x04prefix-test")
            app.state.store.add_internal_review(
                project_id, "G_DELIVERY_READY", "ALLOWED", "审核员", str(bundle), "ALLOWED",
                piece_id=piece_id,
            )
            billing_row = app.state.store.project_billing(project_id)
            billing.settle(billing_row["billing_task_id"])
            app.state.store.update_project_billing(project_id, "settled", settled_points="750.00")

            pages = [
                route("/access"),
                route("/login"),
                route("/ops/login"),
                route("/projects"),
                route("/projects/new"),
                route(f"/projects/{project_id}"),
                route(f"/projects/{project_id}/confirm/C1"),
                route(f"/projects/{project_id}/delivery"),
                route(f"/projects/{project_id}/review-guide"),
                route("/ops"),
            ]
            for page_url in pages:
                response = client.get(page_url)
                self.assertEqual(response.status_code, 200, f"{page_url}: {response.text}")
                self.assertIn(f"window.APP_BASE={json.dumps(prefix)}", response.text)
                parser = LinkParser()
                parser.feed(response.text)
                self.assertTrue(parser.urls, page_url)
                for attribute, value in parser.urls:
                    if value.startswith(("http://", "https://")):
                        continue
                    expected_start = f"{prefix}/" if prefix else "/"
                    self.assertTrue(value.startswith(expected_start), f"{page_url} {attribute}={value}")
                    target = urlsplit(value).path
                    target_response = client.get(target)
                    self.assertNotEqual(target_response.status_code, 404, f"{page_url} -> {value}")

            detail = client.get(route(f"/api/v1/projects/{project_id}/artifacts/D_CYCLE_MEDIA"))
            self.assertEqual(detail.status_code, 200, detail.text)
            media_url = detail.json()["media_url"]
            self.assertTrue(media_url.startswith(f"{prefix}/api/" if prefix else "/api/"), media_url)
            self.assertEqual(client.get(media_url).status_code, 200)

            delivery = client.get(route(f"/api/v1/projects/{project_id}/delivery"))
            self.assertEqual(delivery.status_code, 200, delivery.text)
            download_url = delivery.json()["items"][0]["download_url"]
            self.assertTrue(download_url.startswith(f"{prefix}/api/" if prefix else "/api/"), download_url)
            downloaded = client.get(download_url)
            self.assertEqual(downloaded.status_code, 200, downloaded.text)
            self.assertTrue(downloaded.content.startswith(b"PK"))

            internal_requests = [
                ("get", route("/internal/v1/reviews/pending"), None),
                ("post", route(f"/internal/v1/projects/{project_id}/gates/G_PROJECT_AUTHORIZED/check"), None),
                ("post", route(f"/internal/v1/projects/{project_id}/gates/G_PROJECT_AUTHORIZED/approve"), {}),
                ("post", route(f"/internal/v1/projects/{project_id}/advance"), None),
            ]
            for method, url, body in internal_requests:
                response = client.request(method, url, json=body, headers={"X-CSRF-Token": ops_csrf})
                self.assertNotEqual(response.status_code, 404, f"内部 API 未命中：{url}")

            logout = client.post(route("/api/v1/auth/logout"), headers={"X-CSRF-Token": client_csrf})
            self.assertEqual(logout.status_code, 200, logout.text)
            logout_headers = logout.headers.get_list("set-cookie")
            expected_cookie_path = f"{prefix}/" if prefix else "/"
            self.assertTrue(any(f"Path={expected_cookie_path}" in value for value in logout_headers), logout_headers)
            if prefix:
                self.assertTrue(any("Path=/;" in value for value in logout_headers), logout_headers)

            script = f"""
const fs = require('fs');
global.window = {{APP_BASE: {json.dumps(prefix)}}};
global.document = {{querySelector: () => null, querySelectorAll: () => [], hidden: false}};
global.location = {{pathname: {json.dumps(route('/projects/new'))}, href: '', reload: () => {{}}}};
global.crypto = {{randomUUID: () => '00000000-0000-4000-8000-000000000000'}};
global.fetch = async (url) => ({{status: 200, ok: true, headers: {{get: () => null}}, json: async () => ({{url}}), text: async () => ''}});
const source = fs.readFileSync({json.dumps(str(APP_ROOT / 'web/static/app_v3.js'))}, 'utf8');
const exported = new Function(source + '\\nreturn {{p, api}};')();
(async () => {{
  const paths = [
    '/api/v1/billing/access',
    '/internal/v1/projects/x/gates/G/check',
    '/internal/v1/reviews/pending',
    '/internal/v1/projects/x/gates/G/approve',
    '/internal/v1/projects/x/advance',
    '/api/v1/projects/x/delivery/token',
    '/api/v1/projects/x/media/token',
    '/projects/x',
    '/static/style.css'
  ];
  const mapped = paths.map(exported.p);
  const apiResult = await exported.api('/internal/v1/reviews/pending');
  process.stdout.write(JSON.stringify({{mapped, apiUrl: apiResult.url, idempotent: exported.p(mapped[0])}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
            js_result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
            mapped = json.loads(js_result.stdout)
            expected_paths = [
                route("/api/v1/billing/access"),
                route("/internal/v1/projects/x/gates/G/check"),
                route("/internal/v1/reviews/pending"),
                route("/internal/v1/projects/x/gates/G/approve"),
                route("/internal/v1/projects/x/advance"),
                route("/api/v1/projects/x/delivery/token"),
                route("/api/v1/projects/x/media/token"),
                route("/projects/x"),
                route("/static/style.css"),
            ]
            self.assertEqual(mapped["mapped"], expected_paths)
            self.assertEqual(mapped["apiUrl"], route("/internal/v1/reviews/pending"))
            self.assertEqual(mapped["idempotent"], route("/api/v1/billing/access"))

    def test_factory_prefix_mode(self) -> None:
        self._run_mode("/factory")

    def test_local_mode(self) -> None:
        self._run_mode("")

    def test_invalid_root_path_is_rejected(self) -> None:
        with configured_root_path("factory"):
            with self.assertRaisesRegex(ValueError, "必须为空或以 / 开头"):
                create_app(start_worker=False)

    def test_only_one_javascript_entrypoint_remains(self) -> None:
        static_scripts = sorted(path.name for path in (APP_ROOT / "web/static").glob("app*.js"))
        self.assertEqual(static_scripts, ["app_v3.js"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
