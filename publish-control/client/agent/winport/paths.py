"""Program-area / data-area / system-area path resolution.

Windows layout (source/win-local-agent-package-plan.md section 1.2):
  program : %LOCALAPPDATA%\\Programs\\<Vendor>\\<App>   (user)  or Program Files (machine)
  data    : %LOCALAPPDATA%\\<Vendor>\\publish-worker
  system  : %APPDATA%\\<Vendor>\\Agent

The data area is NEVER overwritten by updates.  Data deliberately avoids
Desktop / Documents / Pictures (Windows Controlled Folder Access == macOS TCC
analogue) and avoids OneDrive redirection.

Every path is overridable by an environment variable so the same code runs in
the Linux static self-test without touching a real user profile:
  WINPORT_PROGRAM / WINPORT_DATA / WINPORT_SYSTEM
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .errors import StorageNotWritable
from .version import APP_NAME, VENDOR


def is_windows() -> bool:
    return os.name == "nt"


def program_dir() -> Path:
    """Root of the installed program area (read-only, replaced on update)."""
    env = os.environ.get("WINPORT_PROGRAM")
    if env:
        return Path(env).expanduser()
    # this file: <program>/agent/winport/paths.py  -> parents[2] == <program>
    return Path(__file__).resolve().parents[2]


def install_root() -> Path:
    """The directory this code ACTUALLY runs from -- never overridable.

    1.2.5 (GPT review 1.2.5 item 3): the trust root (``config/vendor_pubkey.hex``)
    and the startup-chain manifest MUST be read from here, not from a
    caller-supplied ``--program`` / ``WINPORT_PROGRAM``.  Those two are still
    honoured for *data/config* paths (the Linux static test needs them), but a
    caller cannot point the crypto trust chain at their own directory.
    """
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    env = os.environ.get("WINPORT_DATA")
    if env:
        return Path(env).expanduser()
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / VENDOR / "publish-worker"


def system_dir() -> Path:
    env = os.environ.get("WINPORT_SYSTEM")
    if env:
        return Path(env).expanduser()
    if is_windows():
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / VENDOR / "Agent"


# Data-area subdirectories, exactly matching the Mac layout (Mac plan section 1.3).
DATA_SUBDIRS = (
    # 1.1.0 environment model (source/env-design.md): one profile dir per env.
    "profiles/env_1",
    "profiles/env_2",
    "profiles/env_wechat",
    "profiles/env_xhs",
    "run/envs",
    # legacy per-platform slots kept so an in-place upgrade never loses a login
    "profiles/douyin",
    "profiles/douyin-webkit",
    # multi-platform login slots (source/extra-requirements-update.md section 3)
    "profiles/xingtu",
    "profiles/shipinhao",
    "profiles/xiaohongshu",
    "profiles/gongzhonghao",
    "config",
    "run",
    "run/profiles",
    "logs",
    "evidence",
    "media",
    "inbox",
    "outbox",
    "out/douyin",
    "out/xingtu",
    "out/reports",
    "bin",
    "app",
)


class Layout:
    """Resolved directories for one installation, with idempotent ensure()."""

    def __init__(self, program: Path | None = None, data: Path | None = None,
                 system: Path | None = None):
        self.program = Path(program) if program else program_dir()
        self.data = Path(data) if data else data_root()
        self.system = Path(system) if system else system_dir()

    # ---- data area -----------------------------------------------------
    @property
    def profiles(self) -> Path:
        # Chrome 由 agent 以安装根(<install>\profiles\env_N)启动，而客户数据目录
        # (<install>\customers\<cid>) 下还留着一份旧版 profiles。发布 CLI 的端口
        # 归属校验比对的是 --user-data-dir 的字面路径，取错目录会直接拒绝发布
        # （"无法安全确认占用端口 9225 的进程属于2号 的 Chrome 配置目录"）。
        # 安装根存在非空 profiles 时一律以它为准。
        local = self.data / "profiles"
        try:
            if self.data.parent.name.lower() == "customers":
                shared = self.data.parent.parent / "profiles"
                if shared.is_dir() and any(shared.iterdir()):
                    return shared
        except OSError:
            pass
        return local

    @property
    def profile_douyin(self) -> Path:
        return self.data / "profiles" / "douyin"

    @property
    def profile_webkit(self) -> Path:
        return self.data / "profiles" / "douyin-webkit"

    @property
    def config(self) -> Path:
        return self.data / "config"

    @property
    def run(self) -> Path:
        return self.data / "run"

    @property
    def logs(self) -> Path:
        return self.data / "logs"

    @property
    def evidence(self) -> Path:
        return self.data / "evidence"

    @property
    def media(self) -> Path:
        return self.data / "media"

    @property
    def inbox(self) -> Path:
        return self.data / "inbox"

    @property
    def outbox(self) -> Path:
        return self.data / "outbox"

    @property
    def out_douyin(self) -> Path:
        return self.data / "out" / "douyin"

    @property
    def out_xingtu(self) -> Path:
        return self.data / "out" / "xingtu"

    @property
    def out_reports(self) -> Path:
        return self.data / "out" / "reports"

    @property
    def bin(self) -> Path:
        return self.data / "bin"

    @property
    def app_versions(self) -> Path:
        return self.data / "app"

    # ---- program area --------------------------------------------------
    @property
    def runtime(self) -> Path:
        return self.program / "runtime"

    @property
    def wheels(self) -> Path:
        return self.program / "wheels"

    @property
    def browsers(self) -> Path:
        return self.program / "browsers"

    @property
    def ffmpeg(self) -> Path:
        return self.program / "bin" / ("ffmpeg.exe" if is_windows() else "ffmpeg")

    # ---- locks / ledgers ----------------------------------------------
    @property
    def agent_lock(self) -> Path:
        return self.run / "agent.lock"

    @property
    def one_browser_lock(self) -> Path:
        return self.run / "one-browser.lock"

    @property
    def profile_locks(self) -> Path:
        """One launch marker per login slot (never two browsers on one profile)."""
        return self.run / "profiles"

    @property
    def channels_file(self) -> Path:
        return self.config / "channels.json"

    @property
    def environments_file(self) -> Path:
        return self.config / "environments.json"

    @property
    def chrome_state_file(self) -> Path:
        return self.run / "chrome-state.json"

    @property
    def env_lease_dir(self) -> Path:
        """One lease file per environment (single browser instance per env)."""
        return self.run / "envs"

    @property
    def channel_state_file(self) -> Path:
        return self.run / "channel-state.json"

    @property
    def stage2_ledger(self) -> Path:
        return self.run / "stage2-ledger.json"

    @property
    def downlink_ledger(self) -> Path:
        return self.run / "downlink-ledger.jsonl"

    @property
    def downlink_queue(self) -> Path:
        return self.run / "downlink-queue.json"

    @property
    def settings_file(self) -> Path:
        return self.config / "settings.json"

    @property
    def accounts_file(self) -> Path:
        return self.config / "accounts.json"

    @property
    def license_file(self) -> Path:
        return self.system / "license.json"

    def ensure(self) -> "Layout":
        """Create the data area if missing. Idempotent; never deletes."""
        try:
            for sub in DATA_SUBDIRS:
                (self.data / sub).mkdir(parents=True, exist_ok=True)
            self.system.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - platform dependent
            raise StorageNotWritable(f"cannot create data area {self.data}: {exc}")
        return self

    def writable(self) -> bool:
        probe = self.data / ".write-probe"
        try:
            self.data.mkdir(parents=True, exist_ok=True)
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            return False

    def describe(self) -> str:
        return (f"program={self.program}\n"
                f"data={self.data}\n"
                f"system={self.system}\n"
                f"platform={'windows' if is_windows() else sys.platform}")
