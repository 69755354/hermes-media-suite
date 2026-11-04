#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""video_team: 片级任务看板 + 阶段交接 + 门禁。一个片子一条记录走到底。"""
import json, os, sys, time, argparse, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
# 1.2.177: data (board/briefs/handoffs) must be redirectable so tests never
# rewrite tracked files inside the repository.
DATA_ROOT = pathlib.Path(os.environ.get("TEAM_DATA") or ROOT)
BOARD = DATA_ROOT / "board.json"
PIPE = json.loads((ROOT / "pipeline.json").read_text(encoding="utf-8"))["stages"]
ROLES = json.loads((ROOT / "roles.json").read_text(encoding="utf-8"))
STAGE = {s["id"]: s for s in PIPE}
HANDOFF = DATA_ROOT / "handoffs"
HANDOFF.mkdir(exist_ok=True)

def load():
    if BOARD.exists():
        return json.loads(BOARD.read_text(encoding="utf-8"))
    return {"seq": 0, "tasks": []}

def save(b):
    BOARD.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")

def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def find(b, tid):
    for t in b["tasks"]:
        if t["id"] == tid:
            return t
    raise SystemExit(f"没有这条任务: {tid}")

def unlocked(t):
    """当前阶段能否开工：所有 needs 阶段的 done 都必须存在"""
    st = STAGE[t["stage"]]
    done = {h["stage"] for h in t["history"] if h["result"] == "done"}
    return all(n in done for n in st["needs"])

def cmd_add(a):
    b = load(); b["seq"] += 1
    tid = f"V{b['seq']:03d}"
    t = {"id": tid, "title": a.title, "batch": a.batch, "account": a.account,
         "stage": PIPE[0]["id"], "status": "ready", "owner": PIPE[0]["owner"],
         "history": [], "created": now(), "calls": 0, "budget": a.budget, "blocked": None}
    b["tasks"].append(t); save(b)
    print(f"{tid} 已建：{a.title}｜当前阶段 {PIPE[0]['name']}｜负责 {ROLES[PIPE[0]['owner']]['name']}")

def cmd_list(a):
    b = load()
    if not b["tasks"]:
        print("看板是空的"); return
    print(f"{'ID':<6}{'阶段':<8}{'状态':<9}{'负责':<7}{'片名'}")
    for t in b["tasks"]:
        st = STAGE[t["stage"]]
        print(f"{t['id']:<6}{st['name']:<8}{t['status']:<9}{ROLES[st['owner']]['name']:<7}{t['title']}")

def cmd_show(a):
    b = load(); t = find(b, a.id); st = STAGE[t["stage"]]
    print(f"{t['id']} {t['title']}")
    print(f"批次 {t.get('batch')}  账号 {t.get('account')}")
    print(f"当前 {st['name']}（{st['id']}）｜负责 {ROLES[st['owner']]['name']}｜状态 {t['status']}")
    print(f"可开工: {'是' if unlocked(t) else '否，上游未完成'}")
    print(f"付费调用: {t.get('calls',0)}/{t.get('budget',0)}")
    if t.get("blocked"):
        print(f"卡点: {t['blocked']['reason']}｜下一处理者 {t['blocked'].get('next','-')}")
    for h in t["history"]:
        print(f"  - {h['at']} {STAGE[h['stage']]['name']} {h['result']} {h.get('artifact','')} {h.get('note','')}")

def cmd_start(a):
    b = load(); t = find(b, a.id); st = STAGE[t["stage"]]
    if t.get("blocked"):
        raise SystemExit(f"BLOCKED: 有未解除的卡点（{t['blocked']['reason']}），先 team.py unblock {t['id']}")
    if st["owner"] == "leader":
        raise SystemExit("BLOCKED: 团长不参与生产，只负责指挥调度")
    if not unlocked(t):
        need = [n for n in st["needs"] if n not in {h["stage"] for h in t["history"] if h["result"]=="done"}]
        raise SystemExit(f"BLOCKED: 上游未完成 {need}")
    if t["status"] == "working":
        raise SystemExit("已经在做了")
    t["status"] = "working"; t["owner"] = st["owner"]; t["started"] = now()
    save(b); print(f"{t['id']} 开工：{st['name']}｜{ROLES[st['owner']]['name']}")

