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
    # 按当天实际导出的文件枚举账号，不写死客户昵称（与 bot.collect_and_report 同一逻辑）。
    paths, labels, missing = [], [], []
    for idx, (_name, blob) in enumerate(bot._fetch_client_files(
            bot.run_on_client, base + "\\douyin\\作品列表导出_%s*.json" % day)):
        local = "/tmp/dy%d.json" % (idx + 1)
        open(local, "wb").write(blob)
        paths.append(local); labels.append(bot._ordinal_label(idx))
    if not paths:
        print("FAIL: 今天没有任何账号的作品导出（客户机没登录或不可达）")
        return 2

    # 1.2.188 起星图每个账号一份，全部带上。
    star_paths = []
    for idx, (_name, blob) in enumerate(bot._fetch_client_files(
            bot.run_on_client, base + "\\xingtu\\星图数据_%s*.json" % day)):
        local = "/tmp/xt%d.json" % (idx + 1)
        open(local, "wb").write(blob); star_paths.append(local)
    star_ok = bool(star_paths)

    out = os.path.join(a.out_dir, "两个号作品_%s.xlsx" % day)
    cmd = ["python3", BUILD, "--douyin"] + paths + ["--labels", ",".join(labels), "--out", out]
    if star_ok:
        cmd += ["--star"] + star_paths
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if missing:
        print("NOTE: %s 没登录没取到，表里只有 %s" % ("、".join(missing), "、".join(labels)))
    if not star_ok:
        print("NOTE: 星图数据没取到，表里星图列为 0")
    print("OUTPUT: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
