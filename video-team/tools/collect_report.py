#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据组执行器：取数 → 20 列作品表。不发飞书、不刷屏，只交文件。"""
import argparse, base64, os, re, subprocess, sys, time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOT_DIR = os.environ.get("FEISHU_BOT_DIR") or os.path.join(_ROOT, "publish-control", "feishu_publish_bot")
BUILD = os.environ.get("BUILD_TWO_ACCOUNT_SCRIPT") or os.path.join(_ROOT, "video-team", "tools", "build_two_account_table.py")
sys.path.insert(0, BOT_DIR)


def _b64_from(text):
    for ln in reversed((text or "").splitlines()):
        s = ln.strip()
        if re.fullmatch(r"[A-Za-z0-9+/=]{100,}", s or ""):
            return s
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    import bot

    bot.ensure_browser("env_2", 9225)
    d = bot.run_cli(["collect-all"], timeout=115)
    ok = d.get("exit_code") in (0, None)
    if not ok:
        try:
            import json as _j
            ok = bool((_j.loads((d.get("stdout") or "").strip()).get("collected") or {}).get("douyin"))
        except Exception:
            ok = False
    if not ok:
        print("FAIL: 取数没完成：%s" % ((d.get("stderr") or d.get("stdout") or "")[:300]))
        return 2

    base = os.path.join(bot.customer_data_root(None), "out")
    day = time.strftime("%Y%m%d")
    cands = [("/tmp/dy1.json", base + "\\douyin\\作品列表导出_%s_蜡笔新小漫.json" % day, "一号"),
             ("/tmp/dy2.json", base + "\\douyin\\作品列表导出_%s_漫半拍.json" % day, "二号")]
    paths, labels, missing = [], [], []
    for local, remote, label in cands:
        code = 'import base64;print(base64.b64encode(open(r"%s","rb").read()).decode())' % remote
        dd = bot.run_on_client(code, timeout=100)
        b64 = _b64_from(dd if isinstance(dd, str) else (dd.get("stdout") or ""))
        if not b64:
            missing.append(label)
            continue
        open(local, "wb").write(base64.b64decode(b64))
        paths.append(local); labels.append(label)
    if not paths:
        print("FAIL: 两个号都没导出数据（客户机没登录或不可达）：%s" % "、".join(missing))
        return 2

    star_ok = False
    xt_remote = base + "\\xingtu\\星图数据_%s.json" % day
    code = 'import base64;print(base64.b64encode(open(r"%s","rb").read()).decode())' % xt_remote
    dd = bot.run_on_client(code, timeout=100)
    b64 = _b64_from(dd if isinstance(dd, str) else (dd.get("stdout") or ""))
    if b64:
        open("/tmp/xt.json", "wb").write(base64.b64decode(b64)); star_ok = True

    out = os.path.join(a.out_dir, "两个号作品_%s.xlsx" % day)
    cmd = ["python3", BUILD, "--douyin"] + paths + ["--labels", ",".join(labels), "--out", out]
    if star_ok:
        cmd += ["--star", "/tmp/xt.json"]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if missing:
        print("NOTE: %s 没登录没取到，表里只有 %s" % ("、".join(missing), "、".join(labels)))
    if not star_ok:
        print("NOTE: 星图数据没取到，表里星图列为 0")
    print("OUTPUT: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
