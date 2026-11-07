"""Desktop launcher: make sure the agent is up, then open the local panel.

PowerShell-free by design (360 blocks powershell.exe on some customer
machines).  Runs on the data-area virtualenv, because that is where the
runtime dependencies (playwright/psutil/pystray) are installed - the bundled
runtime python has none of them.

Behaviour:
  1. /healthz 200, instance == readiness marker, version == VERSION
     -> just open the panel.
  2. stale agent (old version)                     -> stop the process that
     owns port 9223, then start the supervisor.
  3. start the supervisor, wait for readiness, open the browser.
Every outcome is written to <data>/logs/launcher.log; the exit code is non-zero
when the panel never became ready.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if os.path.join(HERE, "agent") not in sys.path:
    sys.path.insert(0, os.path.join(HERE, "agent"))

from winport.port_owner import ownership as _ownership  # noqa: E402
from winport.port_owner import process_cmdline as _process_cmdline  # noqa: E402
from winport.subprocess_text import hidden_window_options, text_mode_options  # noqa: E402

LOCALAPPDATA = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
DATA = os.path.join(LOCALAPPDATA, "HuolongAgent", "publish-worker")
URL = "http://127.0.0.1:9223/"
HEALTH = URL + "healthz"
LOG = os.path.join(DATA, "logs", "launcher.log")
MARKER = os.path.join(DATA, "run", "agent-ready.json")
SUPERVISOR = os.path.join(HERE, "scripts", "run-agent-task.vbs")
STOP_TIMEOUT_SECONDS = 10.0
STOP_POLL_SECONDS = 0.5
READY_TIMEOUT_SECONDS = 60


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def notify(msg):
    """Show a native dialog so a silent pythonw failure is never invisible."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg[:12000], "\u6f2b\u5267\u53d1\u5e03\u52a9\u624b", 0x10)
    except Exception:
        pass


def expected_version():
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8-sig") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def health():
    try:
        with urllib.request.urlopen(HEALTH, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def ready_marker():
    """Read the agent readiness marker, or None when it is absent/invalid."""
    try:
        with open(MARKER, encoding="utf-8-sig") as fh:
            value = json.load(fh)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def health_matches_marker(state, marker):
    """Bind an already-running panel to its pid/marker before trusting it."""
    if not isinstance(state, dict) or not isinstance(marker, dict):
        return False
    token = marker.get("instance")
    # The updater-supervised launch keeps the supervisor-visible pid in
    # "pid" and the process that really owns 9223 in "agent_pid".
    pid = marker.get("agent_pid") or marker.get("pid")
    if not token or marker.get("ready") is not True or not isinstance(pid, int):
        return False
    if state.get("instance") != token or pid_on_9223() != pid:
        return False
    try:
        import psutil
        image = _norm_path(psutil.Process(pid).exe())
        if not pid_is_ours(pid):
            return False
        for root in (HERE, DATA):
            try:
                if os.path.commonpath([image, _norm_path(root)]) == _norm_path(root):
                    return True
            except ValueError:  # program and data may be on different drives
                continue
        return False
    except Exception:
        return False


def _process_alive(pid):
    """Best-effort liveness check; uncertain results count as alive."""
    try:
        import psutil  # type: ignore
        return bool(psutil.pid_exists(int(pid)))
    except ImportError:
        pass
    except Exception:
        return True
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "PID eq %d" % int(pid), "/NH"],
                capture_output=True, timeout=15,
                **hidden_window_options(["tasklist"]),
                **text_mode_options())
        except (OSError, subprocess.SubprocessError):
            return True
        if result.returncode != 0:
            return True
        return str(int(pid)) in (result.stdout or "").split()
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    except Exception:
        return True
    return True


def wait_for_release(pid, *, timeout=None, poll=None):
    """Poll until ``pid`` is gone AND port 9223 has no listener."""
    if timeout is None:
        timeout = STOP_TIMEOUT_SECONDS
    if poll is None:
        poll = STOP_POLL_SECONDS
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        owner = pid_on_9223()
        alive = _process_alive(pid)
        if owner is None and not alive:
            return True, owner, alive
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False, owner, alive
        time.sleep(min(max(0.01, float(poll)), remaining))


def pid_is_ours(pid):
    owned, reason = _ownership(pid, DATA)
    if not owned:
        log("port 9223 pid=%s ownership refused: %s" % (pid, reason))
    return owned


def pid_on_9223():
    """Return the PID listening on 9223, or None.  netstat only - no WMI."""
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True,
                             timeout=15,
                             **hidden_window_options(["netstat", "-ano"]),
                             **text_mode_options())
        if result.returncode != 0:
            raise RuntimeError("port inventory failed")
        out = result.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        if os.name != "nt":
            return None
        raise RuntimeError("port inventory unavailable") from exc
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper().startswith("TCP") \
                and parts[1].endswith(":9223") and parts[3].upper() == "LISTENING":
            try:
                return int(parts[4])
            except ValueError as exc:
                raise RuntimeError("invalid listener PID") from exc
    return None


