#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""状态机与门禁：所有写操作都在这里，CLI/守护进程共用。"""
import json, os, hashlib, pathlib, time
from . import db

ROOT = pathlib.Path(__file__).resolve().parent.parent
PIPE = json.loads((ROOT / "pipeline.json").read_text(encoding="utf-8"))["stages"]
ROLES = json.loads((ROOT / "roles.json").read_text(encoding="utf-8"))
STAGE = {s["id"]: s for s in PIPE}
ORDER = [s["id"] for s in PIPE]

class Blocked(Exception):
    pass

def _stage(con, tid, sid):
    r = con.execute("SELECT * FROM stages WHERE task_id=? AND stage_id=?", (tid, sid)).fetchone()
    if not r:
        raise Blocked(f"没有这个阶段: {tid}/{sid}")
    return dict(r)

def _task(con, tid):
    r = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not r:
        raise Blocked(f"没有这条任务: {tid}")
    return dict(r)

def _done_set(con, tid):
    return {r["stage_id"] for r in con.execute(
        "SELECT stage_id FROM stages WHERE task_id=? AND status='done'", (tid,))}

def _needs_ok(con, tid, sid):
    return all(n in _done_set(con, tid) for n in STAGE[sid]["needs"])

def _refresh_ready(con, tid):
    """上游完成的阶段自动置 ready（不改已 working/blocked/done）"""
    done = _done_set(con, tid)
    for s in PIPE:
        if s["id"] in done:
            continue
        cur = _stage(con, tid, s["id"])
        if cur["status"] == "pending" and all(n in done for n in s["needs"]):
            con.execute("UPDATE stages SET status='ready', updated_at=? WHERE task_id=? AND stage_id=?",
                        (db.now(), tid, s["id"]))

