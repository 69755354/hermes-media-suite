#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""执行器适配层：把任务书交给具体执行单位，返回产出物路径。

规则：
- 每个阶段都必须有明确执行器，不允许 NOT_WIRED 蒙混；
- 付费/对外发布必须人工放行（HumanGate），不自动执行；
- 执行器给不出 OUTPUT 路径或产出物不存在，一律算失败，不假装成功。
"""
import json, os, pathlib, re, shutil, subprocess, time


def resolve_executor(raw):
    """执行器路径优先取环境变量，其次 PATH，最后回落到配置原值。"""
    env = os.environ.get("CODEX_DS_SCRIPT")
    if env:
        return env
    if raw and os.path.exists(raw):
        return raw
    return shutil.which(raw or "") or raw or "codex_ds.sh"

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_ROOT = pathlib.Path(os.environ.get("TEAM_DATA") or ROOT)
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


class NotWired(Exception):
    """执行器没接通（配置层问题，需要修架构）。"""


class HumanGate(Exception):
    """需要人点头才能继续（付费/对外动作）。"""

    def __init__(self, reason, next_handler="leader", ticket=None):
        super().__init__(reason)
        self.next_handler = next_handler
        self.ticket = ticket


class ExecFail(Exception):
    """执行器跑完但没有合格产出物。"""


def workdir(tid, sid):
    d = ROOT / CFG.get("workdir", "work") / tid / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stub(brief, tid, sid):
    d = workdir(tid, sid)
    p = d / f"{sid}_artifact.txt"
    p.write_text(f"[stub] {tid}/{sid}\n{brief[:400]}\n", encoding="utf-8")
    return str(p)


def _stub_ok(brief, tid, sid):
    """联调用：产出能满足验收闸的假文件（不花钱，不代表真实跑通）。"""
    d = workdir(tid, sid)
    if sid == "COMPLIANCE":
        p = d / "verdict.txt"; p.write_text("VERDICT: PASS\n逐条对照：全部通过（stub）\n", encoding="utf-8")
    elif sid == "PUBLISH":
        p = d / "receipt.txt"; p.write_text("CONFIRMED 已回读作品列表（stub）\n", encoding="utf-8")
    elif sid == "COLLECT":
        p = d / "table.csv"; p.write_text("号,作品名称\n一号,stub\n", encoding="utf-8")
    else:
        p = d / f"{sid}_artifact.txt"; p.write_text(f"[stub_ok] {tid}/{sid}\n", encoding="utf-8")
    return str(p)


def _run_cmd(cmd, cwd, timeout, stdin_text=None):
    r = subprocess.run(cmd, input=stdin_text, text=True, cwd=str(cwd),
                       capture_output=True, timeout=timeout)
    return r


def _codex_like(brief, tid, sid, extra_prefix=""):
    ex = CFG["executors"].get("codex", {})
    if not ex.get("enabled"):
        raise NotWired("codex 执行器未启用（config.json executors.codex.enabled=false）")
    d = workdir(tid, sid)
    prompt = (extra_prefix + "\n\n" + brief).strip()
    (d / "brief.md").write_text(prompt, encoding="utf-8")
    cmd = [resolve_executor(ex.get("cmd")), "exec", "--skip-git-repo-check", "--sandbox", "danger-full-access", prompt]
    try:
        r = _run_cmd(cmd, d, ex.get("timeout", 3600))
    except subprocess.TimeoutExpired:
        raise ExecFail(f"执行器超时（>{ex.get('timeout', 3600)}s）")
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    (d / "run.log").write_text(out, encoding="utf-8")
    if r.returncode != 0:
        raise ExecFail(f"执行器退出码 {r.returncode}，见 {d/'run.log'}")
    m = re.findall(r"OUTPUT:\s*(\S+)", out)
    if not m:
        raise ExecFail(f"执行器没有给出 OUTPUT: 路径，见 {d/'run.log'}")
    p = pathlib.Path(m[-1].strip().strip('`"\''))
    if not p.is_absolute():
        p = (d / p).resolve()
    if not p.exists():
        raise ExecFail(f"执行器给的产出物不存在：{p}")
    return str(p)


def _codex(brief, tid, sid):
    return _codex_like(brief, tid, sid)


REVIEW_PREFIX = """你是审核组，不是视频组。只做判定，不改稿、不出片、不重写文案。
逐条对照任务书里的验收标准与合规红线，最后必须单独一行输出：
VERDICT: PASS
或
VERDICT: REJECT
并在 VERDICT 行之前逐条列出未通过项（写明哪一条、什么问题）。
同时把判定写成文件，结尾一行输出 OUTPUT: <绝对路径>。
"""


def _review(brief, tid, sid):
    return _codex_like(brief, tid, sid, REVIEW_PREFIX)


def _publish(brief, tid, sid):
    """发布=对外动作：只出待发工单，必须人工放行后由发布组执行。"""
    d = workdir(tid, sid)
    tk = DATA_ROOT / "handoffs" / f"PUB_{tid}.md"
    tk.parent.mkdir(exist_ok=True)
    art = _artifact_path(tid, "COMPOSE")
    tk.write_text(
        f"# 待发布工单 {tid}\n\n- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- 成片：{art or '（上游 COMPOSE 未登记产出物）'}\n\n"
        f"## 放行方式\n人工确认后执行：\n\n    ./teamctl approve {tid} PUBLISH\n\n"
        f"## 约束\n- 未放行不得对外发布\n- 发布后必须回读作品列表确认，拿不到回执按未发布处理\n",
        encoding="utf-8")
    raise HumanGate(f"发布需人工放行（工单 {tk}）", "leader", str(tk))


def _data(brief, tid, sid):
    """数据组：调取数脚本产出 20 列作品表，不发飞书、不刷屏。"""
    d = workdir(tid, sid)
    tool = ROOT / "tools" / "collect_report.py"
    if not tool.exists():
        raise NotWired("数据组脚本 tools/collect_report.py 不存在")
    try:
        r = _run_cmd(["python3", str(tool), "--out-dir", str(d)], d, 600)
    except subprocess.TimeoutExpired:
        raise ExecFail("取数超时（>600s）")
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    (d / "run.log").write_text(out, encoding="utf-8")
    if r.returncode != 0:
        raise ExecFail(f"取数失败（exit {r.returncode}）：{out.strip().splitlines()[-1][:200] if out.strip() else ''}")
    m = re.findall(r"OUTPUT:\s*(\S+)", out)
    if not m or not pathlib.Path(m[-1].strip()).exists():
        raise ExecFail("取数没产出文件（缺 OUTPUT 或文件不存在）")
    return m[-1].strip()


def _artifact_path(tid, sid):
    import sqlite3
    dbp = ROOT / CFG.get("db", "state/team.db")
    con = sqlite3.connect(dbp)
    try:
        r = con.execute("SELECT path FROM artifacts WHERE task_id=? AND stage_id=? ORDER BY id DESC LIMIT 1",
                        (tid, sid)).fetchone()
    except Exception:
        r = None
    finally:
        con.close()
    return r[0] if r else None


ADAPTERS = {
    "stub": _stub,
    "stub_ok": _stub_ok,
    "codex": _codex,
    "codex_review": _review,
    "publish_gate": _publish,
    "data_tools": _data,
}


def _resolve(name):
    ex = CFG["executors"].get(name)
    if not ex:
        for v in CFG["executors"].values():
            if v.get("type") == name:
                ex = v
                break
    if not ex:
        raise NotWired(f"没有这个执行器: {name}")
    fn = ADAPTERS.get(ex["type"])
    if not fn:
        raise NotWired(f"执行器类型没有实现: {ex['type']}")
    return fn


def get(name):
    return _resolve(name)


def dispatch(tid, sid, brief, name=None):
    name = name or CFG["stage_executor"].get(sid)
    fn = _resolve(name)
    return fn(brief, tid, sid)
