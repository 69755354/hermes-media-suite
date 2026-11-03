#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 team.db 的片场状态转成 newme office 的任务文件（每 2 秒由服务端调用）。"""
import json, os, pathlib, sqlite3, sys, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = pathlib.Path(os.environ.get("TEAM_DB") or (ROOT / "state" / "team.db"))
OUT = pathlib.Path(os.environ.get("TASKS_OUT") or (ROOT / "office" / ".newme-office" / "tasks.json"))
ROLE = {"leader": "leader", "production": "production", "review": "review", "publish": "publish", "data": "data"}
FALLBACK = "production"

def main():
    con = sqlite3.connect(str(DB)); con.row_factory = sqlite3.Row
    tasks = []
    try:
        rows = con.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    except sqlite3.Error:
        rows = []
    for t in rows:
        stages = con.execute("SELECT * FROM stages WHERE task_id=? ORDER BY ord", (t["id"],)).fetchall()
        if not stages:
            continue
        cur = next((s for s in stages if s["status"] == "working"), None) \
              or next((s for s in stages if s["status"] == "blocked"), None) \
              or next((s for s in stages if s["status"] == "ready"), None)
        alldone = all(s["status"] == "done" for s in stages)
        if cur and cur["status"] == "working":
            status = "working"
        elif cur and cur["status"] == "blocked":
            status = "waiting"
        elif alldone:
            status = "done"
        elif cur:
            status = "idle"
        else:
            status = "idle"
        role = ROLE.get((cur or stages[0])["assignee"], FALLBACK)
        if role not in ROLE: role = FALLBACK
        NAME = {"TOPIC":"选题","COPY":"文案","STORYBOARD":"分镜","MEDIA":"生成","COMPOSE":"合成",
                "COMPLIANCE":"合规","PUBLISH":"发布","COLLECT":"取数","REVIEW":"复盘"}
        rn = {"leader":"团长","production":"视频组","review":"审核组","publish":"发布组","data":"数据组"}
        cur_stage = cur["stage_id"] if cur else stages[-1]["stage_id"]
        summary = f"当前：{NAME.get(cur_stage, cur_stage)} · 承接 {rn.get(role, role)}"
        if cur and cur["status"] == "blocked":
            summary += f'｜卡点：{cur["blocked_reason"]}｜下一处理者 {rn.get(cur["blocked_next"] or "leader","团长")}'
        calls = sum(s["used_calls"] for s in stages)
        summary += f"｜付费调用 {calls}/{t['budget_calls']}"
        tasks.append({
            "id": t["id"], "title": t["title"], "status": status,
            "project": t["batch"] or "未分批", "provider": t["account"] or "未指定",
            "roleHint": role, "activeRoles": [role],
            "summary": summary[:2000], "reply": "",
            "url": "", "turnId": f'{t["id"]}-{cur_stage}',
            "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "sample": False,
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"schemaVersion": 1, "tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, OUT)
    print(json.dumps({"tasks": len(tasks)}))

if __name__ == "__main__":
    main()
