"""上传校验、改名、EXIF 清理与项目目录约束。"""

from __future__ import annotations

import hashlib
import io
import os
import json
import subprocess
import uuid
from pathlib import Path

from PIL import Image


MAX_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
MAX_VIDEO_SECONDS = 600
MAX_VIDEO_PIXELS = 4096 * 4096
MAX_VIDEO_FPS = 60.0
MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    "image/webp": (b"RIFF", ".webp"),
    "video/mp4": (None, ".mp4"),
}


def safe_child(root: Path, candidate: Path) -> Path:
    root_real = root.resolve()
    target = candidate.resolve()
    if root_real != target and root_real not in target.parents:
        raise ValueError("非法文件路径")
    return target


def detect_mime(data: bytes, declared: str) -> tuple[str, str]:
    if len(data) > MAX_BYTES:
        raise ValueError("单个素材不得超过 20MB")
    if declared not in MAGIC:
        raise ValueError("只支持 JPG、PNG、WEBP 或 MP4")
    prefix, suffix = MAGIC[declared]
    if prefix and not data.startswith(prefix):
        raise ValueError("素材类型与文件内容不一致")
    if declared == "image/webp" and data[8:12] != b"WEBP":
        raise ValueError("WEBP 文件头无效")
    if declared == "video/mp4" and (len(data) < 12 or data[4:8] != b"ftyp"):
        raise ValueError("MP4 文件头无效")
    return declared, suffix


def store_upload(project_dir: Path, original_name: str, declared_mime: str, data: bytes) -> tuple[Path, str, str]:
    mime, suffix = detect_mime(data, declared_mime)
    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{suffix}"
    target = safe_child(assets_dir, assets_dir / stored)
    if mime.startswith("image/"):
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("图片像素过大")
            output = io.BytesIO()
            if suffix == ".jpg":
                image.convert("RGB").save(output, "JPEG", quality=92, optimize=True)
            elif suffix == ".png":
                image.save(output, "PNG", optimize=True)
            else:
                image.save(output, "WEBP", quality=92)
            data = output.getvalue()  # 重编码自然剥离 EXIF/GPS。
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError("图片无法解析") from exc
    staging = safe_child(assets_dir, assets_dir / f".{uuid.uuid4().hex}.upload")
    try:
        staging.write_bytes(data)
        os.chmod(staging, 0o640)
        if mime == "video/mp4":
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration:stream=codec_type,width,height,avg_frame_rate", "-of", "json", str(staging),
                ],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if probe.returncode != 0:
                raise ValueError("视频无法解析")
            metadata = json.loads(probe.stdout)
            duration = float(metadata.get("format", {}).get("duration") or 0)
            video_stream = next((row for row in metadata.get("streams", []) if row.get("codec_type") == "video"), None)
            if not video_stream or not 0 < duration <= MAX_VIDEO_SECONDS:
                raise ValueError("视频时长无效或超过 10 分钟")
            if int(video_stream.get("width") or 0) * int(video_stream.get("height") or 0) > MAX_VIDEO_PIXELS:
                raise ValueError("视频像素过大")
            rate = str(video_stream.get("avg_frame_rate") or "0/1").split("/", 1)
            fps = float(rate[0]) / max(float(rate[1]), 1.0)
            if fps <= 0 or fps > MAX_VIDEO_FPS:
                raise ValueError("视频帧率无效或超过 60fps")
        os.replace(staging, target)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    return target, mime, hashlib.sha256(data).hexdigest()