def stop_pid(pid, verify=True):
    # verify=False is used only when the caller already proved ownership from
    # the /healthz payload (legacy install living outside product folders).
    if verify and not pid_is_ours(pid):
        return False
    if not verify:
        live = health()
        health_ok = bool(live) and str(live.get("app", "")).lower() == "winport"
        cmd = " ".join(_process_cmdline(pid) or []).lower()
        # A plain string in /healthz is not enough on its own; accept the kill
        # only for a winport process whose own path names this product.
        product_ok = "winport" in cmd and (
            "manju-publish-assistant" in cmd or "huolongagent" in cmd)
        # A hung legacy agent may answer nothing at all; the path proof still
        # stands then. But if the port does answer and it is NOT winport, the
        # port was hijacked -- never kill on path evidence alone.
        if not (product_ok and (health_ok or live is None)):
            log("refusing to kill pid=%s: health_ok=%s product_ok=%s"
                % (pid, health_ok, product_ok))
            return False
    if pid_on_9223() != pid:
        log("refusing to kill pid=%s: it no longer owns 9223" % pid)
        return False
    try:
        res = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                             timeout=20,
                             **hidden_window_options(["taskkill", "/PID", str(pid), "/F"]))
        log("taskkill pid=%s rc=%s" % (pid, res.returncode))
    except (OSError, subprocess.SubprocessError) as exc:
        log("taskkill failed: %s" % exc)
        return False
    released, owner, alive = wait_for_release(pid)
    if not released:
        log("pid %s did not release port 9223: alive=%s port_owner=%s"
            % (pid, alive, owner))
        return False
    log("stopped pid=%s; port 9223 released" % pid)
    return True


def spawn(instance_token=None):
    """Start the supervisor, never the agent directly.

    The supervisor owns the resident-agent lifetime and restarts it after a
    crash.  This panel process only waits for the readiness marker and opens
    the browser, so closing the panel cannot orphan the agent.
    """
    if not os.path.isfile(SUPERVISOR):
        log("supervisor missing: %s - reinstall required" % SUPERVISOR)
        raise RuntimeError("supervisor missing: %s" % SUPERVISOR)
    try:
        args = ["wscript.exe", "//nologo", SUPERVISOR]
        proc = subprocess.Popen(
            args, cwd=HERE, close_fds=True,
            **hidden_window_options(
                args, popen=True,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)))
        log("started supervisor pid=%s" % proc.pid)
        return proc
    except OSError as exc:
        reason = "supervisor start failed: %s (script=%s, cwd=%s)" % (exc, SUPERVISOR, HERE)
        log(reason)
        raise RuntimeError(reason) from exc


def _norm_path(value):
    try:
        return os.path.normcase(os.path.realpath(str(value)))
    except OSError:
        return os.path.normcase(os.path.abspath(str(value)))


def supervisor_processes():
    """Return ``(pid, script_path)`` for every wscript running a supervisor."""
    found = []
    try:
        import psutil  # type: ignore
    except Exception as exc:
        raise RuntimeError("supervisor inventory unavailable") from exc
    try:
        iterator = psutil.process_iter()
    except Exception as exc:
        raise RuntimeError("supervisor inventory unavailable") from exc
    for proc in iterator:
        try:
            name = str(proc.name() or "").lower()
            if not name:
                raise RuntimeError("process name unreadable")
            if name not in ("wscript.exe", "cscript.exe"):
                continue
            info = {"pid": proc.pid, "cmdline": proc.cmdline()}
            if not info.get("cmdline"):
                raise RuntimeError("script process command line unreadable")
            argv = [str(item) for item in info["cmdline"]]
            scripts = [item for item in argv
                       if item.lower().endswith("run-agent-task.vbs")]
            if scripts:
                found.append((int(info.get("pid") or 0), scripts[0]))
        except psutil.NoSuchProcess:
            continue
    return found


def current_supervisor_pids():
    target = _norm_path(SUPERVISOR)
    found = supervisor_processes()
    try:
        from scripts.bootstrap_py import read_owner_text
        owner = json.loads(read_owner_text(
            os.path.join(DATA, "run", "supervisor.lock", "owner.txt"), log))
        pid = int(owner["pid"])
        if (pid <= 0 or owner.get("version") != expected_version()
                or _norm_path(owner["program"]) != _norm_path(HERE)
                or (pid, target) not in [(p, _norm_path(script)) for p, script in found]):
            return []
        return [pid]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def stop_foreign_supervisors(include_current=False):
    """Stop foreign or unverified same-path owners before spawning a replacement."""
    target = _norm_path(SUPERVISOR)
    keep_pids = set(current_supervisor_pids()) if not include_current else set()
    stopped = 0
    for pid, script in supervisor_processes():
        if pid <= 0:
            continue
        if _norm_path(script) == target and pid in keep_pids:
            continue
        log("stopping supervisor pid=%s script=%s" % (pid, script))
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, timeout=15,
                           **hidden_window_options(
                               ["taskkill", "/PID", str(pid), "/F"]))
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and _process_alive(pid):
                time.sleep(0.2)
            if _process_alive(pid):
                raise RuntimeError("supervisor pid=%s did not exit after taskkill" % pid)
            else:
                stopped += 1
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("supervisor stop failed pid=%s: %s" % (pid, exc)) from exc
    return stopped


