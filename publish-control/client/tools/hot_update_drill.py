#!/usr/bin/env python3
"""Local end-to-end drill for the signed incremental updater.

No COS, no real customer machine.  Two throw-away client trees are built from
this source tree.  A local HTTP server plays the static COS endpoint, and a
small fake agent provides /healthz + the readiness marker.  The drill runs the
real updater CLI (download -> signature -> stage -> replace -> detached
supervisor -> restart -> self-check), then repeats with a deliberately broken
1.2.75 instance to prove automatic rollback and restart of 1.2.74.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "agent"), str(ROOT / "tools")]

from devsign import publickey, sign  # noqa: E402
from winport import updater  # noqa: E402

SEED = hashlib.sha256(b"hot-update-drill-key").digest()
PUBLIC = publickey(SEED)
FROM_VERSION = "1.2.74"
TO_VERSION = "1.2.75"
CHANGED = "agent/winport/__init__.py"
MARKER = "HOT_UPDATE_DRILL = \"1.2.75\"\n"


def log(message: str) -> None:
    print(message, flush=True)


def step(number: int, title: str, ok: bool = True, detail: str = "") -> None:
    log(f"[{number}] {'OK' if ok else 'FAIL'}  {title}" + (f"  ({detail})" if detail else ""))
    if not ok:
        raise SystemExit(1)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def build_manifest(program: Path, version: str) -> dict:
    files = {}
    for path in sorted(program.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.name == "MANIFEST.json" or path.name == "fake_agent.py":
            continue
        rel = path.relative_to(program).as_posix()
        files[rel] = {"sha256": updater.sha256_file(path), "bytes": path.stat().st_size}
    manifest = {"schema_version": "1.0", "version": version, "files": files}
    (program / "MANIFEST.json").write_text(json.dumps(manifest, indent=2),
                                            encoding="utf-8")
    return manifest


def copy_client(base: Path) -> Path:
    client = base / "client"
    shutil.copytree(ROOT / "agent", client / "agent",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "config", client / "config",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (client / "config" / "vendor_pubkey.hex").write_text(PUBLIC.hex() + "\n",
                                                         encoding="ascii")
    (client / "VERSION").write_text(FROM_VERSION + "\n", encoding="utf-8")
    shutil.copy2(ROOT / "tools" / "hot_update_fake_agent.py", client / "fake_agent.py")
    build_manifest(client, FROM_VERSION)
    data = base / "data"
    for sub in ("run", "logs", "config", "run/update"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    (data / "config" / "settings.json").write_text(json.dumps({
        "remote_channel": {"enabled": False},
        "updates": {
            "enabled": True,
            "check_interval_seconds": 3600,
            "health_timeout_seconds": 5,
            "tunnel_timeout_seconds": 5,
        },
    }, indent=2), encoding="utf-8")
    (base / "system").mkdir()
    return client


def make_patch(server_root: Path):
    original = (ROOT / CHANGED).read_bytes()
    new_bytes = original + MARKER.encode("utf-8")
    zip_path = server_root / f"patch-{TO_VERSION}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(CHANGED, new_bytes)
    body = {
        "schema": 1,
        "version": TO_VERSION,
        "min_version": FROM_VERSION,
        "files": [{"path": CHANGED, "sha256": sha(new_bytes),
                   "size": len(new_bytes), "mode": 0o644}],
        "patch_zip_url": "",
        "patch_zip_sha256": updater.sha256_file(zip_path),
        "notes": "local drill: one Python file",
    }
    return zip_path, body, new_bytes


def sign_manifest(body: dict) -> dict:
    value = dict(body)
    value["signature"] = sign(updater.manifest_payload(value), SEED, PUBLIC).hex()
    return value


def serve(server_root: Path, patch_zip: Path, body: dict):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(server_root), **kwargs)

        def log_message(self, *_args):
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    port = server.server_port
    body = dict(body)
    body["patch_zip_url"] = f"http://127.0.0.1:{port}/{patch_zip.name}"
    (server_root / "manifest.json").write_text(
        json.dumps(sign_manifest(body), ensure_ascii=False, indent=2),
        encoding="utf-8")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}/manifest.json"


def health(port: int):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def wait_health(port: int, version: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = health(port)
        if last and last.get("version") == version:
            return last
        time.sleep(0.1)
    raise RuntimeError(f"health did not become {version}: {last}")


def stop_process(proc) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def run_client(label: str, server_root: Path, manifest_url: str,
               patch_body: dict, fail_new: bool) -> dict:
    base = server_root / label
    base.mkdir()
    client = copy_client(base)
    data = base / "data"
    port = free_port()
    fail_file = base / "fail-new.txt"
    if fail_new:
        fail_file.write_text("fail 1.2.75\n", encoding="utf-8")
    stop_file = data / "run" / "stop-update-drill"
    fake = client / "fake_agent.py"
    command = [sys.executable, str(fake), "--data", str(data), "--port", str(port),
               "--fail-file", str(fail_file)]
    env = dict(os.environ)
    env.update({"PYTHONPATH": str(client / "agent"), "PYTHONDONTWRITEBYTECODE": "1",
                "WINPORT_PROGRAM": str(client), "WINPORT_DATA": str(data),
                "WINPORT_SYSTEM": str(base / "system")})
    old_proc = subprocess.Popen(command, cwd=str(client), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    restarted_pid = 0
    try:
        old_health = wait_health(port, FROM_VERSION)
        old_pid = old_health.get("pid")
        step(1, f"{label}: fake 1.2.74 agent is healthy", True, f"pid={old_pid}")

        cli = [sys.executable, "-B", "-m", "winport.updater", "perform",
               "--program", str(client), "--data", str(data),
               "--manifest-url", manifest_url,
               "--health-url", f"http://127.0.0.1:{port}/healthz",
               "--old-pid", str(old_pid),
               "--agent-command-json", json.dumps(command),
               "--stop-file", str(stop_file),
               "--allow-insecure-http", "--wait", "40"]
        result = subprocess.run(cli, cwd=str(client), env=env, capture_output=True,
                                text=True, timeout=90)
        if result.returncode != 0:
            log(result.stdout)
            log(result.stderr)
            raise RuntimeError(f"updater CLI failed rc={result.returncode}")
        status = updater.read_status(updater.Layout(program=client, data=data))
        step(2, f"{label}: updater returned", True, str(status.get("state")))

        want_state = "updated" if not fail_new else "rolled_back"
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            status = updater.read_status(updater.Layout(program=client, data=data))
            if status.get("state") == want_state:
                break
            time.sleep(0.25)
        step(3, f"{label}: status is {want_state}", status.get("state") == want_state,
             str(status.get("state")))

        version = (client / "VERSION").read_text(encoding="utf-8").strip()
        changed_text = (client / CHANGED).read_text(encoding="utf-8")
        if not fail_new:
            step(4, f"{label}: version is {TO_VERSION}", version == TO_VERSION, version)
            step(5, f"{label}: one-file patch applied", MARKER.strip() in changed_text)
            new_health = wait_health(port, TO_VERSION)
            restarted_pid = int(new_health.get("pid") or 0)
            step(6, f"{label}: new instance is healthy", True,
                 f"pid={new_health.get('pid')}, old={old_pid}")
            backup = data / "run" / "update" / f"backup-{FROM_VERSION}" / CHANGED
            step(7, f"{label}: old file was backed up", backup.is_file())
        else:
            step(4, f"{label}: version rolled back to {FROM_VERSION}", version == FROM_VERSION, version)
            step(5, f"{label}: file restored from backup", MARKER.strip() not in changed_text)
            new_health = wait_health(port, FROM_VERSION)
            restarted_pid = int(new_health.get("pid") or 0)
            step(6, f"{label}: old instance restarted automatically", True,
                 f"pid={new_health.get('pid')}, old={old_pid}")
        manifest = json.loads((client / "MANIFEST.json").read_text(encoding="utf-8"))
        if not fail_new:
            step(8, f"{label}: MANIFEST refreshed", manifest.get("version") == TO_VERSION,
                 str(manifest.get("version")))
            step(9, f"{label}: integrity re-check passed",
                 updater.verify_program(client).get("ok") is True)
        return {"status": status, "version": version, "health": new_health,
                "old_pid": old_pid}
    finally:
        stop_process(old_proc)
        if not restarted_pid:
            try:
                marker = json.loads((data / "run" / "agent-ready.json").read_text(encoding="utf-8"))
                restarted_pid = int(marker.get("pid") or 0)
            except Exception:
                restarted_pid = 0
        if restarted_pid and restarted_pid != old_proc.pid:
            try:
                os.kill(restarted_pid, 15)
            except OSError:
                pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="keep the temporary trees")
    args = parser.parse_args(argv)
    root = Path(tempfile.mkdtemp(prefix="hot-update-drill-"))
    server = None
    try:
        server_root = root / "server"
        server_root.mkdir()
        patch_zip, body, new_bytes = make_patch(server_root)
        server, manifest_url = serve(server_root, patch_zip, body)
        log(f"temporary client root: {root}")
        log("manifest URL: local HTTP loopback (COS stand-in)")
        success = run_client("success", server_root, manifest_url, body, False)
        step(10, "SUCCESS PATH: 1.2.74 -> 1.2.75, restarted, healthy",
             success["version"] == TO_VERSION and success["status"]["state"] == "updated")

        failed = run_client("rollback", server_root, manifest_url, body, True)
        step(11, "FAILURE PATH: broken 1.2.75 rolled back to a healthy 1.2.74",
             failed["version"] == FROM_VERSION
             and failed["status"]["state"] == "rolled_back")
        log("DRILL PASSED")
        return 0
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if args.keep:
            log(f"kept: {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
