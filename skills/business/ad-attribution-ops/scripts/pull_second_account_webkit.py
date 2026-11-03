#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""二号（蜡笔新小漫）作品数据采集：Playwright WebKit + 已登录 profile，同源 GET 导出接口。

为何需要它：douyin_creator_collect.py 只能挂 CDP Chrome（一号的 9224）。二号的登录态在
Playwright WebKit 的 profiles/douyin-webkit 里（CDP 挂不上），所以单独走本脚本。

用法（Mac 上跑）：
  cd ~/publish-worker && .venv/bin/python pull_second_account_webkit.py [--date YYYYMMDD]
产物：~/publish-worker/out/douyin2/作品列表导出_<日期>_二号.xlsx
注意：launch_persistent_context 会用该 profile；跑前确认没有别的自动化浏览器在用它。
"""
import argparse, datetime, pathlib
from playwright.sync_api import sync_playwright

PROF = "/Users/<MAC_USER>/publish-worker/profiles/douyin-webkit"
OUT = pathlib.Path("/Users/<MAC_USER>/publish-worker/out/douyin2")
API = "https://creator.douyin.com/web/api/creator/item/list/download"
PAGE = "https://creator.douyin.com/creator-micro/data/manage/works"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / ("作品列表导出_" + a.date + "_二号.xlsx")
    with sync_playwright() as p:
        ctx = p.webkit.launch_persistent_context(PROF, headless=False)
        try:
            pg = ctx.new_page()
            try:
                pg.goto(PAGE, wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_timeout(4000)
            except Exception as e:
                print("PAGE_ERR:", type(e).__name__, str(e)[:120])
            r = ctx.request.get(API, timeout=60000)
            b = r.body()
            print("HTTP:", r.status, "BYTES:", len(b))
            if len(b) > 2000 and b[:2] == b"PK":
                dst.write_bytes(b)
                print("SAVED:", dst)
            else:
                print("BLOCKED 未登录或接口变了:", b[:200])
            pg.close()
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
