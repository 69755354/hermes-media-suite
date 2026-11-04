"""Minimal fake agent used only by tools/hot_update_drill.py.

It has no product logic.  It exists to prove the updater restarts the same
command on the same data directory and that healthz/readiness are re-checked.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "agent"))

from winport.lock import FileLock  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fail-file", default="")
    args = parser.parse_args(argv)
    data = Path(args.data)
    (data / "run").mkdir(parents=True, exist_ok=True)
    (data / "logs").mkdir(parents=True, exist_ok=True)
    version = (ROOT / "VERSION").read_text(encoding="utf-8-sig").strip()
    instance = os.urandom(16).hex()
    fail_file = Path(args.fail_file) if args.fail_file else None
    failing = bool(fail_file and fail_file.exists() and version == "1.2.75")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def do_GET(self):
            if self.path != "/healthz":
                self.send_error(404)
                return
            if failing:
                body = b'{"ok": false, "error": "simulated broken update"}'
                self.send_response(503)
            else:
                body = json.dumps({"ok": True, "app": "winport", "version": version,
                                   "instance": instance, "pid": os.getpid()}).encode("utf-8")
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    marker = data / "run" / "agent-ready.json"
    marker.write_text(json.dumps({
        "pid": os.getpid(), "ready": True,
        "panel_url": f"http://127.0.0.1:{args.port}/",
        "instance": instance, "version": version, "ts": time.time(),
    }), encoding="utf-8")
    lock = FileLock(data / "run" / "agent.lock")
    lock.acquire()
    stop = threading.Event()

    def _stop(*_args):
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    try:
        signal.signal(signal.SIGINT, _stop)
    except (ValueError, OSError):
        pass
    stop_file = data / "run" / "stop-update-drill"
    try:
        with (data / "logs" / "fake-agent.log").open("a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%F %T')} started version={version} "
                      f"pid={os.getpid()} port={args.port} failing={failing}\n")
        while not stop.is_set():
            if stop_file.exists():
                break
            time.sleep(0.1)
    finally:
        server.shutdown()
        server.server_close()
        lock.release()
        marker.unlink(missing_ok=True)
        stop_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
