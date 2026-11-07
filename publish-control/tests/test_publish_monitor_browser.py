"""The read-only publish-failure monitor, in a real Chromium.

It must (1) report a verification-failure text that appears after install,
(2) keep reporting after a navigation (it is an init script), (3) go quiet
once the receipt closes, and (4) leave no string-named globals on window that
name the product or reveal a monitor -- page scripts can enumerate those.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT / "agent"))

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

from winport import platform_receipt  # noqa: E402

FAILURE = "验证失败，请重试"
PAGE = "<html><body><div id=app>发布页</div></body></html>"


class _Receipt:
    """The slice of PlatformReceipt that install_monitor/close touch."""

    def __init__(self, page, cdp):
        self.page, self.cdp, self.active, self.handlers = page, cdp, True, []
        self.page_failures = []

    observe_page_failure = platform_receipt.PublishReceipt.observe_page_failure
    close = platform_receipt.PublishReceipt.close


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class PublishMonitorBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as exc:  # pragma: no cover - no browser on this host
            cls.pw.stop()
            raise unittest.SkipTest("chromium unavailable: %s" % exc)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        # Serve pages over http like the real creator site (data: URLs get no bindings).
        self.page.route("http://creator.test/**", lambda route: route.fulfill(
            status=200, content_type="text/html; charset=utf-8", body=PAGE))
        self.page.goto("http://creator.test/post")
        cdp = self.page.context.new_cdp_session(self.page)
        cdp.send("Page.enable")  # as PublishReceipt does; init scripts need it
        self.baseline_keys = set(self.page.evaluate("Object.keys(window)"))
        self.receipt = _Receipt(self.page, cdp)
        platform_receipt.install_monitor(self.page, self.receipt, [FAILURE])
        self.addCleanup(self.page.close)

    def _show(self, text):
        self.page.evaluate("t => { const d=document.createElement('div'); d.textContent=t;"
                           " document.body.appendChild(d); }", text)
        self.page.wait_for_timeout(400)

    def test_reports_failure_text(self):
        self._show(FAILURE)
        self.assertTrue(any(FAILURE in f for f in self.receipt.page_failures), self.receipt.page_failures)

    def test_survives_navigation(self):
        self.page.goto("http://creator.test/next")
        self._show(FAILURE)
        self.assertTrue(any(FAILURE in f for f in self.receipt.page_failures), self.receipt.page_failures)

    def test_quiet_after_close(self):
        self.receipt.close()
        self.receipt.active = True  # prove the page side stopped, not just the flag
        self._show(FAILURE)
        self.assertEqual(self.receipt.page_failures, [])

    def test_no_revealing_string_globals(self):
        added = set(self.page.evaluate("Object.keys(window)")) - self.baseline_keys
        revealing = sorted(k for k in added
                           if any(w in k.lower() for w in ("monitor", "publish", "winport", "stop", "installed")))
        self.assertEqual(revealing, [])


if __name__ == "__main__":
    unittest.main()