def supervisor_failure_reason():
    from scripts.bootstrap_py import supervisor_diagnostics
    return ("Supervisor takeover failed: expected version=%s.\n%s" %
            (expected_version(), supervisor_diagnostics(DATA)))


def open_browser():
    try:
        import webbrowser
        webbrowser.open(URL)
    except Exception as exc:  # noqa: BLE001
        log("browser open failed: %s" % exc)


def _auto_activate():
    """First launch after install: redeem the package token if still unlicensed."""
    try:
        from winport.activation import activate
        from winport.paths import Layout
        result = activate(Layout(program=HERE, data=DATA).ensure())
        log("auto activation: %s" % (result.get("reason") or result))
    except Exception as exc:  # never block the panel
        log("auto activation skipped: %s" % exc)


def main():
    _auto_activate()
    # Customers look on the desktop, not in %LOCALAPPDATA%: keep a drop folder
    # there and let the media resolver read it (1.2.142).
    def _desktop_folder():
        try:
            from winport import desktop as _desktop
            _desktop.ensure(DATA, log)
        except Exception as exc:
            log("desktop materials folder skipped: %s" % exc)

    try:
        import threading as _threading
        _folder_thread = _threading.Thread(target=_desktop_folder,
                                           name="desktop-folder", daemon=True)
        _folder_thread.start()
        _folder_thread.join(5.0)
    except Exception as exc:
        log("desktop materials folder thread skipped: %s" % exc)
    want = expected_version()
    state = health()
    marker = ready_marker()
    if state and want and state.get("version") == want \
            and health_matches_marker(state, marker):
        log("agent already running version=%s" % state.get("version"))
        stop_foreign_supervisors()  # retain verified owner; stop only extras
        if not current_supervisor_pids():
            # A healthy agent with no supervisor is one crash away from a dead
            # panel.  Take over without blocking the browser: stop any old
            # supervisor and let the current one adopt the live agent.
            stop_foreign_supervisors()
            spawn()
            deadline = time.monotonic() + READY_TIMEOUT_SECONDS
            while not current_supervisor_pids():
                if time.monotonic() >= deadline:
                    raise RuntimeError(supervisor_failure_reason())
                time.sleep(0.5)
        open_browser()
        return 0
    if state or pid_on_9223():
        # A hung legacy agent answers nothing, so ``state`` alone is not a
        # trustworthy signal that the port is free.
        log("stale or unbound agent version=%s expected=%s instance=%s"
            % ((state or {}).get("version"), want, (state or {}).get("instance")))
        stop_foreign_supervisors(include_current=True)
        # A legacy install may be watched by its own supervisor, which can
        # relaunch it the moment we kill it.  Stop the port owner up to three
        # times, then decide from the port itself -- never from one kill's
        # return value, which is false when a relaunch raced us.
        for attempt in range(3):
            pid = pid_on_9223()
            if not pid:
                break
            owned = pid_is_ours(pid)
            if not owned:
                log("legacy winport on 9223 pid=%s health=%s; stopping it"
                    % (pid, state))
            if not stop_pid(pid, verify=owned):
                log("could not stop pid=%s attempt=%s" % (pid, attempt))
            time.sleep(0.5)
        stopped = pid_on_9223() is None
        if not stopped:
            notify("\u65e7\u7248\u672c\u505c\u4e0d\u4e0b\u6765\u3002"
                   "\u8bf7\u91cd\u542f\u7535\u8111\u540e\u518d\u8bd5\u3002")
            return 7
    stop_foreign_supervisors()
    spawn()
    for _ in range(READY_TIMEOUT_SECONDS):
        time.sleep(1)
        state = health()
        marker = ready_marker()
        if state and want and state.get("version") == want \
                and health_matches_marker(state, marker) and current_supervisor_pids():
            log("ready version=%s instance=%s"
                % (state.get("version"), state.get("instance")))
            open_browser()
            return 0
    reason = ("Agent not ready: expected version=%s, health version=%s, marker matches=%s. %s"
              % (want, (state or {}).get("version"),
                 health_matches_marker(state, marker) if state else False,
                 supervisor_failure_reason()))
    log(reason)
    notify(reason)
    notify("\u7a0b\u5e8f\u6ca1\u6709\u542f\u52a8\u8d77\u6765\u3002\u8bf7\u628a\u684c\u9762\u4e0a\u7684 install-log.txt \u53d1\u7ed9\u670d\u52a1\u5546\u3002")
    return 4


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001 - pythonw must never fail invisibly
        log("unexpected failure: %s: %s" % (type(exc).__name__, exc))
        notify("Startup failed: %s" % exc)
        notify("\u7a0b\u5e8f\u542f\u52a8\u5931\u8d25\u3002"
               "\u8bf7\u628a\u684c\u9762\u4e0a\u7684 install-log.txt \u53d1\u7ed9\u670d\u52a1\u5546\u3002")
        code = 8
    sys.exit(code)