def add_task(title, batch="-", account="-", budget_calls=60, tid=None):
    con = db.connect()
    n = con.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] + 1
    tid = tid or f"V{n:03d}"
    while con.execute("SELECT 1 FROM tasks WHERE id=?", (tid,)).fetchone():
        n += 1; tid = f"V{n:03d}"
    con.execute("INSERT INTO tasks(id,title,batch,account,budget_calls,status,created_at) VALUES(?,?,?,?,?,?,?)",
                (tid, title, batch, account, budget_calls, "open", db.now()))
    for i, s in enumerate(PIPE, 1):
        con.execute("""INSERT INTO stages(task_id,stage_id,ord,status,owner_role,assignee,
                       budget_calls,used_calls,attempts,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (tid, s["id"], i, "pending", s["owner"], s["owner"], 0, 0, 0, db.now()))
    con.execute("UPDATE stages SET status='ready' WHERE task_id=? AND stage_id=?", (tid, PIPE[0]["id"]))
    db.event(con, tid, PIPE[0]["id"], "task_created", "leader", title=title, budget=budget_calls)
    con.commit(); con.close()
    return tid

def _profile():
    """项目画像：把 skill/知识库/素材/硬口径固定进每份任务书。"""
    import os, json as _j
    cfg = _j.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    name = os.environ.get("TEAM_PROFILE") or cfg.get("profile")
    if not name:
        return None
    p = ROOT / "profiles" / f"{name}.json"
    if not p.exists():
        return None
    return _j.loads(p.read_text(encoding="utf-8"))


def brief(tid, sid=None):
    con = db.connect()
    t = _task(con, tid)
    sid = sid or con.execute("SELECT stage_id FROM stages WHERE task_id=? AND status IN ('ready','working','blocked') ORDER BY ord LIMIT 1", (tid,)).fetchone()["stage_id"]
    s = STAGE[sid]; st = _stage(con, tid, sid)
    ups = db.rows(con, "SELECT a.*, s2.stage_id FROM artifacts a JOIN stages s2 ON s2.task_id=a.task_id AND s2.stage_id=a.stage_id WHERE a.task_id=? AND a.stage_id IN ({}) ORDER BY a.id".format(",".join("?"*len(s["needs"]) or "''")), tuple([tid]+s["needs"])) if s["needs"] else []
    L = [f"# 任务书 {tid} · {s['name']}", "",
         f"- 片名：{t['title']}", f"- 批次：{t['batch']}   账号：{t['account']}",
         f"- 承接：{ROLES[s['owner']]['name']}（{ROLES[s['owner']]['who']}）" if st["assignee"] == s["owner"] else f"- 承接：{ROLES.get(st['assignee'],{}).get('name',st['assignee'])}",
         f"- 交付物：{s['artifact']}", ""]
    prof = _profile()
    if prof:
        L += ["## 项目上下文（开工前逐项读完，没读不许动手）",
              f"- 项目目录：{prof['project_dir']}",
              "- 必读 skill：", *[f"  - {x}" for x in prof.get("skills", [])],
              "- 知识库（事实来源，禁编造）：", *[f"  - {x}" for x in prof.get("knowledge", [])],
              f"- 素材根：{prof.get('assets','')}",
              "- 硬口径：", *[f"  {i}. {x}" for i, x in enumerate(prof.get("rules", []), 1)],
              ""]
    L += ["## 上游输入"]
    L += [f"- {STAGE[a['stage_id']]['name']}：{a['path']}（{a['note'] or ''}）" for a in ups] or ["- 无（起始阶段）"]
    L += ["", "## 验收标准（逐条可判定，缺一不可）"]
    L += [f"{i}. {x}" for i, x in enumerate(s.get("accept", []), 1)]
    L += ["", "## 流程约束",
          f"1. 本阶段只交付「{s['artifact']}」，不越界做下游的事",
          ("2. 本阶段允许付费生成，上限 %d 次，超出即停并挂 blocked" % (st["budget_calls"] or t["budget_calls"])) if s.get("paid") else "2. 本阶段禁止任何付费生成与对外发布动作",
          f"3. 产出物写到 {ROOT/'work'/tid/sid}，结尾一行 OUTPUT: <绝对路径>",
          "4. 缺信息输出 NEED_INFO（列待确认项，不阻塞交付），不合规输出 COMPLIANCE，做不了输出 BLOCKED 并写明原因与下一处理者",
          "5. 不要直接向用户汇报，结果交回团长", ""]
    extra = os.environ.get("TEAM_EXTRA", "").strip()
    if extra:
        L += ["## 本次追加要求（优先级高于上面的通用约束）", extra, ""]
    L += ["## 待确认项", "- 交付时列出；没有则写「无」", ""]
    con.close()
    return "\n".join(L)

def start(tid, sid, actor="leader", lease_seconds=900):
    con = db.connect(); t = _task(con, tid); s = STAGE[sid]; st = _stage(con, tid, sid)
    if st["status"] == "blocked":
        raise Blocked(f"有未解除卡点（{st['blocked_reason']}），先 unblock")
    if st["status"] != "ready":
        raise Blocked(f"{s['name']} 当前状态 {st['status']}，不能开工")
    if not _needs_ok(con, tid, sid):
        raise Blocked(f"上游未完成：{[n for n in s['needs'] if n not in _done_set(con,tid)]}")
    if st["assignee"] == "leader":
        raise Blocked("团长不参与生产，只负责指挥调度；先 assign 给执行单位")
    if s.get("paid") and st["used_calls"] <= 0:
        raise Blocked(f"{s['name']} 是付费阶段，先登记调用次数（calls --n N）再开工")
    _brief_gate(tid, sid)
    if sid == "PUBLISH" and not _approval_file(tid, sid).exists():
        raise Blocked("对外发布未放行：先 teamctl approve <id> PUBLISH（人工点头才行）")
    if sid == "COMPLIANCE" and st["assignee"] not in ("review",):
        raise Blocked("合规审核必须由审核组独立执行，不能派给视频组")
    busy = con.execute("SELECT stage_id FROM stages WHERE task_id=? AND status='working'", (tid,)).fetchone()
    if busy:
        raise Blocked(f"同一片子同时只能一个阶段在跑（当前 {busy['stage_id']}）")
    con.execute("""UPDATE stages SET status='working', started_at=?, heartbeat_at=?, lease_until=?,
                   attempts=attempts+1, updated_at=? WHERE task_id=? AND stage_id=?""",
                (db.now(), time.time(), time.time()+lease_seconds, db.now(), tid, sid))
    db.event(con, tid, sid, "started", actor, assignee=st["assignee"], attempt=st["attempts"]+1)
    con.commit(); con.close()

def heartbeat(tid, sid, lease_seconds=900):
    con = db.connect()
    con.execute("UPDATE stages SET heartbeat_at=?, lease_until=?, updated_at=? WHERE task_id=? AND stage_id=?",
                (time.time(), time.time()+lease_seconds, db.now(), tid, sid))
    con.commit(); con.close()

def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def done(tid, sid, artifact, note="", actor="leader"):
    con = db.connect(); s = STAGE[sid]; st = _stage(con, tid, sid); t = _task(con, tid)
    if st["status"] != "working":
        raise Blocked(f"{s['name']} 当前状态 {st['status']}，不能交工")
    if not artifact or not os.path.exists(artifact):
        raise Blocked(f"产出物不存在：{artifact}")
    if s.get("paid") and st["used_calls"] <= 0:
        raise Blocked(f"{s['name']} 是付费阶段，必须先登记调用次数（calls --n N）")
    if artifact and _sha(artifact) is None:
        raise Blocked("产出物读取失败")
    _accept_gate(tid, sid, artifact, note)
    con.execute("INSERT INTO artifacts(task_id,stage_id,path,sha256,size,note,created_at) VALUES(?,?,?,?,?,?,?)",
                (tid, sid, artifact, _sha(artifact), os.path.getsize(artifact), note, db.now()))
    con.execute("UPDATE stages SET status='done', finished_at=?, blocked_reason=NULL, blocked_next=NULL, updated_at=? WHERE task_id=? AND stage_id=?",
                (db.now(), db.now(), tid, sid))
    db.event(con, tid, sid, "done", actor, artifact=artifact, note=note, calls=st["used_calls"])
    _refresh_ready(con, tid)
    left = con.execute("SELECT COUNT(*) c FROM stages WHERE task_id=? AND status!='done'", (tid,)).fetchone()["c"]
    if left == 0:
        con.execute("UPDATE tasks SET status='closed', closed_at=? WHERE id=?", (db.now(), tid))
    con.commit()
    hp = ROOT / "handoffs" / f"{tid}_{sid}.md"; hp.parent.mkdir(exist_ok=True)
    nxt = [x for x in PIPE if sid in x.get("needs", [])]
    hp.write_text(f"# 交接单 {tid} · {s['name']}\n\n- 片名：{t['title']}\n- 完成：{db.now()}\n- 产出物：{artifact}\n- 说明：{note or '无'}\n\n## 下游\n" +
                  ("\n".join(f"- {x['name']}（{ROLES[x['owner']]['name']}）" for x in nxt) or "- 结束") + "\n", encoding="utf-8")
    con.close()
    return hp

def reject(tid, sid, reason, actor="leader"):
    con = db.connect(); st = _stage(con, tid, sid)
    if st["status"] not in ("working", "ready"):
        raise Blocked(f"当前状态 {st['status']}，不能退单")
    con.execute("UPDATE stages SET status='ready', assignee='leader', blocked_reason=?, updated_at=? WHERE task_id=? AND stage_id=?",
                (f"退单：{reason}", db.now(), tid, sid))
    db.event(con, tid, sid, "rejected", actor, reason=reason, kept_artifacts=True)
    con.commit(); con.close()

def assign(tid, sid, to, reason, actor="leader"):
    con = db.connect(); st = _stage(con, tid, sid)
    if to not in ROLES or to == "leader":
        raise Blocked(f"只能派给执行单位：{[k for k in ROLES if k!='leader']}")
    if st["status"] in ("done",):
        raise Blocked("阶段已完成，不能改派")
    old = st["assignee"]
    con.execute("UPDATE stages SET assignee=?, status='ready', blocked_reason=NULL, blocked_next=NULL, updated_at=? WHERE task_id=? AND stage_id=?",
                (to, db.now(), tid, sid))
    db.event(con, tid, sid, "assigned", actor, frm=old, to=to, reason=reason)
    con.commit(); con.close()

def block(tid, sid, reason, next_handler="leader", actor="leader"):
    con = db.connect(); st = _stage(con, tid, sid)
    if st["status"] in ("done",):
        raise Blocked("已完成，不能挂起")
    con.execute("UPDATE stages SET status='blocked', blocked_reason=?, blocked_next=?, updated_at=? WHERE task_id=? AND stage_id=?",
                (reason, next_handler, db.now(), tid, sid))
    db.event(con, tid, sid, "blocked", actor, reason=reason, next=next_handler)
    con.commit(); con.close()

def unblock(tid, sid, actor="leader"):
    con = db.connect(); st = _stage(con, tid, sid)
    if st["status"] != "blocked":
        raise Blocked(f"当前没有卡点（{st['status']}）")
    why = st["blocked_reason"]
    con.execute("UPDATE stages SET status='ready', blocked_reason=NULL, blocked_next=NULL, updated_at=? WHERE task_id=? AND stage_id=?",
                (db.now(), tid, sid))
    db.event(con, tid, sid, "unblocked", actor, reason=why)
    con.commit(); con.close()

def add_calls(tid, sid, n, note="", actor="leader"):
    con = db.connect(); st = _stage(con, tid, sid); t = _task(con, tid)
    cap = st["budget_calls"] or t["budget_calls"]
    if st["used_calls"] + n > cap:
        raise Blocked(f"超出预算上限 {cap}（已用 {st['used_calls']}，本次 {n}）")
    con.execute("INSERT INTO calls(ts,task_id,stage_id,n,note) VALUES(?,?,?,?,?)", (db.now(), tid, sid, n, note))
    con.execute("UPDATE stages SET used_calls=used_calls+?, updated_at=? WHERE task_id=? AND stage_id=?",
                (n, db.now(), tid, sid))
    db.event(con, tid, sid, "calls", actor, n=n, total=st["used_calls"]+n, note=note)
    con.commit(); con.close()

def expire_leases(lease_check=True):
    if not lease_check:
        return []
    con = db.connect(); out = []
    for r in con.execute("SELECT * FROM stages WHERE status='working' AND lease_until IS NOT NULL AND lease_until < ?", (time.time(),)):
        con.execute("UPDATE stages SET status='blocked', blocked_reason=?, blocked_next='leader', updated_at=? WHERE task_id=? AND stage_id=?",
                    ("心跳超时（租约到期）", db.now(), r["task_id"], r["stage_id"]))
        db.event(con, r["task_id"], r["stage_id"], "lease_expired", "daemon")
        out.append((r["task_id"], r["stage_id"]))
    con.commit(); con.close()
    return out

def status(tid=None):
    con = db.connect()
    if tid:
        t = _task(con, tid)
        sts = db.rows(con, "SELECT * FROM stages WHERE task_id=? ORDER BY ord", (tid,))
        arts = db.rows(con, "SELECT * FROM artifacts WHERE task_id=? ORDER BY id", (tid,))
        con.close()
        return {"task": t, "stages": sts, "artifacts": arts}
    tasks = db.rows(con, "SELECT * FROM tasks ORDER BY created_at DESC")
    board = []
    for t in tasks:
        cur = db.rows(con, "SELECT * FROM stages WHERE task_id=? AND status IN ('working','blocked','ready') ORDER BY ord LIMIT 1", (t["id"],))
        board.append({"task": t, "current": cur[0] if cur else None})
    con.close()
    return board

def next_ready():
    """列出所有上游已完成、可开工的阶段"""
    con = db.connect()
    out = []
    for r in db.rows(con, """SELECT s.*, t.title FROM stages s JOIN tasks t ON t.id=s.task_id
                             WHERE s.status='ready' AND s.assignee!='leader' ORDER BY s.task_id, s.ord"""):
        done = _done_set(con, r["task_id"])
        if all(n in done for n in STAGE[r["stage_id"]]["needs"]):
            out.append(r)
    con.close()
    return out

def record_brief(tid, sid, text):
    """任务书登记：把 sha256 写进 events，开工时校验，防拿旧文件充数。"""
    con = db.connect()
    db.event(con, tid, sid, "brief", "leader", sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
    con.commit(); con.close()


def _brief_gate(tid, sid):
    """任务书物理闸：没编译出本次任务书不许开工。"""
    bp = ROOT / "briefs" / f"{tid}_{sid}.md"
    if not bp.exists():
        raise Blocked(f"没有任务书 {bp.name}，先 brief 再开工")
    txt = bp.read_text(encoding="utf-8", errors="ignore")
    for k in ("## 验收标准", "## 流程约束"):
        if k not in txt:
            raise Blocked(f"任务书缺「{k}」，重新编译 brief")
    con = db.connect()
    r = con.execute("SELECT payload FROM events WHERE task_id=? AND stage_id=? AND kind='brief' ORDER BY id DESC LIMIT 1",
                    (tid, sid)).fetchone()
    con.close()
    if not r:
        raise Blocked("任务书没有登记（走 teamctl brief/dispatch 生成），不许开工")
    import json as _j
    try:
        want = _j.loads(r["payload"]).get("sha256")
    except Exception:
        want = None
    got = hashlib.sha256(txt.encode("utf-8")).hexdigest()
    if want != got:
        raise Blocked("任务书文件与登记不一致（被改过或不是本次生成），重新 brief")


def _accept_gate(tid, sid, artifact, note):
    """验收物理闸：每阶段的交付物必须能被程序判定，不靠嘴。"""
    txt = ""
    try:
        txt = pathlib.Path(artifact).read_text(encoding="utf-8", errors="ignore")[:200000]
    except Exception:
        txt = ""
    up = (txt + "\n" + (note or "")).upper()
    if sid == "COMPLIANCE":
        if "VERDICT: PASS" not in up:
            raise Blocked("审核未通过：产出物没有 VERDICT: PASS，不能进入发布")
    elif sid == "PUBLISH":
        if "CONFIRMED" not in up:
            raise Blocked("发布没有回读确认：note 或产出物必须含 CONFIRMED，否则按未发布处理")
    elif sid == "COLLECT":
        if not artifact.lower().endswith((".xlsx", ".csv")):
            raise Blocked("取数产出物必须是表格（.xlsx/.csv）")


def _approval_file(tid, sid):
    """放行文件按台账隔离，避免测试库/生产库互相串。"""
    dbp = os.environ.get("TEAM_DB") or str(ROOT / CFG.get("db", "state/team.db"))
    key = hashlib.sha1(dbp.encode()).hexdigest()[:8]
    d = ROOT / "approvals" / key
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sid}_{tid}.ok"


def approve(tid, sid, who="human", note=""):
    """人工放行：一次点头放行该片该阶段。"""
    con = db.connect()
    _task(con, tid); _stage(con, tid, sid)
    f = _approval_file(tid, sid)
    f.write_text(f"{who} {db.now()} {note}\n", encoding="utf-8")
    db.event(con, tid, sid, "approved", who, note=note, file=str(f))
    con.commit(); con.close()
    return f
