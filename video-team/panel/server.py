#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读看板服务：读 team.db，不改任何状态。"""
import json, os, pathlib, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from teamd import db

PIPE = json.loads((pathlib.Path(__file__).resolve().parent.parent / "pipeline.json").read_text(encoding="utf-8"))
STAGES = {s["id"]: s for s in PIPE["stages"]}
ROLES = json.loads((pathlib.Path(__file__).resolve().parent.parent / "roles.json").read_text(encoding="utf-8"))
HTML = (pathlib.Path(__file__).resolve().parent / "index.html").read_bytes()

def board():
    con = db.connect()
    tasks = db.rows(con, "SELECT * FROM tasks ORDER BY created_at DESC")
    out = []
    for t in tasks:
        st = db.rows(con, "SELECT * FROM stages WHERE task_id=? ORDER BY ord", (t["id"],))
        arts = db.rows(con, "SELECT stage_id, path, size FROM artifacts WHERE task_id=?", (t["id"],))
        ev = db.rows(con, "SELECT ts, stage_id, kind, actor, payload FROM events WHERE task_id=? ORDER BY id DESC LIMIT 12", (t["id"],))
        out.append({"task": t, "stages": [dict(s, name=STAGES[s["stage_id"]]["name"], role=ROLES.get(s["assignee"], {}).get("name", s["assignee"])) for s in st],
                    "artifacts": arts, "events": [dict(e) for e in ev]})
    ev_all = db.rows(con, "SELECT ts, task_id, stage_id, kind, payload FROM events ORDER BY id DESC LIMIT 30")
    con.close()
    return {"tasks": out, "events": [dict(e) for e in ev_all], "roles": ROLES,
            "stages": [s["id"] for s in PIPE["stages"]], "stage_names": {s["id"]: s["name"] for s in PIPE["stages"]}}

TOKEN = os.environ.get("PANEL_TOKEN", "")

class H(BaseHTTPRequestHandler):
    def _authed(self):
        if not TOKEN:
            return True
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if q.get("k", [""])[0] == TOKEN:
            self.send_response(302)
            self.send_header("Set-Cookie", f"team_token={TOKEN}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
            loc = u.path if u.path not in ("", "/") else "./"
            self.send_header("Location", loc)
            self.end_headers()
            return False
        ck = self.headers.get("Cookie", "")
        return f"team_token={TOKEN}" in ck

    def do_GET(self):
        if not self._authed():
            if TOKEN and not urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("k"):
                self.send_response(401); self.end_headers(); self.wfile.write("需要访问口令".encode()); return
            return
        if self.path.startswith("/api/board"):
            b = json.dumps(board(), ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if self.path in ("", "/", "/index.html"):
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(HTML))); self.end_headers(); self.wfile.write(HTML); return
        self.send_response(404); self.end_headers()
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(os.environ.get("PANEL_PORT", "8899"))
    HTTPServer(("127.0.0.1", port), H).serve_forever()