def cmd_done(a):
    b = load(); t = find(b, a.id); st = STAGE[t["stage"]]
    if st["owner"] == "leader" and st["id"] != "REVIEW":
        raise SystemExit("BLOCKED: 团长不参与生产，只负责指挥调度")
    art = a.artifact or ""
    if st["id"] != "REVIEW" and not art:
        raise SystemExit(f"BLOCKED: {st['name']} 必须交产出物路径（--artifact）")
    if art and not os.path.exists(art):
        raise SystemExit(f"BLOCKED: 产出物不存在 {art}")
    if st.get("paid") and t.get("calls", 0) <= 0:
        raise SystemExit(f"BLOCKED: {st['name']} 是付费阶段，必须先登记调用次数（team.py calls {t['id']} --n N）")
    t["history"].append({"stage": st["id"], "result": "done", "at": now(),
                         "artifact": art, "note": a.note or "", "by": st["owner"]})
    idx = [s["id"] for s in PIPE].index(st["id"])
    nxt = PIPE[idx+1] if idx+1 < len(PIPE) else None
    if nxt:
        t["stage"] = nxt["id"]; t["owner"] = nxt["owner"]; t["status"] = "ready"
    else:
        t["status"] = "closed"
    t["blocked"] = None
    save(b)
    hp = HANDOFF / f"{t['id']}_{st['id']}.md"
    hp.write_text(f"# 交接单 {t['id']} · {st['name']}\n\n- 片名：{t['title']}\n- 完成时间：{now()}\n- 产出物：{art}\n- 说明：{a.note or '无'}\n\n## 下游\n- 阶段：{nxt['name'] if nxt else '结束'}\n- 负责：{ROLES[nxt['owner']]['name'] if nxt else '-'}\n- 开工条件：{'上游已完成' if nxt else '-'}\n", encoding="utf-8")
    print(f"{t['id']} {st['name']} 完成 → 交接单 {hp.name} → 下一阶段 {nxt['name'] if nxt else '结束'}")

def cmd_reject(a):
    """退单：不推进阶段，写原因与已完成产物，交回团长改派"""
    b = load(); t = find(b, a.id); st = STAGE[t["stage"]]
    t["history"].append({"stage": st["id"], "result": "rejected", "at": now(),
                         "artifact": "", "note": a.reason, "by": t.get("owner")})
    t["status"] = "ready"; t["owner"] = "leader"
    save(b); print(f"{t['id']} {st['name']} 已退单：{a.reason}｜交回团长改派")

def cmd_assign(a):
    """团长改派：只换承接人，不跳阶段、不放行门禁"""
    b = load(); t = find(b, a.id)
    if a.to not in ROLES or a.to == "leader":
        raise SystemExit(f"BLOCKED: 只能派给执行单位 {list(ROLES)}")
    old = t.get("owner"); t["owner"] = a.to; t["status"] = "ready"; t["blocked"] = None
    t["history"].append({"stage": t["stage"], "result": "assigned", "at": now(),
                         "artifact": "", "note": f"{old}→{a.to}：{a.reason}", "by": "leader"})
    save(b); print(f"{t['id']} 改派 {old} → {a.to}：{a.reason}")

def cmd_block(a):
    """卡点：保留已完成产物，标明原因与下一处理者，状态仍可查"""
    b = load(); t = find(b, a.id); st = STAGE[t["stage"]]
    t["status"] = "blocked"; t["blocked"] = {"reason": a.reason, "next": a.next or "leader", "at": now()}
    t["history"].append({"stage": st["id"], "result": "blocked", "at": now(),
                         "artifact": "", "note": a.reason, "by": t.get("owner")})
    save(b); print(f"{t['id']} 挂起（{st['name']}）：{a.reason}｜下一处理者 {a.next or 'leader'}")

def cmd_unblock(a):
    b = load(); t = find(b, a.id)
    if not t.get("blocked"):
        print(f"{t['id']} 没有卡点"); return
    why = t["blocked"]["reason"]
    t["blocked"] = None; t["status"] = "ready"
    t["history"].append({"stage": t["stage"], "result": "unblocked", "at": now(),
                         "artifact": "", "note": f"解除：{why}", "by": "leader"})
    save(b); print(f"{t['id']} 卡点已解除：{why}")

def cmd_calls(a):
    """登记付费调用；超预算直接拦，不许悄悄加钱"""
    b = load(); t = find(b, a.id)
    total = t.get("calls", 0) + a.n
    if total > t.get("budget", 0):
        raise SystemExit(f"BLOCKED: 超出预算上限 {t.get('budget')}（已用 {t.get('calls',0)}，本次 {a.n}）")
    t["calls"] = total
    t["history"].append({"stage": a.stage or t["stage"], "result": "calls", "at": now(),
                         "artifact": "", "note": f"{a.n} 次 {a.note or ''}".strip(), "by": t.get("owner")})
    save(b); print(f"{t['id']} 付费调用 +{a.n} → {total}/{t.get('budget')}")

