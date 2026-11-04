#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端回归：状态机、门禁、预算、卡点、改派、租约、人工闸、验收闸。"""
import os, subprocess, tempfile, unittest, pathlib, sys, time, sqlite3

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTL = str(ROOT / "teamctl")

class T(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(self.db)
        # 1.2.177: briefs/handoffs/approvals must land in a throwaway tree.  The
        # old suite rewrote tracked files under the repository on every run.
        self.data = tempfile.mkdtemp(prefix="team-data-")
        self.env = dict(os.environ, TEAM_DB=self.db, TEAM_DATA=self.data,
                        PYTHONIOENCODING="utf-8")

    def tearDown(self):
        for suf in ("", "-wal", "-shm"):
            p = self.db + suf
            if os.path.exists(p): os.remove(p)
        import shutil; shutil.rmtree(self.data, ignore_errors=True)

    def ctl(self, *args, ok=True):
        # Windows cannot execute the extensionless script directly; run it with
        # the same interpreter and decode explicitly instead of relying on the
        # console code page (中文 Windows 默认 GBK 会直接抛 UnicodeDecodeError).
        r = subprocess.run([sys.executable, CTL, *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           env=self.env, cwd=str(ROOT))
        if ok and r.returncode != 0:
            raise AssertionError(f"{args} rc={r.returncode}\n{r.stdout}\n{r.stderr}")
        return r

    def brief(self, sid):
        self.ctl("brief", "V001", "--stage", sid)

    def test_full_chain(self):
        self.ctl("add", "测试片", "--budget", "6")
        for sid in ["TOPIC", "COPY", "STORYBOARD"]:
            self.ctl("dispatch", "V001", "--stage", sid, "--executor", "stub")
        # 付费阶段未登记调用：开不了工
        r = self.ctl("dispatch", "V001", "--stage", "MEDIA", "--executor", "stub", ok=False)
        self.assertIn("付费阶段", r.stdout)
        self.ctl("calls", "V001", "--stage", "MEDIA", "--n", "3")
        self.ctl("dispatch", "V001", "--stage", "MEDIA", "--executor", "stub")
        self.ctl("calls", "V001", "--stage", "COMPOSE", "--n", "1")
        self.ctl("dispatch", "V001", "--stage", "COMPOSE", "--executor", "stub")
        # 审核：没有 VERDICT: PASS 不许过
        r = self.ctl("dispatch", "V001", "--stage", "COMPLIANCE", "--executor", "stub", ok=False)
        self.assertIn("VERDICT", r.stdout)
        self.ctl("unblock", "V001", "--stage", "COMPLIANCE")
        self.ctl("dispatch", "V001", "--stage", "COMPLIANCE", "--executor", "stub_ok")
        # 发布：没人工放行不许开
        r = self.ctl("dispatch", "V001", "--stage", "PUBLISH", "--executor", "stub_ok", ok=False)
        self.assertIn("未放行", r.stdout)
        self.ctl("approve", "V001", "PUBLISH", "--note", "测试放行")
        # 发布：没有回读确认不算发出去
        r = self.ctl("dispatch", "V001", "--stage", "PUBLISH", "--executor", "stub", ok=False)
        self.assertIn("CONFIRMED", r.stdout)
        self.ctl("unblock", "V001", "--stage", "PUBLISH")
        self.ctl("dispatch", "V001", "--stage", "PUBLISH", "--executor", "stub_ok")
        # 取数：必须是表格
        r = self.ctl("dispatch", "V001", "--stage", "COLLECT", "--executor", "stub", ok=False)
        self.assertIn("表格", r.stdout)
        self.ctl("unblock", "V001", "--stage", "COLLECT")
        self.ctl("dispatch", "V001", "--stage", "COLLECT", "--executor", "stub_ok")
        self.ctl("dispatch", "V001", "--stage", "REVIEW", "--executor", "stub")
        st = self.ctl("status", "V001").stdout
        self.assertIn("closed", st)
        # 超预算
        r = self.ctl("calls", "V001", "--stage", "MEDIA", "--n", "99", ok=False)
        self.assertIn("超出预算上限", r.stdout)

    def test_brief_gate(self):
        self.ctl("add", "任务书闸")
        r = self.ctl("start", "V001", "--stage", "TOPIC", ok=False)
        self.assertIn("任务书", r.stdout)
        self.brief("TOPIC")
        self.ctl("start", "V001", "--stage", "TOPIC")

    def test_review_independence(self):
        self.ctl("add", "审核独立")
        self.brief("TOPIC")
        r = self.ctl("assign", "V001", "--stage", "COMPLIANCE", "--to", "production", "--reason", "试", ok=False)
        # 合规阶段的 owner 是 review，改派给 production 后开不了工
        self.assertEqual(r.returncode, 0)
        self.brief("COMPLIANCE")
        r = self.ctl("start", "V001", "--stage", "COMPLIANCE", ok=False)
        self.assertIn("上游未完成", r.stdout)

    def test_reject_assign_block(self):
        self.ctl("add", "退单测试")
        self.ctl("reject", "V001", "--stage", "TOPIC", "--reason", "方向不对")
        self.brief("TOPIC")
        r = self.ctl("start", "V001", "--stage", "TOPIC", ok=False)
        self.assertIn("团长不参与生产", r.stdout + r.stderr)
        self.ctl("assign", "V001", "--stage", "TOPIC", "--to", "production", "--reason", "重派")
        self.ctl("start", "V001", "--stage", "TOPIC")
        self.ctl("block", "V001", "--stage", "TOPIC", "--reason", "素材缺失")
        r = self.ctl("start", "V001", "--stage", "TOPIC", ok=False)
        self.assertIn("卡点", r.stdout + r.stderr)
        self.ctl("unblock", "V001", "--stage", "TOPIC")
        self.ctl("start", "V001", "--stage", "TOPIC")

    def test_lease_expiry(self):
        self.ctl("add", "租约测试")
        self.brief("TOPIC")
        code = ("import sys; sys.path.insert(0, %r); from teamd import engine; "
                "engine.start('V001','TOPIC',lease_seconds=-1); print(engine.expire_leases())") % str(ROOT)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           env=self.env, cwd=str(ROOT))
        self.assertIn("('V001', 'TOPIC')", r.stdout, r.stdout + r.stderr)
        st = self.ctl("status", "V001").stdout
        self.assertIn("心跳超时", st)

if __name__ == "__main__":
    unittest.main(verbosity=2)
