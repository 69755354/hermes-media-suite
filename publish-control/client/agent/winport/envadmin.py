"""Self-service environment administration (1.2.18).

The customer adds / disables / deletes Douyin accounts from the local panel.
This module is the single writer of ``config/environments.json`` for those
operations, so every path takes the same registry lock, re-reads the file under
the lock, re-checks the port, and writes atomically.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from .environments import Environment, default_environments, environment_from_entry, validate_environments
from .errors import ConfigError
from .jsonio import read_json, write_json
from .lock import FileLock
from .subprocess_text import hidden_window_options, text_mode_options

MAX_ACCOUNTS = 4
DEFAULT_SEATS = 4
SUPPORTED_PLATFORMS = ("douyin", "xingtu")
REGISTRY_LOCK_NAME = "environments-admin.lock"
PORT_SCAN_START = 9224
PORT_SCAN_STOP = PORT_SCAN_START + 4000


def visible_envs(envs):
    return [env for env in (envs or []) if getattr(env, "visible", True)]


def license_account_limit(layout=None, *, license_obj=None) -> int:
    """Seats ceiling: ``min(4, license.seats)``, defaulting to 4.

    This is a display/self-service limit, not a signature verdict.  A damaged or
    missing licence falls back to the shipped default so the customer can still
    install and use the panel; publishing remains separately gated by the full
    licence check.
    """
    if license_obj is None and layout is not None:
        from .licstate import read_license_file
        read = read_license_file(layout.license_file)
        if read.get("kind") == "ok":
            license_obj = read.get("obj")
    seats = DEFAULT_SEATS
    if isinstance(license_obj, dict) and "seats" in license_obj:
        try:
            parsed = int(license_obj["seats"])
        except (TypeError, ValueError):
            parsed = DEFAULT_SEATS
        if parsed >= 0:
            seats = parsed
    return min(MAX_ACCOUNTS, seats)


def _registry_lock(layout) -> FileLock:
    return FileLock(layout.run / REGISTRY_LOCK_NAME)


def _read_registry(layout):
    raw = read_json(layout.environments_file, default=None)
    if raw is None:
        raw = {"environments": [e.describe() for e in default_environments()]}
    elif isinstance(raw, list):
        raw = {"environments": raw}
    elif not isinstance(raw, dict):
        raise ConfigError("environments.json 顶层必须是对象或数组")
    entries = raw.get("environments")
    if not isinstance(entries, list):
        entries = []
    envs = [environment_from_entry(e) for e in entries]
    problems = validate_environments(envs)
    if problems:
        raise ConfigError("environments.json 有配置错误：" + "；".join(problems))
    return raw, envs


def _write_registry(layout, raw) -> None:
    write_json(layout.environments_file, raw)


def _normalise_label(label: str | None, default: str) -> str:
    text = (label or "").strip()
    if not text:
        return default
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) > 30:
        text = text[:30]
    return text


def _normalise_platforms(platforms) -> tuple[list[str] | None, str | None]:
    if platforms is None or platforms == "":
        return list(SUPPORTED_PLATFORMS), None
    if isinstance(platforms, str):
        parts = [p.strip() for p in platforms.replace("，", ",").split(",") if p.strip()]
    elif isinstance(platforms, (list, tuple, set)):
        parts = [str(p).strip() for p in platforms if str(p).strip()]
    else:
        return None, "平台参数必须是名称或名称列表"
    unique = []
    for platform in parts:
        if platform in SUPPORTED_PLATFORMS and platform not in unique:
            unique.append(platform)
        elif platform not in SUPPORTED_PLATFORMS:
            return None, f"本版只支持抖音和星图，不能添加平台：{platform}"
    if not unique:
        return None, "请至少选择一个平台"
    return unique, None


def _port_open(host: str, port: int, probe=None) -> bool:
    if probe is not None:
        try:
            return bool(probe(host, int(port)))
        except Exception:
            return False
    from .health import tcp_listening
    return tcp_listening(host, int(port))


def find_free_debug_port(used_ports, *, probe=None, start=PORT_SCAN_START,
                         stop=PORT_SCAN_STOP) -> int | None:
    used = {int(p) for p in (used_ports or set()) if p is not None}
    for port in range(start, stop + 1):
        if port in used:
            continue
        if not _port_open("127.0.0.1", port, probe=probe):
            return port
    return None


def default_shortcut_maker(layout, env=None):
    """Refresh the three fixed shortcuts via ``scripts/make-shortcut.ps1``.

    ``env`` is kept for caller compatibility; 1.2.32 no longer creates a
    per-environment desktop icon.
    """
    if os.name != "nt":
        return {"ok": True, "skipped": True, "reason": "非 Windows 环境，跳过桌面快捷方式"}
    script = layout.program / "scripts" / "make-shortcut.ps1"
    if not script.exists():
        return {"ok": False, "error": f"找不到桌面快捷方式脚本：{script}"}
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-File", str(script), "-Program", str(layout.program),
           "-DataDir", str(layout.data)]
    try:
        proc = subprocess.run(cmd, cwd=str(layout.program), timeout=90,
                              capture_output=True,
                              **hidden_window_options(cmd),
                              **text_mode_options())
        if proc.returncode == 0:
            return {"ok": True, "env_id": getattr(env, "env_id", None)}
        return {"ok": False, "error": (proc.stderr or proc.stdout or "").strip()[:400]}
    except Exception as exc:
        return {"ok": False, "error": f"桌面快捷方式刷新失败：{exc}"}


def add_environment(layout, *, label=None, platforms=None, probe=None,
                    shortcut_maker=None, account_limit=None,
                    lock_timeout=10.0) -> dict:
    layout.ensure()
    lock = _registry_lock(layout)
    if not lock.acquire(timeout=lock_timeout):
        return {"ok": False, "error": "账号配置正在被另一个操作占用，请稍后再试"}
    try:
        raw, envs = _read_registry(layout)
        visible = visible_envs(envs)
        limit = account_limit if account_limit is not None else license_account_limit(layout)
        if len(visible) >= limit:
            if limit >= MAX_ACCOUNTS:
                return {"ok": False, "error": "本机最多 4 个账号，要更多请再加一台电脑"}
            return {"ok": False,
                    "error": f"当前授权只支持 {limit} 个账号；要继续请续费，或换一台电脑后重新导入授权"}

        wanted, platform_error = _normalise_platforms(platforms)
        if platform_error:
            return {"ok": False, "error": platform_error}
        default_label = f"{len(visible) + 1}号"
        label = _normalise_label(label, default_label)
        if any(e.visible and e.label == label for e in envs):
            return {"ok": False, "error": f"已经有叫「{label}」的账号，请换一个名字"}
        env_id = _next_env_id(envs)
        profile_name = env_id
        used_ports = {e.debug_port for e in envs if e.debug_port is not None}
        port = find_free_debug_port(used_ports, probe=probe)
        if port is None:
            return {"ok": False, "error": "找不到可用调试端口，请关闭占用端口的程序后重试"}
        if _port_open("127.0.0.1", port, probe=probe):
            return {"ok": False, "error": f"调试端口 {port} 刚被占用，请重试"}

        profile_dir = layout.profiles / profile_name
        try:
            profile_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return {"ok": False, "error": f"账号目录已存在，不能覆盖：{profile_dir}"}

        entry = {
            "env_id": env_id,
            "label": label,
            "nickname": f"{label}（抖音/星图）",
            "profile": profile_name,
            "debug_port": port,
            "platforms": wanted,
            "proxy": None,
            "enabled": True,
            "visible": True,
        }
        raw.setdefault("platform_overrides", {})
        raw["environments"] = list(raw.get("environments") or []) + [entry]
        _write_registry(layout, raw)
        env_obj = environment_from_entry(entry)
        shortcut = (shortcut_maker or default_shortcut_maker)(layout, env_obj)
        result = {
            "ok": True,
            "env_id": env_id,
            "label": label,
            "debug_port": port,
            "platforms": wanted,
            "profile": str(profile_dir),
            "shortcut": shortcut,
            "message": f"账号「{label}」已创建，请在下方点「开始登录」扫码",
        }
        if shortcut.get("ok") is False:
            result["notice"] = "账号已创建，但桌面快捷方式刷新失败；可重新运行 bootstrap.bat 修复"
        return result
    except (ConfigError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        lock.release()


def disable_environment(layout, env_id, *, shortcut_maker=None,
                        lock_timeout=10.0) -> dict:
    layout.ensure()
    lock = _registry_lock(layout)
    if not lock.acquire(timeout=lock_timeout):
        return {"ok": False, "error": "账号配置正在被另一个操作占用，请稍后再试"}
    try:
        raw, envs = _read_registry(layout)
        target = next((e for e in envs if e.env_id == env_id), None)
        if target is None:
            return {"ok": False, "error": f"没有找到账号：{env_id}"}
        entries = raw.get("environments") or []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("env_id") == env_id:
                entry["enabled"] = False
                break
        _write_registry(layout, raw)
        _ = (shortcut_maker or default_shortcut_maker)(layout, target)
        return {"ok": True, "env_id": env_id, "label": target.label,
                "message": f"账号「{target.label}」已停用，历史数据保留"}
    except (ConfigError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        lock.release()


def delete_environment(layout, env_id, *, confirm=False, shortcut_maker=None,
                       lock_timeout=10.0) -> dict:
    if confirm is not True and str(confirm).lower() not in ("true", "1", "yes"):
        return {"ok": False, "error": "删除账号必须二次确认；请勾选确认后再删"}
    layout.ensure()
    lock = _registry_lock(layout)
    if not lock.acquire(timeout=lock_timeout):
        return {"ok": False, "error": "账号配置正在被另一个操作占用，请稍后再试"}
    try:
        raw, envs = _read_registry(layout)
        target = next((e for e in envs if e.env_id == env_id), None)
        if target is None:
            return {"ok": False, "error": f"没有找到账号：{env_id}"}
        if not target.visible:
            return {"ok": False, "error": "该平台本版未开通，不能在面板删除"}
        entries = [e for e in (raw.get("environments") or [])
                   if not (isinstance(e, dict) and e.get("env_id") == env_id)]
        raw["environments"] = entries
        moved = []
        stamp = time.strftime("%Y%m%d-%H%M%S")
        recycle = layout.data / "recycle" / f"{env_id}_{stamp}"
        recycle.mkdir(parents=True, exist_ok=True)
        profile_dir = layout.profiles / target.profile_name
        if profile_dir.exists():
            shutil.move(str(profile_dir), str(recycle / "profile"))
            moved.append(str(profile_dir))
        for rel in (f"{env_id}.launch.json", f"{env_id}.lease"):
            src = layout.env_lease_dir / rel
            if src.exists():
                run_recycle = recycle / "run"
                run_recycle.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(run_recycle / rel))
                moved.append(str(src))
        _write_registry(layout, raw)
        _ = (shortcut_maker or default_shortcut_maker)(layout, target)
        return {"ok": True, "env_id": env_id, "label": target.label,
                "recycle": str(recycle), "moved": moved,
                "message": f"账号「{target.label}」已删除，历史数据已移入回收站"}
    except (ConfigError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        lock.release()


def _next_env_id(envs) -> str:
    existing = {e.env_id for e in envs}
    index = 1
    while f"env_{index}" in existing:
        index += 1
    return f"env_{index}"