def cmd_next(a):
    b = load(); ready = [t for t in b["tasks"] if t["status"] in ("ready","working") and unlocked(t)]
    if not ready:
        print("没有可开工的任务"); return
    for t in ready:
        st = STAGE[t["stage"]]
        print(f"{t['id']} {st['name']} {ROLES[st['owner']]['name']} {t['title']}")

BRIEFS = DATA_ROOT / "briefs"; BRIEFS.mkdir(exist_ok=True)

def cmd_brief(a):
    b = load(); t = find(b, a.id); st = STAGE[t["stage"]]
    if st["owner"] == "leader":
        raise SystemExit("BLOCKED: 团长不参与生产")
    ups = [h for h in t["history"] if h["stage"] in st["needs"]]
    lines = [f"# 任务书 {t['id']} · {st['name']}", "",
             f"- 片名：{t['title']}",
             f"- 批次：{t.get('batch')}   账号：{t.get('account')}",
             f"- 承接：{ROLES[st['owner']]['name']}（{ROLES[st['owner']]['who']}）",
             f"- 交付物：{st['artifact']}", "",
             "## 上游输入"]
    for h in ups:
        lines.append(f"- {STAGE[h['stage']]['name']}：{h.get('artifact')}（{h.get('note','')}）")
    if not ups:
        lines.append("- 无（起始阶段）")
    lines += ["", "## 验收标准（逐条可判定，缺一不可）"]
    for i, x in enumerate(st.get("accept", []), 1):
        lines.append(f"{i}. {x}")
    lines += ["", "## 流程约束",
              f"1. 本阶段只交付「{st['artifact']}」，不越界做下游的事",
              ("2. 本阶段允许调用付费生成，但只准做本阶段需要的量，超出即停" if st.get("paid")
               else "2. 本阶段禁止任何付费生成与对外发布动作"),
              "3. 产出物写到项目目录，结尾用一行 OUTPUT: <绝对路径> 标注",
              "4. 缺信息输出 NEED_INFO（列待确认项，不阻塞交付），不合规输出 COMPLIANCE，做不了输出 BLOCKED",
              "5. 不要直接向用户汇报，结果交回团长",
              "", "## 待确认项", "- 由执行方在交付时列出；没有则写「无」", ""]
    fp = BRIEFS / f"{t['id']}_{st['id']}.md"
    fp.write_text("\n".join(lines), encoding="utf-8")
    print(fp)

p = argparse.ArgumentParser(prog="team")
sp = p.add_subparsers(dest="c", required=True)
x = sp.add_parser("add"); x.add_argument("title"); x.add_argument("--batch", default="-"); x.add_argument("--account", default="-"); x.add_argument("--budget", type=int, default=60); x.set_defaults(f=cmd_add)
sp.add_parser("list").set_defaults(f=cmd_list)
x = sp.add_parser("show"); x.add_argument("id"); x.set_defaults(f=cmd_show)
x = sp.add_parser("start"); x.add_argument("id"); x.set_defaults(f=cmd_start)
x = sp.add_parser("done"); x.add_argument("id"); x.add_argument("--artifact"); x.add_argument("--note"); x.set_defaults(f=cmd_done)
x = sp.add_parser("reject"); x.add_argument("id"); x.add_argument("--reason", required=True); x.set_defaults(f=cmd_reject)
x = sp.add_parser("assign"); x.add_argument("id"); x.add_argument("--to", required=True); x.add_argument("--reason", required=True); x.set_defaults(f=cmd_assign)
x = sp.add_parser("block"); x.add_argument("id"); x.add_argument("--reason", required=True); x.add_argument("--next"); x.set_defaults(f=cmd_block)
x = sp.add_parser("unblock"); x.add_argument("id"); x.set_defaults(f=cmd_unblock)
x = sp.add_parser("calls"); x.add_argument("id"); x.add_argument("--n", type=int, required=True); x.add_argument("--stage"); x.add_argument("--note"); x.set_defaults(f=cmd_calls)
sp.add_parser("next").set_defaults(f=cmd_next)
x = sp.add_parser("brief"); x.add_argument("id"); x.set_defaults(f=cmd_brief)
a = p.parse_args(); a.f(a)
