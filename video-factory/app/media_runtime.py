"""单机多进程共享的媒体转码资源闸门。"""

from __future__ import annotations

import fcntl
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from . import config


@contextmanager
def media_slot(lock_dir: Path, slots: int) -> Iterator[None]:
    """通过文件槽锁限制整台广州机的 ffmpeg 并发数。"""
    slot_dir = Path(lock_dir).resolve() / "media-slots"
    slot_dir.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    while descriptor is None:
        for index in range(slots):
            candidate = os.open(
                slot_dir / f"ffmpeg-{index}.lock", os.O_CREAT | os.O_RDWR, 0o640
            )
            try:
                fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(candidate)
                continue
            descriptor = candidate
            break
        if descriptor is None:
            time.sleep(0.05)
    try:
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _single_thread_command(command: Sequence[str]) -> list[str]:
    result = list(command)
    if not result or Path(result[0]).name != "ffmpeg":
        raise ValueError("媒体闸门只接受 ffmpeg 命令")
    # 末尾参数覆盖调用方可能传入的更高线程数；编码器与滤镜都固定为 1。
    result[-1:-1] = [
        "-threads", "1", "-filter_threads", "1", "-filter_complex_threads", "1"
    ]
    return result


def run_ffmpeg(
    command: Sequence[str],
    *,
    lock_dir: Path | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    shared_lock_dir = lock_dir or (
        config.database_path().parent / ".factory-locks"
    )
    with media_slot(shared_lock_dir, config.media_concurrency()):
        return subprocess.run(_single_thread_command(command), **kwargs)
