"""防黑屏：常驻进程运行期间保持显示器/系统唤醒（仅 Windows 生效）。

背景：客户机在无人操作时执行排期/取数，Windows 会按电源计划关显示器，
看起来就是“电脑老黑屏”。这里用 SetThreadExecutionState 在独立线程里持续
声明 ES_DISPLAY_REQUIRED，进程退出即自动失效，不修改任何系统电源设置。
"""
from __future__ import annotations

import os
import threading
import time

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

_thread = None
_lock = threading.Lock()


def _loop(interval: float = 55.0) -> None:
    import ctypes
    k32 = ctypes.windll.kernel32
    while True:
        try:
            k32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
        except Exception:
            return
        time.sleep(interval)


def keep_display_awake(interval: float = 55.0) -> bool:
    """启动一个守护线程持续抑制息屏；重复调用只启动一次。"""
    global _thread
    if os.name != "nt":
        return False
    with _lock:
        if _thread is not None and _thread.is_alive():
            return True
        _thread = threading.Thread(target=_loop, args=(interval,),
                                   daemon=True, name="winport-keep-awake")
        _thread.start()
        return True
