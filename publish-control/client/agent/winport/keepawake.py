"""Keep-awake: user-level SetThreadExecutionState (no admin) plus an optional
system-level powercfg enhancement that records the original values so uninstall
can roll them back (Windows plan section 5)."""

from __future__ import annotations

from . import win32


class KeepAwake:
    def __init__(self, logger=None):
        self.logger = logger
        self.active = False
        self.last_state = None
        self.reason = ""

    def acquire(self) -> bool:
        flags = (win32.ES_CONTINUOUS | win32.ES_SYSTEM_REQUIRED
                 | win32.ES_DISPLAY_REQUIRED)
        state = win32.set_thread_execution_state(flags)
        if not win32.IS_WINDOWS:
            self.reason = "non-windows: no-op (static test)"
            return False
        if state is None:
            self.reason = "SetThreadExecutionState failed"
            return False
        self.last_state = state
        self.active = True
        self.reason = ("holding ES_CONTINUOUS|ES_SYSTEM_REQUIRED|ES_DISPLAY_REQUIRED; "
                       "verify on the real machine with powercfg /requests")
        return True

    def release(self) -> None:
        if self.active:
            win32.set_thread_execution_state(win32.ES_CONTINUOUS)
            self.active = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


# --- optional system-level enhancement (needs admin) -----------------------
POWERCFG_KEYS = {
    "standby-timeout-ac": ("SUB_SLEEP", "STANDBYIDLE"),
    "monitor-timeout-ac": ("SUB_VIDEO", "VIDEOIDLE"),
    "disk-timeout-ac": ("SUB_DISK", "DISKIDLE"),
    "lid-action-ac": ("SUB_BUTTONS", "LIDACTION"),
}


def powercfg_command(key: str, value: int) -> str:
    name = POWERCFG_KEYS[key]
    if key == "standby-timeout-ac":
        return f"powercfg /change standby-timeout-ac {value}"
    if key == "monitor-timeout-ac":
        return f"powercfg /change monitor-timeout-ac {value}"
    if key == "disk-timeout-ac":
        return f"powercfg /change disk-timeout-ac {value}"
    return (f"powercfg /setacvalueindex SCHEME_CURRENT {name[0]} {name[1]} {value}"
            "  &&  powercfg /setactive SCHEME_CURRENT")


def revert_commands(original: dict) -> list:
    """original = {key: value} captured before we changed anything."""
    return [powercfg_command(k, v) for k, v in (original or {}).items()]
