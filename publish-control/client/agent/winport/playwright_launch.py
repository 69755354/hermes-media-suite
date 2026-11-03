"""Headful browser for a WebKit slot (no CDP port exists for WebKit).

Chromium slots are started as a plain process with ``--user-data-dir`` +
``--remote-debugging-port``.  WebKit has no CDP endpoint, so the only honest
way to give the customer a window they can log in to is Playwright's persistent
context, which reuses the same on-disk profile directory and therefore keeps
"one profile = one login state" true for both engines.

The process is a real-machine item: it needs the bundled browsers and the
Playwright wheel, neither of which exist on the Linux build host.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import threading
import time
from pathlib import Path


def _export_browsers_path() -> None:
    program = Path(__file__).resolve().parents[2]
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(program / "browsers"))


def run(profile: str, url: str, *, headless: bool = False) -> int:
    _export_browsers_path()
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        print(f"playwright unavailable: {exc}", file=sys.stderr)
        return 5
    Path(profile).mkdir(parents=True, exist_ok=True)
    closed = threading.Event()
    with sync_playwright() as pw:
        ctx = pw.webkit.launch_persistent_context(profile, headless=headless)
        ctx.on("close", lambda *_: closed.set())
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("close", lambda *_: closed.set())
        if url:
            page.goto(url, wait_until="domcontentloaded")
        while not closed.is_set():
            time.sleep(random.uniform(0.6, 1.4))
        try:
            ctx.close()
        except Exception:
            pass
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="winport.playwright_launch")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--url", default="")
    parser.add_argument("--data")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)
    return run(args.profile, args.url, headless=args.headless)


if __name__ == "__main__":
    raise SystemExit(main())
