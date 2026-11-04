"""Pre-submit hold rules for the publish driver.

A fill-stage failure happens before the publish button is pressed, so its
ledger reservation is recycled and the channel normally stays open.  Account
level stops are the exception: captcha, SMS verification, risk control and a
lost login must still freeze the channel, otherwise every queued task walks
into the same wall.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

CLIENT = Path(__file__).resolve().parents[1] / "client"
sys.path.insert(0, str(CLIENT / "agent"))

from winport.publish_exec import PlaywrightDriver  # noqa: E402
from winport.publish_guard import (CAPTCHA, LOGIN_LOST,  # noqa: E402
                                   PublishHoldStore,
                                   RISK_CONTROL, SMS_VERIFICATION)


class PreSubmitHoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = PublishHoldStore(Path(self.tmp.name) / "publish_holds.json")
        # Bind the real methods without running __init__ (no Chromium/CDP).
        self.driver = object.__new__(PlaywrightDriver)
        self.driver._pre_submit = True
        self.driver.channel = SimpleNamespace(channel_id="ch-1")
        self.driver._hold_store = self.store

    def hold(self):
        return self.store.get("ch-1")

    def test_login_page_during_fill_freezes_channel(self):
        self.driver._apply_hold(
            "创作者中心跳转到了登录页。首次安装须由账号本人完成一次登录",
            "fill", {})
        self.assertIsNotNone(self.hold())
        self.assertEqual(self.hold()["kind"], LOGIN_LOST)

    def test_sms_verification_during_fill_freezes_channel(self):
        self.driver._apply_hold(
            "发布触发短信二次验证，但没有可用的验证码文件路径",
            "fill", {})
        self.assertEqual(self.hold()["kind"], SMS_VERIFICATION)

    def test_risk_control_during_fill_freezes_channel(self):
        self.driver._apply_hold(
            "操作频繁，请稍后再试", "fill", {})
        self.assertEqual(self.hold()["kind"], RISK_CONTROL)

    def test_captcha_during_fill_freezes_channel(self):
        self.driver._apply_hold(
            "页面出现安全验证，需要拖动滑块", "fill", {})
        self.assertEqual(self.hold()["kind"], CAPTCHA)

    def test_ordinary_fill_failure_does_not_freeze_channel(self):
        self.driver._apply_hold("标题回读不一致", "fill", {})
        self.assertIsNone(self.hold())

    def test_post_submit_failure_still_freezes_channel(self):
        self.driver._pre_submit = False
        self.driver._apply_hold("标题回读不一致", "publish", {})
        self.assertEqual(self.hold()["kind"], "publish_unknown")

    def test_explicit_account_kind_wins_over_reason_text(self):
        self.driver._apply_hold("页面关闭", "fill", {}, kind=LOGIN_LOST)
        self.assertEqual(self.hold()["kind"], LOGIN_LOST)


if __name__ == "__main__":
    unittest.main()
