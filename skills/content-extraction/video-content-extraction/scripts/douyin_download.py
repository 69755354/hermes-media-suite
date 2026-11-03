#!/usr/bin/env python3
"""抖音视频下载：Playwright 手机UA 打开页面 → DOM 拿 video.src → 输出直链。

用法:
  python3 douyin_download.py <分享短链或video_id> [输出路径]

示例:
  python3 douyin_download.py "https://v.douyin.com/OUi300hX7Gw/" /tmp/video.mp4
  python3 douyin_download.py 7673448791810946283 /tmp/video.mp4

依赖:
  pip3 install playwright
  chromium 由 `python3 -m playwright install chromium` 安装到 ~/.cache/ms-playwright/
"""
import sys, time, re, json, subprocess, os, glob

PHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")


def find_chromium() -> str:
    """自动探测已安装的 chromium 二进制路径，兼容版本号变化。"""
    # 1. 优先用 playwright 内置的默认路径（让 playwright 自己选）
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        default = p.chromium.executable_path
        if default and os.path.exists(default):
            return default
    # 2. glob 扫描 ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
    base = os.path.expanduser("~/.cache/ms-playwright")
    candidates = sorted(glob.glob(f"{base}/chromium-*/chrome-linux64/chrome"), reverse=True)
    if candidates:
        return candidates[0]
    # 3. headless_shell fallback
    candidates = sorted(glob.glob(f"{base}/chromium_headless_shell-*/chrome-headless-shell-linux64/headless_shell"), reverse=True)
    if candidates:
        return candidates[0]
    raise RuntimeError(
        "未找到 chromium 二进制。请运行: python3 -m playwright install chromium")


def resolve_video_id(short_url: str) -> str:
    """分享短链 → video_id（curl 跟随重定向）"""
    r = subprocess.run(
        ["curl", "-s", "-L", short_url, "-H", f"User-Agent: {PHONE_UA}"],
        capture_output=True, text=True, timeout=30)
    m = re.search(r"(?:share/video|video/)(\d+)", r.stdout)
    if not m:
        raise RuntimeError(f"无法从短链提取 video_id: {short_url}")
    return m.group(1)

def get_video_src(video_id: str, timeout_ms: int = 45000) -> str:
    """Playwright 手机UA 打开页面，从 DOM video 元素拿直链。"""
    from playwright.sync_api import sync_playwright
    chrome_path = find_chromium()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, executable_path=chrome_path,
            args=['--no-sandbox', '--disable-dev-shm-usage'])
        try:
            context = browser.new_context(
                viewport={'width': 390, 'height': 844},
                user_agent=PHONE_UA, locale='zh-CN')
            page = context.new_page()
            page.goto(f"https://www.douyin.com/video/{video_id}",
                      wait_until='domcontentloaded', timeout=timeout_ms)
            time.sleep(6)  # 等视频加载（readyState=4）
            src = page.evaluate(
                "() => { const v = document.querySelector('video'); return v ? (v.src || v.currentSrc) : null; }")
            if not src:
                raise RuntimeError("页面无 video 元素或 src 为空")
            return src
        finally:
            browser.close()

def download(src: str, out_path: str) -> None:
    """手机UA + Referer curl 下载（必须 -L 跟进 302）。"""
    r = subprocess.run([
        "curl", "-s", "-L", "--max-time", "120", src,
        "-H", f"User-Agent: {PHONE_UA}",
        "-H", "Referer: https://www.douyin.com/",
        "-o", out_path, "-w", "%{http_code} %{size_download}"],
        capture_output=True, text=True, timeout=150)
    code, size = r.stdout.split()
    if code != "200" or int(size) < 10000:
        raise RuntimeError(f"下载失败 HTTP={code} size={size}")
    print(f"OK: {out_path} ({int(size)//1024}KB) HTTP={code}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    arg = sys.argv[1].strip()
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/douyin_video.mp4"
    video_id = arg if arg.isdigit() else resolve_video_id(arg)
    print(f"video_id: {video_id}")
    src = get_video_src(video_id)
    print(f"直链: {src[:120]}...")
    download(src, out)
