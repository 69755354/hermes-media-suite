"""Xingtu card handling without writing data-winport-* attributes, in Chromium.

Before 1.2.189 the scripts tagged platform DOM nodes (data-winport-task-card,
-task-row, -pick-card, -video-baseline) to find them again on the next call.
That leaves a product-named trace in the platform's page.  The scripts now
re-enumerate on every call; a card is re-identified by the text lines it was
listed with, so a re-render between "list" and "click" can never redirect a
click to another card -- it fails closed instead.

These are synthetic pages built to the selectors the scripts rely on.  They
prove the logic; a real-page DOM regression on the creator site is still
required before release.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT / "agent"))

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

from winport import xingtu_tasks as xt  # noqa: E402

NO_TAGS = "() => [...document.querySelectorAll('*')].some(el => [...el.attributes].some(a => a.name.startsWith('data-winport')))"


def _card(order, title, quota):
    act = lambda label: "window.__clicked=%s;return false" % json.dumps([order, label]).replace('"', "'")
    return ('<div class="task-card" data-order-id="%s">'
            '<div><span class="indicator-label">剩余额度</span><span>%s</span></div>'
            '<div><span class="indicator-label">任务类型</span><span>APP种草</span></div>'
            '<div class="title">任务：%s</div>'
            '<a href="#" onclick="%s">去投稿</a>'
            '<button onclick="%s">查看详情</button></div>') % (order, quota, title, act("去投稿"), act("查看详情"))


def _page(*cards):
    return '<html><body><div id="list">%s</div></body></html>' % "".join(cards)


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class XingtuNoDomTagsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as exc:  # pragma: no cover
            cls.pw.stop()
            raise unittest.SkipTest("chromium unavailable: %s" % exc)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)

    def _load(self, html):
        self.page.set_content(html)
        self.page.evaluate("() => { window.__clicked = null; }")

    def _list(self):
        cards = self.page.evaluate(xt._js_task_cards())
        return cards, [xt.parse_card(c) for c in cards]

    def _click_text(self, task, text):
        ok = self.page.evaluate(xt._JS_CLICK_CARD_TEXT,
                                {"index": task["index"], "text": text,
                                 "lines": task["card_lines"]})
        return ok, self.page.evaluate("() => window.__clicked")

    def test_listing_writes_nothing_into_the_page(self):
        self._load(_page(_card("O1", "爆款A", 10), _card("O2", "爆款B", 5)))
        cards, tasks = self._list()
        self.assertEqual(len(cards), 2)
        self.assertFalse(self.page.evaluate(NO_TAGS))
        self.assertTrue(all(t["card_lines"] for t in tasks))

    def test_click_by_listed_identity(self):
        self._load(_page(_card("O1", "爆款A", 10), _card("O2", "爆款B", 5)))
        _, tasks = self._list()
        ok, clicked = self._click_text(tasks[1], "去投稿")
        self.assertTrue(ok)
        self.assertEqual(clicked, ["O2", "去投稿"])
        self.assertFalse(self.page.evaluate(NO_TAGS))

    def test_rerender_shifting_indexes_still_hits_the_chosen_card(self):
        self._load(_page(_card("O1", "爆款A", 10), _card("O2", "爆款B", 5)))
        _, tasks = self._list()
        chosen = tasks[0]                       # O1 at index 0
        self.page.evaluate("h => document.getElementById('list').insertAdjacentHTML('afterbegin', h)",
                           _card("O9", "新任务", 3))   # O1 moves to index 1
        ok, clicked = self._click_text(chosen, "去投稿")
        self.assertTrue(ok)
        self.assertEqual(clicked, ["O1", "去投稿"])

    def test_chosen_card_gone_fails_closed(self):
        self._load(_page(_card("O1", "爆款A", 10), _card("O2", "爆款B", 5)))
        _, tasks = self._list()
        self.page.evaluate("() => document.querySelector('[data-order-id=O1]').remove()")
        ok, clicked = self._click_text(tasks[0], "去投稿")
        self.assertFalse(ok)
        self.assertIsNone(clicked)

    def test_identical_cards_use_the_listed_index(self):
        self._load(_page(_card("O1", "同名", 1), _card("O1", "同名", 1)))
        _, tasks = self._list()
        ok, _ = self._click_text(tasks[1], "去投稿")
        self.assertTrue(ok)

    def test_detail_by_order_needs_no_prior_listing(self):
        self._load(_page(_card("O1", "爆款A", 10), _card("O2", "爆款B", 5)))
        self.assertTrue(self.page.evaluate(xt._JS_CLICK_DETAIL_BY_ORDER, "O2"))
        self.assertEqual(self.page.evaluate("() => window.__clicked"), ["O2", "查看详情"])
        self.assertFalse(self.page.evaluate(NO_TAGS))

    def test_detail_by_order_ambiguous_fails_closed(self):
        self._load(_page(_card("O1", "爆款A", 10), _card("O1", "爆款B", 5)))
        self.assertFalse(self.page.evaluate(xt._JS_CLICK_DETAIL_BY_ORDER, "O1"))

    def test_detail_by_task_name_live(self):
        self._load(_page(_card("O1", "爆款A", 10), _card("O2", "爆款B", 5)))
        names = self.page.evaluate("() => {" + xt.XINGTU_VISIBLE_CARD_NAME_JS + xt._JS_TASK_CARD_ROOTS +
                                   " return __xingtuTaskCardRoots().map(__xingtuCardName); }")
        self.assertEqual(len(set(names)), 2, names)
        self.assertTrue(self.page.evaluate(xt._JS_CLICK_DETAIL_BY_TASK, names[1]))
        self.assertEqual(self.page.evaluate("() => window.__clicked"), ["O2", "查看详情"])

    def test_rows_and_picker_write_nothing(self):
        self._load('<html><body><table><tbody class="el-table__body-wrapper">'
                   '<tr class="el-table__row"><td class="task-title">任务一</td><td>视频已上传</td></tr>'
                   '</tbody></table>'
                   '<div class="semi-portal"><div>选择星图任务</div>'
                   '<div class="card-container-x1"><span class="task-name">任务：剧集剪辑</span></div>'
                   '<div class="card-container-x2"><span class="task-name">任务：APP种草</span></div>'
                   '</div></body></html>')
        rows = self.page.evaluate(xt._js_list_rows())
        picks = self.page.evaluate(xt._JS_PICKER_CARDS)
        self.assertEqual(len(rows), 1)
        self.assertEqual([p["name"] for p in picks], ["任务：剧集剪辑", "任务：APP种草"])
        self.assertFalse(self.page.evaluate(NO_TAGS))

    def test_video_baseline_writes_nothing(self):
        from winport import publish_exec
        self._load('<html><body><video src="https://v.test/a.mp4" width="200" height="120"></video></body></html>')
        base = publish_exec._video_preview_baseline(self.page)
        self.assertEqual(base["count"], 1)
        self.assertFalse(self.page.evaluate(NO_TAGS))


if __name__ == "__main__":
    unittest.main()
