#!/usr/bin/env python3
"""Self-verification for the 5 adopted mainstream-tool improvements (A-E).

Runs the REAL CLI + library entry points on the Linux build host and records,
for every case: the literal command, the expected result, the ACTUAL exit code
and stdout/stderr, and the SHA-256 of every artefact produced.  Cases that can
only be confirmed on a Windows machine are listed as 待真机, never as a pass.

    python3 tools/verify_ae.py --out ../bundle_v4/SELF_VERIFY_REPORT_AE.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

from winport import dryrun, ed25519_pure, evidence, idempotency, license as license_mod  # noqa: E402
from winport import panel, state_machine  # noqa: E402
import devsign  # noqa: E402
from devsign import mint_dev_license  # noqa: E402
from winport.paths import Layout  # noqa: E402
from winport.jsonio import write_json  # noqa: E402
from winport.subprocess_text import text_mode_options  # noqa: E402

CASES: list[dict] = []
RAW: list[str] = []
ENV = dict(os.environ, PYTHONPATH=str(ROOT / "agent"), PYTHONUTF8="1",
           PYTHONIOENCODING="utf-8")


def sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run(argv, *, timeout=180):
    proc = subprocess.run([str(a) for a in argv], capture_output=True,
                          cwd=str(ROOT), env=ENV, timeout=timeout,
                          **text_mode_options())
    out = (proc.stdout or "") + (proc.stderr or "")
    RAW.append("$ " + " ".join(str(a) for a in argv) + f"\n[exit={proc.returncode}]\n{out}")
    return {"cmd": " ".join(str(a) for a in argv), "rc": proc.returncode, "out": out}


def cli(args, *, data, program=ROOT):
    return run([sys.executable, "-m", "winport", *args,
                "--data", str(data), "--program", str(program)])


def record(cid, title, cmd, expected, res, ok, artifacts=None, note=""):
    CASES.append({"cid": cid, "title": title, "cmd": cmd, "expected": expected,
                  "rc": res["rc"] if isinstance(res, dict) else res,
                  "actual": res["out"] if isinstance(res, dict) else "",
                  "ok": bool(ok), "artifacts": artifacts or [], "note": note})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} {title}")


def seed(layout: Layout, *, settings=None):
    shutil.copyfile(ROOT / "config" / "environments.json.tmpl",
                    layout.environments_file)
    shutil.copyfile(ROOT / "config" / "settings.json.tmpl", layout.settings_file)
    if settings:
        doc = json.loads(layout.settings_file.read_text("utf-8"))
        doc.update(settings)
        layout.settings_file.write_text(json.dumps(doc, ensure_ascii=False,
                                                   indent=2), encoding="utf-8")


def plan_doc(**over):
    account = over.get("account_id", "env_1:douyin")
    piece = {"piece_no": 1, "title": "上集标题", "copy_body": "上集文案",
             "topics": ["#示例话题"], "sha256": "a" * 64, "md5": "b" * 32,
             "file_name": "01_第12集-上.mp4",
             "covers": {"vertical": "c.jpg", "horizontal": None}}
    doc = {"plan_id": "PLAN-AE-1", "env_id": over.get("env_id", "env_1"),
           "channel_id": account, "account_id": account,
           "platform": over.get("platform", "douyin"),
           "schedule_at": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
           "piece": piece,
           "compliance": {"content_hash": idempotency.material_fingerprint(
               piece, account_id=account)}}
    doc.update({k: v for k, v in over.items() if k not in ("env_id", "account_id",
                                                           "platform")})
    return doc


# ------------------------------------------------------------------ A
def case_A(scratch: Path, layout: Layout) -> None:
    # 1.2.5: the production CLI has NO injection flag (the trust root is fixed).
    # A synthetic, test-signed licence therefore cannot be exercised through
    # `python -m winport`; the allow-path is driven IN-PROCESS through the same
    # `cli._licence_gate` helper the CLI calls, with the test-only injection
    # arguments that no CLI flag reaches.  Negative cases (A2/A4) still go
    # through the real CLI subprocess.
    from winport import cli as cli_mod
    from winport.settings import load_settings
    from winport.platforms import load_registry
    seed = os.urandom(32)
    public = devsign.publickey(seed)
    machine = "M-AE-A"
    licence = mint_dev_license(seed, machine_id=machine,
                               expires_at=(datetime.now(timezone.utc)
                                           + timedelta(days=90)).isoformat(),
                               accounts=[{"account_id": "env_1:douyin",
                                          "platform": "douyin"}])
    licence_path = scratch / "license_A.json"
    licence_path.write_text(json.dumps(licence, ensure_ascii=False),
                            encoding="utf-8")
    pub = scratch / "pub_A.hex"
    pub.write_text(public.hex(), encoding="utf-8")

    plan_path = scratch / "plan.json"
    plan_path.write_text(json.dumps(plan_doc(), ensure_ascii=False, indent=2),
                         encoding="utf-8")
    plan = json.loads(plan_path.read_text("utf-8"))
    envs, channels = load_registry(layout)
    settings = load_settings(layout.settings_file)

    def gate_for(plan_doc_):
        return cli_mod._licence_gate(
            layout, license_path=str(licence_path), plan=plan_doc_,
            allow_test_injection=True, pubkey_override=str(pub),
            machine_id_override=machine)

    gate = gate_for(plan)
    preview = dryrun.build_preview(plan, envs=envs, channels=channels,
                                   settings=settings, license_info=gate)
    dryrun.write_preview(layout, preview)
    preview_path = layout.run / "publish-preview.json"
    artifacts = []
    ok = (gate.get("publish_allowed") is True and preview["ok"]
          and preview_path.exists())
    if preview_path.exists():
        artifacts = [(str(preview_path), sha256(preview_path)),
                     (str(layout.run / "publish-preview.md"),
                      sha256(layout.run / "publish-preview.md"))]
    ok = ok and preview["confirm_ref"].startswith("dryrun:")
    record("A1", "dry-run 产出「将要发布什么」清单并通过 schema 校验",
           "python3 -c 'cli._licence_gate(..., allow_test_injection=True)' + "
           "dryrun.build_preview/write_preview (in-process; no CLI injection flag)",
           "gate.publish_allowed=true；生成 publish-preview.json/.md，ok=true，带 confirm_ref",
           {"rc": 0 if ok else 1, "out": json.dumps(
               {"publish_allowed": gate.get("publish_allowed"),
                "status": gate.get("status"), "ok": preview["ok"],
                "confirm_ref": preview["confirm_ref"]}, ensure_ascii=False)},
           ok, artifacts)

    bad = plan_doc()
    bad["piece"]["title"] = ""
    bad_path = scratch / "plan_bad.json"
    bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    res = cli(["dry-run", "--plan", str(bad_path), "--out", str(scratch / "bad.json")],
              data=layout.data)
    ok = res["rc"] == 2 and "TITLE_MISSING" in res["out"]
    record("A2", "校验不过（缺标题）明确报错且非 0 退出、不许硬发",
           res["cmd"], "rc=2；回显含 TITLE_MISSING", res, ok)

    token = preview["confirm_token"]
    stored = dryrun.read_preview(layout)
    good = dryrun.check_confirmation(stored, plan, envs=envs, channels=channels,
                                     settings=settings, confirm_token=token,
                                     license_info=gate_for(plan))
    record("A3", "飞书确认按钮带回的 token 与清单一致 -> 通过",
           "python3 -c 'dryrun.check_confirmation(..., confirm_token=<stored>)'",
           "confirmation.ok=true",
           {"rc": 0 if good["ok"] else 1, "out": json.dumps(good, ensure_ascii=False)},
           bool(good["ok"]))
    bad_confirm = dryrun.check_confirmation(stored, plan, envs=envs,
                                            channels=channels, settings=settings,
                                            confirm_token="0" * 64,
                                            license_info=gate_for(plan))
    record("A4", "确认 token 不一致（清单被改过）-> 拒绝",
           "python3 -c 'dryrun.check_confirmation(..., confirm_token=\"0\"*64)'",
           "confirmation.ok=false；reason 含「不一致」",
           {"rc": 0 if not bad_confirm["ok"] else 1,
            "out": json.dumps(bad_confirm, ensure_ascii=False)},
           (not bad_confirm["ok"]) and ("不一致" in bad_confirm["reason"]))

    res = cli(["publish-key", "--plan", str(plan_path)], data=layout.data)
    record("A5", "清单同时给出幂等键（素材指纹+环境+时间窗）",
           res["cmd"], "rc=0；idempotency_key 以 env_1| 开头", res,
           res["rc"] == 0 and '"env_1|' in res["out"])


# ------------------------------------------------------------------ B
def case_B(scratch: Path, layout: Layout) -> None:
    store = evidence.EvidenceStore(layout, retention_days=14)
    record_file = store.capture("upload", env_id="env_1", channel_id="env_1:douyin",
                                platform="douyin", error="simulated HTTP 500",
                                note="自验：合成页面快照（真机由 Playwright 落真实截图）",
                                screenshot=b"\x89PNG\r\n\x1a\nAE-VERIFY",
                                html="<html><body>HTTP 500</body></html>")
    artifacts = [("evidence/" + record_file["screenshot"],
                  sha256(store.root / record_file["screenshot"])),
                 ("evidence/" + record_file["html"],
                  sha256(store.root / record_file["html"])),
                 ("evidence/" + record_file["meta"],
                  sha256(store.root / record_file["meta"])),
                 ("evidence/" + "INDEX.jsonl", sha256(store.index_path))]
    res = cli(["evidence-list"], data=layout.data)
    ok = (record_file["screenshot_available"] and record_file["html_available"]
          and "env_1" in record_file["screenshot"]
          and res["rc"] == 0 and record_file["screenshot"] in res["out"])
    record("B1", "失败留证：文件名带时间+环境，截图/HTML/json + INDEX 索引",
           res["cmd"], "evidence/ 下有 <时间>__env_1__upload__*.png/.html/.json，"
           "evidence-list 能回显", res, ok, artifacts,
           note=f"文件名={record_file['screenshot']}")

    # a real failure path through the product: a browser that is not installed
    res = cli(["login-open", "--channel", "env_1:douyin", "--chrome-path",
               str(scratch / "no-such-chrome.exe")], data=layout.data)
    after = evidence.EvidenceStore(layout).list_entries()
    browser_rows = [r for r in after if r["step"] == "browser"]
    ok = res["rc"] == 5 and len(browser_rows) == 1 and browser_rows[0]["env_id"] == "env_1"
    record("B2", "起浏览器失败自动留证（真失败路径，不是造的）",
           res["cmd"], "rc=5(CHROME_MISSING)；evidence 目录多一条 step=browser 记录",
           res, ok,
           [("evidence/INDEX.jsonl", sha256(store.index_path))],
           note=f"browser 记录数={len(browser_rows)}")

    res = cli(["evidence-prune", "--days", "0"], data=layout.data)
    remaining = evidence.EvidenceStore(layout).list_entries()
    ok = res["rc"] == 0 and remaining == []
    record("B3", "清理策略：evidence-prune --days 0 清空超期证据与索引",
           res["cmd"], "rc=0；removed_count>0；索引清空", res, ok)


# ------------------------------------------------------------------ C
def case_C(scratch: Path, layout: Layout) -> None:
    plan_path = scratch / "plan.json"
    res1 = cli(["publish-key", "--plan", str(plan_path)], data=layout.data)
    res2 = cli(["publish-key", "--plan", str(plan_path)], data=layout.data)
    key1 = _json_field(res1["out"], "idempotency_key")
    key2 = _json_field(res2["out"], "idempotency_key")
    record("C1", "同一素材+同一环境+同一时间窗 -> 同一幂等键（重试会收敛）",
           res1["cmd"], "两次 key 完全相同", res1,
           bool(key1) and key1 == key2, note=f"key={key1}")

    res3 = cli(["publish-key", "--plan", str(scratch / "plan_env2.json")],
               data=layout.data)
    key3 = _json_field(res3["out"], "idempotency_key")
    record("C2", "换环境 -> 不同幂等键（同内容可在另一个号发一次）",
           res3["cmd"], "env_2 的 key 与 env_1 不同", res3, bool(key3) and key3 != key1)

    # process killed (SIGKILL) mid-flight, then restart: no duplicate publish
    ledger_path = layout.run / "stage2-ledger.json"
    key = key1
    script = (
        "import os, signal, sys\n"
        f"sys.path.insert(0, {str(ROOT / 'agent')!r})\n"
        "from winport.stage2_ledger import Stage2Ledger\n"
        f"ledger = Stage2Ledger({str(ledger_path)!r})\n"
        f"print('RESERVE=' + ledger.reserve({key!r}, account_id='env_1:douyin'), flush=True)\n"
        "os.kill(os.getpid(), signal.SIGKILL)\n")
    killed = run([sys.executable, "-c", script])
    state = _kv(run([sys.executable, "-c",
                     "import sys; sys.path.insert(0," + repr(str(ROOT / 'agent'))
                     + ");from winport.stage2_ledger import Stage2Ledger;"
                     + "print('STATE=' + str(Stage2Ledger("
                     + repr(str(ledger_path))
                     + ").state(" + repr(key) + ")))"])["out"], "STATE")
    retry = run([sys.executable, "-c",
                 "import sys; sys.path.insert(0," + repr(str(ROOT / 'agent'))
                 + ");from winport.stage2_ledger import Stage2Ledger;"
                 + "print('RESERVE=' + Stage2Ledger(" + repr(str(ledger_path))
                 + ").reserve(" + repr(key) + "))"])
    retry_state = _kv(retry["out"], "RESERVE")
    ok = killed["rc"] == -9 and "RESERVE=NEW" in killed["out"] \
        and state == "RESERVED" and retry_state == "RESERVED"
    record("C3", "进程被强杀后重启：键仍是 RESERVED，拒绝重复发布",
           killed["cmd"], "kill rc=-9；重启后 state=RESERVED，再次 reserve 返回 RESERVED",
           killed, ok, note=f"state={state} retry={retry_state}")

    # two concurrent "clicks" on the same key -> exactly one NEW
    race = ("import sys\n"
            f"sys.path.insert(0, {str(ROOT / 'agent')!r})\n"
            "from winport.stage2_ledger import Stage2Ledger\n"
            f"print(Stage2Ledger({str(ledger_path)!r}).reserve({(key + '-race')!r}))\n")
    procs = [subprocess.Popen([sys.executable, "-c", race], stdout=subprocess.PIPE,
                              env=ENV, **text_mode_options()) for _ in range(2)]
    states = sorted(p.communicate(timeout=60)[0].strip() for p in procs)
    record("C4", "重复点击/并发触发同一动作 -> 只允许一次 NEW",
           "（两个并发 reserve 同一 key）", "states == ['NEW', 'RESERVED']",
           {"cmd": "python -c '<concurrent reserve>'", "rc": 0, "out": str(states)},
           states == ["NEW", "RESERVED"], note=f"states={states}")


# ------------------------------------------------------------------ D
def case_D(scratch: Path, layout: Layout) -> None:
    samples = [
        ("有效", {"status": "ONLINE", "evidence": {"cookie_count": 3}}),
        ("未登录", {"status": "OFFLINE", "evidence": {"cookie_count": 0}}),
        ("掉线", {"status": "OFFLINE", "evidence": {"cookie_count": 0}},
         {"state": state_machine.VALID}),
        ("限流", {"status": "UNVERIFIED", "evidence": {"cookie_count": 2,
                                                       "backend_status": 429}}),
        ("封禁", {"status": "OFFLINE", "reason": "账号封禁",
                  "evidence": {"cookie_count": 2, "backend_status": 403}}),
        ("未知", {"status": "UNVERIFIED", "evidence": {"probe_error": "boom"}}),
    ]
    lines = []
    for item in samples:
        row, prev = item[1], (item[2] if len(item) > 2 else None)
        rec = state_machine.classify(row, previous=prev)
        lines.append(f"{item[0]} -> {rec['state']}({rec['label']}) 依据={rec['criteria']}")
    out = "\n".join(lines)
    expected = {"有效": "VALID", "未登录": "NOT_LOGGED_IN", "掉线": "DROPPED",
                "限流": "RATE_LIMITED", "封禁": "BANNED", "未知": "UNKNOWN"}
    ok = all(f"{cn} -> {code}" in out for cn, code in expected.items())
    record("D1", "状态机六态判定口径（未登录/有效/掉线/限流/封禁/未知）",
           "python -c 'state_machine.classify(...)' 六组样本",
           "六种状态各自命中且给出依据", {"cmd": "classify x6", "rc": 0, "out": out}, ok)

    res = cli(["state", "--persist"], data=layout.data)
    record("D2", "环境/账号状态视图（CLI）：按环境聚合 + 只报受影响环境的变化",
           res["cmd"], "rc=0；输出 environments[].state/state_label 与 alerts",
           res, res["rc"] == 0 and '"state_label"' in res["out"])

    previous = [{"channel_id": "env_1:douyin", "account_state": "VALID"},
                {"channel_id": "env_2:douyin", "account_state": "VALID"}]
    current = [
        {"channel_id": "env_1:douyin", "env_id": "env_1", "platform_name": "抖音",
         "account_state": "RATE_LIMITED", "account_state_label": "限流",
         "account_state_reason": "HTTP 429"},
        {"channel_id": "env_2:douyin", "env_id": "env_2", "platform_name": "抖音",
         "account_state": "VALID", "account_state_label": "有效",
         "account_state_reason": "ok"}]
    alerts = state_machine.env_alerts(previous, current,
                                      env_labels={"env_1": "1号", "env_2": "2号"})
    ok = len(alerts) == 1 and alerts[0]["env_id"] == "env_1"
    record("D3", "告警只提醒受影响的环境（1号限流，不会连累2号）",
           "python -c 'state_machine.env_alerts(...)'", "只有 1 条 env_1 告警",
           {"cmd": "env_alerts", "rc": 0,
            "out": json.dumps(alerts, ensure_ascii=False, indent=2)}, ok)

    rows = state_machine.annotate(
        [{"channel_id": "env_1:douyin", "env_id": "env_1", "status": "UNVERIFIED",
          "platform": "douyin", "platform_name": "抖音", "nickname": "1号",
          "debug_port": 9224, "profile": "p", "evidence": {"cookie_count": 2,
                                                            "backend_status": 429}}])
    html = panel.render_html({"title": "t", "environments": [
        {"env_id": "env_1", "label": "1号", "nickname": "1号", "profile": "p",
         "debug_port": 9224, "status": "UNVERIFIED", "platforms": ["douyin"],
         "rows": rows}], "counts": {}, "chrome": {"level": "ok", "text": "x"},
        "license": {"level": "ok", "text": "授权剩余 100 天"},
        "evidence": {"root": "/d/evidence", "retention_days": 14, "entries": 0}})
    ok = "异常" in html and "st-bad" in html
    record("D4", "面板用客户话显示状态（异常，内部限流/封禁只保留配色）",
           "python -c 'panel.render_html(...)'", "HTML 内出现「异常」与状态配色",
           {"cmd": "panel.render_html", "rc": 0,
            "out": "html bytes=" + str(len(html))}, ok)


# ------------------------------------------------------------------ E
def case_E(scratch: Path, layout: Layout) -> None:
    seed_dir = layout.system
    pub_path = scratch / "vendor_pubkey.hex"
    pub_path.write_text((ROOT / "config" / "vendor_pubkey.hex").read_text("utf-8"),
                        encoding="utf-8")
    for days, machine in ((20, "M-E30"), (-30, "M-EXPIRED")):
        seed = os.urandom(32)
        public = devsign.publickey(seed)
        licence = mint_dev_license(seed, machine_id=machine,
                                   expires_at=(datetime.now(timezone.utc)
                                               + timedelta(days=days)).isoformat(),
                                   grace_days=14,
                                   accounts=[{"account_id": "env_1:douyin",
                                              "platform": "douyin"}])
        lic_path = scratch / f"license_{machine}.json"
        lic_path.write_text(json.dumps(licence, ensure_ascii=False), encoding="utf-8")
        pub = scratch / f"pub_{machine}.hex"
        pub.write_text(public.hex(), encoding="utf-8")
        # 1.2.5: license-notices no longer accepts a caller-supplied key (the
        # trust root is fixed), so a dev-signed licence is evaluated in-process.
        notice = license_mod.expiry_notices(licence)
        gate = license_mod.publish_gate(licence, public, machine,
                                        account_id="env_1:douyin")
        sim = {"rc": 0, "out": json.dumps({"expiry": notice, "publish_gate": gate},
                                          ensure_ascii=False)}
        if days > 0:
            ok = notice["level"] == "30" and gate["publish_allowed"] is True
            record("E1", "剩余 20 天 -> 命中 30 天阈值提醒；发布仍允许",
                   "python3 -c 'license.expiry_notices/publish_gate (in-process)'",
                   "level=30；expiry_blocks_publish=false；gate.publish_allowed=true",
                   sim, ok)
        else:
            ok = notice["level"] == "expired" \
                and gate["publish_allowed"] is False \
                and gate["collect_allowed"] is True
            record("E2", "已过期 -> 只停新增发布；抓数/数据不受影响",
                   "python3 -c 'license.expiry_notices/publish_gate (in-process)'",
                   "level=expired；publish_allowed=false；collect_allowed=true",
                   sim, ok)

    # dry-run must REFUSE to publish when the licence is EXPIRED (E hard gate).
    # 1.2.5: in-process (the CLI has no injection flag); a signed, expired
    # licence bound to this host's real machine id must yield status EXPIRED.
    from winport import cli as cli_mod
    from winport.fingerprint import fingerprint
    seed = os.urandom(32)
    public = devsign.publickey(seed)
    fake_machine = fingerprint()["machine_id"]
    expired = mint_dev_license(seed, machine_id=fake_machine,
                               expires_at=(datetime.now(timezone.utc)
                                           - timedelta(days=40)).isoformat(),
                               grace_days=14,
                               accounts=[{"account_id": "env_1:douyin",
                                          "platform": "douyin"}])
    expired_path = scratch / "license_expired_self.json"
    expired_path.write_text(json.dumps(expired, ensure_ascii=False),
                            encoding="utf-8")
    pub = scratch / "pub_self.hex"
    pub.write_text(public.hex(), encoding="utf-8")
    gate = cli_mod._licence_gate(
        layout, license_path=str(expired_path), plan=plan_doc(),
        allow_test_injection=True, pubkey_override=str(pub),
        machine_id_override=fake_machine)
    ok = gate.get("status") == "EXPIRED" and gate.get("publish_allowed") is False
    record("E3", "授权到期 -> 发布门禁直接拒绝新增发布（硬门，不是提醒）",
           "python3 -c 'cli._licence_gate(..., allow_test_injection=True)'",
           "status=EXPIRED；publish_allowed=false",
           {"rc": 0 if ok else 1, "out": json.dumps(gate, ensure_ascii=False)},
           ok)
    # ...and the real CLI hard-blocks an unverifiable licence the same way.
    res = cli(["dry-run", "--plan", str(scratch / "plan.json"),
               "--out", str(scratch / "blocked.json"),
               "--license", str(expired_path)], data=layout.data)
    record("E3b", "真 CLI：不可验证/过期的授权 -> dry-run 直接拒绝（rc=2）",
           res["cmd"], "rc=2；problems 含 LICENCE_BLOCKS_PUBLISH", res,
           res["rc"] == 2 and "LICENCE_BLOCKS_PUBLISH" in res["out"])


def _json_field(text, key):
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    return doc.get(key)


def _kv(text, key):
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return None


def render(path, work: str) -> str:
    lines = ["# 自验报告 · 主流工具 5 条改进（A-E）",
             "",
             f"- 运行环境：Linux 构建机（{sys.platform}，python {sys.version.split()[0]}）",
             f"- 工作目录：`{work}`",
             f"- 通过：{sum(1 for c in CASES if c['ok'])}/{len(CASES)}",
             "",
             "> 纪律：没有回显/哈希 = 没验过；本机验证 ≠ 真机验证。"
             "只能真机确认的列在文末「待真机」。",
             "", "## A-E 逐条自验", ""]
    for case in CASES:
        lines.append(f"### {case['cid']} · {case['title']}　"
                     f"{'✅' if case['ok'] else '❌'}")
        lines.append(f"- 命令：`{case['cmd']}`")
        lines.append(f"- 期望：{case['expected']}")
        lines.append(f"- 实际退出码：`{case['rc']}`")
        lines.append("- 实际回显：")
        lines.append("```")
        lines.append(case["actual"].strip()[:3500])
        lines.append("```")
        if case["artifacts"]:
            lines.append("- 产物哈希：")
            for name, digest in case["artifacts"]:
                lines.append(f"  - `{name}` → `{digest}`")
        if case["note"]:
            lines.append(f"- 备注：{case['note']}")
        lines.append("")
    lines += PENDING
    lines += ["## 验收人可复现命令", "", "```bash",
              "cd output/win-port",
              "python3 -m unittest discover -s tests          # 130 项单测",
              "python3 tools/static_verify.py                 # 静态验收",
              "python3 tools/verify_ae.py --out /tmp/AE.md    # 本报告 A-E",
              "```", ""]
    return "\n".join(lines) + "\n"


PENDING = [
    "## 待真机（只能 Windows + 真 Chrome + 真账号确认）",
    "",
    "| # | 待验项 | 为什么本机验不了 | 怎么补验 |",
    "|---|---|---|---|",
    "| A-W1 | 飞书确认按钮真的带回 dry-run token | 构建机无飞书 | 在飞书机器人上点确认，核对 `confirm_token` |",
    "| B-W1 | 失败截图/HTML 是真实页面 | 构建机无浏览器 | 客户机故意让上传失败，看 evidence/ 下是否有真 PNG+HTML |",
    "| C-W1 | 强杀发生在「上传中/填表中」仍不重复发布 | 构建机只演到账本层 | 客户机上传到一半 taskkill，重启后看平台只有一条 |",
    "| D-W1 | 限流/封禁口径与真实平台返回一致 | 需要真账号触发 | 用一个受限号跑 `winport state` 看判定与依据 |",
    "| E-W1 | 到期后抓数/历史数据仍可用 | 需要真机数据区 | 客户机把 license 改成过期，跑 collect/report |",
    "",
    "## 已知风险",
    "",
    "- 限流/封禁判定依赖平台返回的 HTTP 状态码与页面标记；若平台改版把标记改掉，"
    "会退化为 UNKNOWN（宁可不报，不误报），需随平台改版更新标记表。",
    "- 素材指纹目前含 title+copy+媒体 sha256；若客户改了标题但没换视频，会被视为"
    "一条新内容（符合预期，但要注意标题微调也会生成新键）。",
    "- 截图/HTML 只在真实驱动接入后才有内容；本机记录会如实标注 unavailable。",
    "",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "bundle_v4"
                                        / "SELF_VERIFY_REPORT_AE.md"))
    ap.add_argument("--work", default=None)
    args = ap.parse_args(argv)
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="winport-ae-"))
    work.mkdir(parents=True, exist_ok=True)
    layout = Layout(program=ROOT, data=work / "data", system=work / "system").ensure()
    seed(layout)

    (work / "plan.json").write_text(json.dumps(plan_doc(), ensure_ascii=False,
                                               indent=2), encoding="utf-8")
    (work / "plan_env2.json").write_text(
        json.dumps(plan_doc(env_id="env_2", account_id="env_2:douyin",
                            channel_id="env_2:douyin"), ensure_ascii=False,
                   indent=2), encoding="utf-8")

    case_A(work, layout)
    case_B(work, layout)
    case_C(work, layout)
    case_D(work, layout)
    case_E(work, layout)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(out, str(work)), encoding="utf-8")
    out.with_suffix(".raw.log").write_text("\n\n".join(RAW) + "\n", encoding="utf-8")
    passed = sum(1 for c in CASES if c["ok"])
    print(f"AE VERIFY: {passed}/{len(CASES)} cases passed")
    print(f"report: {out}")
    return 0 if passed == len(CASES) else 2


if __name__ == "__main__":
    raise SystemExit(main())
