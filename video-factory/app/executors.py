"""采集、转写、跨机推理、免费合成和 MOCK 演示执行器。"""
# > 执行者：codex

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import glob
from pathlib import Path
from urllib.parse import quote_plus

from .media_runtime import run_ffmpeg


def collect_with_playwright(query: str, output: Path, limit: int = 5) -> list[dict[str, str]]:
    from playwright.sync_api import sync_playwright

    results: list[dict[str, str]] = []
    with sync_playwright() as api:
        candidates = sorted(glob.glob(str(Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / ".cache" / "ms-playwright") / "chromium-*" / "chrome-linux*" / "chrome")), reverse=True)
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH") or (candidates[0] if candidates else None)
        browser = api.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
        page.goto(f"https://www.bing.com/search?q={quote_plus(query)}", wait_until="domcontentloaded", timeout=45_000)
        for item in page.locator("li.b_algo h2 a").all()[:limit]:
            title = (item.inner_text() or "").strip()
            url = item.get_attribute("href") or ""
            if title and url.startswith("http"):
                results.append({"title": title, "url": url, "source": "公开网页", "verified_at": page.evaluate("new Date().toISOString()")})
        if not results:
            page.goto(f"https://www.baidu.com/s?wd={quote_plus(query)}", wait_until="domcontentloaded", timeout=45_000)
            for item in page.locator("#content_left h3 a").all()[:limit]:
                title = (item.inner_text() or "").strip()
                url = item.get_attribute("href") or ""
                if title and url.startswith("http"):
                    results.append({"title": title, "url": url, "source": "公开网页", "verified_at": page.evaluate("new Date().toISOString()")})
        browser.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"query": query, "items": results, "note": "公开搜索结果索引；使用前仍需打开原文核验。"}, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def transcribe_with_whisper(media: Path, output: Path, model_name: str = "small") -> dict[str, object]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8", local_files_only=True)
    segments, info = model.transcribe(str(media), language="zh", vad_filter=True)
    rows = [{"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()} for seg in segments]
    payload = {"language": info.language, "duration": info.duration, "segments": rows, "engine": "本地语音转写"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def reason_with_codex(prompt: str, output: Path, timeout: int = 420) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="factory-reason-", suffix=".txt", delete=False) as handle:
        last_message = Path(handle.name)
    try:
        allowed_env = {
            key: value for key, value in os.environ.items()
            if key in {"PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "TERM", "SSL_CERT_FILE", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"}
        }
        allowed_env["NO_COLOR"] = "1"
        from . import config

        remote_script = Path(config.remote_codex_script())
        if remote_script.is_file():
            # 广州不安装 Codex；prompt 通过 stdin 进入已有安全包装，再由 SSH 发往新加坡。
            result = subprocess.run(
                [str(remote_script), prompt],
                cwd=str(config.REPO_ROOT), capture_output=True, text=True,
                timeout=timeout, check=False, env=allowed_env,
            )
            text = result.stdout.strip()
        else:
            result = subprocess.run(
                ["codex", "exec", "--sandbox", "read-only", "--output-last-message", str(last_message), prompt],
                cwd=str(config.REPO_ROOT), capture_output=True, text=True,
                timeout=timeout, check=False, env=allowed_env,
            )
            text = last_message.read_text(encoding="utf-8") if last_message.exists() else ""
        if result.returncode != 0 or not text:
            raise RuntimeError((result.stderr or result.stdout or "推理执行失败")[-1000:])
        output.write_text(text, encoding="utf-8")
        return text
    finally:
        last_message.unlink(missing_ok=True)


def compose_mock_video(output: Path, duration: int = 30) -> dict[str, object]:
    """使用 ffmpeg 真合成带永久识别角标的演示片，不调用任何付费服务。"""
    output.parent.mkdir(parents=True, exist_ok=True)
    if "_MOCK" not in output.name:
        raise ValueError("MOCK 文件名必须带 _MOCK")
    font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    vf = (
        "drawbox=x=0:y=0:w=iw:h=110:color=black@0.55:t=fill,"
        f"drawtext=fontfile={font}:text='演示样片':fontcolor=white:fontsize=52:x=(w-text_w)/2:y=28,"
        f"drawtext=fontfile={font}:text='付费制作尚未放行':fontcolor=white:fontsize=34:x=(w-text_w)/2:y=(h-text_h)/2"
    )
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0xB72A20:s=720x1280:r=25:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=48000:duration={duration}",
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(output),
    ]
    run_ffmpeg(cmd, capture_output=True, text=True, timeout=180, check=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height", "-of", "json", str(output)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return json.loads(probe.stdout)
