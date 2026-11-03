"""1.2.9 发布归属台账 + 星图后台数据 + 按需取数（用户口径：默认不发送）。

用户只要两样：
  ① 素材发到了**哪个抖音号**（账号名 + 号 ID）
  ② 那个号的**星图后台数据**（审核状态 / 播放量 / 星图有效播放 / 分成 / 预估收益）

本模块 = 这两样的唯一落点：
  * ``run/publish-records.jsonl``  每提交一条素材追加一行（发布归属 + 结果 + 失败原因）；
    星图后台抓回的数字**并入同一行**（``merge_star``），不另开表；
  * ``export_flat_xlsx``           一张扁平 Excel：单 Sheet，播放量降序，末行合计；
  * **默认不发送任何数据**：无定时、无周期、无后台自动上传；数据只留在客户机本地
    （台账 + 报表）。只有收到我方「取数指令」时才把这张表传**一次**。
  * ``heartbeat``                  轻量心跳（由 daemon 每 5 分钟调一次）：只带
    机器指纹 + 授权号，**不传任何数据**，只问「是否有取数指令」；
    心跳对客户不可见（不写任何客户可见日志 / 面板）。
  * ``upload``                     收到指令后才执行的那一次投递；
    载荷 = 数据表 + 机器指纹 + 授权号 + 时间戳 + HMAC-SHA256 签名。
  * 只传**数字与元数据**；禁止素材正文 / 登录态 / cookie（``_assert_no_secrets``）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .fingerprint import fingerprint
from .jsonio import append_jsonl, read_json, read_jsonl
from .minimal_xlsx import write_xlsx

SCHEMA = "winport-report/1"
SIGNATURE_HEADER = "X-Winport-Signature"
FETCH_TOKEN_HEADER = "X-Winport-Fetch-Token"
DEFAULT_HEARTBEAT_SECONDS = 300          # 心跳节奏由 daemon 决定（默认 5 分钟）
DEFAULT_KEY = "winport-demo-shared-secret"
DEFAULT_URL = "http://127.0.0.1:8791/ingest"

#: 结果（发布归属）
RESULT_OK = "成功"
RESULT_FAIL = "失败"
RESULT_PENDING = "待确认"
RESULTS = (RESULT_OK, RESULT_FAIL, RESULT_PENDING)

#: 扁平 Excel 列（严格按用户给的 8 列；「抖音号」列写「账号名（号 ID）」以同时满足①）
EXPORT_HEADERS = ["抖音号", "作品名称", "发布时间", "审核状态", "播放量",
                  "星图有效播放", "分成(元)", "预估收益(元)"]

#: 只准传数字与元数据 —— 命中即拒（防止误把正文/登录态塞进载荷）。
FORBIDDEN_KEYS = {"content", "cookie", "cookies", "session", "token",
                  "password", "storage_state", "登录态", "素材正文"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _num(value) -> float:
    try:
        return float(str(value).strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_keys(item)


def _assert_no_secrets(payload) -> None:
    bad = sorted(set(_iter_keys(payload)) & FORBIDDEN_KEYS)
    if bad:
        raise ValueError(f"载荷含禁止字段（正文/登录态/cookie）：{bad}")


def _derive_heartbeat_url(url: str) -> str:
    """Map the ingest URL to its sibling heartbeat endpoint (/ingest -> /heartbeat)."""
    base = url.rstrip("/")
    if base.endswith("/ingest"):
        base = base[:-len("/ingest")]
    return base + "/heartbeat"


def sign_payload(body: bytes, key: str) -> str:
    """HMAC-SHA256 over the canonical body -> ``sha256=<hex>``."""
    return "sha256=" + hmac.new(key.encode("utf-8"), body,
                                hashlib.sha256).hexdigest()


def star_fields_from_row(record: dict) -> dict:
    """把星图后台的一行（列名未知，13 列口径）按关键字映射到我们的字段。

    星图导出表头没有公开枚举，所以按关键字识别，识别不到就留空，绝不臆造列。
    """
    out = {"audit_status": "", "play_count": 0, "star_valid_play": 0,
           "share_amount": 0.0, "est_income": 0.0, "publish_time": "",
           "grab_time": _now_iso()}
    for col, value in record.items():
        name = str(col)
        if "发布" in name and "时间" in name:
            out["publish_time"] = str(value)
        elif "审核" in name:
            out["audit_status"] = str(value)
        elif "星图" in name or ("有效" in name and "播放" in name):
            out["star_valid_play"] = _num(value)
        elif "播放" in name:
            out["play_count"] = _num(value)
        elif "分成" in name:
            out["share_amount"] = _num(value)
        elif "预估" in name or "收益" in name:
            out["est_income"] = _num(value)
    return out


class ReportCenter:
    """发布归属台账 + 扁平导出 + 按需取数（单机单实例；默认不发送）。"""

    def __init__(self, layout, *, settings=None):
        self.layout = layout
        self.settings = settings or {}
        rpt = (self.settings or {}).get("report") or {}
        self.key = rpt.get("key") or DEFAULT_KEY
        self.url = rpt.get("url") or DEFAULT_URL
        self.heartbeat_url = rpt.get("heartbeat_url") or _derive_heartbeat_url(self.url)
        #: 多客户服务端上按客户分桶；空则不带该参数（本机回环测试用）。
        self.customer = rpt.get("customer") or ""
        #: 心跳总开关（默认开）。数据只在收到取数指令时传一次，与该开关无关。
        self.enabled = rpt.get("enabled", True)

    # --- 路径 -------------------------------------------------------------
    @property
    def records_path(self) -> Path:
        return self.layout.run / "publish-records.jsonl"

    # --- 台账 -------------------------------------------------------------
    def rows(self) -> list:
        return [r for r in read_jsonl(self.records_path)
                if isinstance(r, dict) and r.get("work_name") is not None]

    def record(self, work_name: str, account_name: str, account_id: str, *,
               submit_time=None, result=RESULT_PENDING, failure_reason="",
               source_folder="", item_id="", published_at=None, **star) -> dict:
        if result not in RESULTS:
            raise ValueError(f"result must be one of {RESULTS}, got {result!r}")
        row = {
            "record_id": hashlib.sha256(
                f"{work_name}|{account_id}|{submit_time or _now_iso()}".encode()
            ).hexdigest()[:16],
            "work_name": work_name, "account_name": account_name,
            "account_id": account_id, "source_folder": source_folder,
            "submit_time": submit_time or _now_iso(),
            "published_at": published_at or "",
            "item_id": str(item_id or ""),
            "publish_time": star.get("publish_time", ""), "result": result,
            "failure_reason": failure_reason,
            "audit_status": star.get("audit_status", ""),
            "play_count": _num(star.get("play_count")),
            "star_valid_play": _num(star.get("star_valid_play")),
            "share_amount": _num(star.get("share_amount")),
            "est_income": _num(star.get("est_income")),
            "grab_time": star.get("grab_time", ""),
        }
        append_jsonl(self.records_path, row)
        return row

    def record_published(self, plan: dict, *, channel=None, result=None) -> dict:
        """Append exactly one publish-ledger row for a confirmed work ID."""
        result = result or {}
        item_id = str(result.get("platform_work_id")
                      or result.get("item_id") or "").strip()
        if not item_id:
            return {"recorded": False, "reason": "missing item_id"}
        for row in self.rows():
            if str(row.get("item_id") or "") == item_id:
                return {"recorded": False, "duplicate": True, "row": row}
        piece = (plan or {}).get("piece") or {}
        work_name = (piece.get("title") or piece.get("file_name")
                     or (plan or {}).get("plan_id") or item_id)
        account_name = ((plan or {}).get("account_name")
                        or (plan or {}).get("account_nickname")
                        or getattr(channel, "nickname", ""))
        account_id = ((plan or {}).get("account_id")
                      or getattr(channel, "account_id", ""))
        published_at = result.get("published_at") or _now_iso()
        row = self.record(
            str(work_name), str(account_name or ""), str(account_id or ""),
            submit_time=published_at, published_at=published_at,
            result=RESULT_OK, item_id=item_id,
            source_folder=str((plan or {}).get("source_folder") or ""))
        return {"recorded": True, "row": row}

    def merge_star(self, record_id: str, **fields) -> bool:
        """把抓回的星图后台数据并入同一行（按 record_id 原子重写）。"""
        rows = self.rows()
        hit = False
        for row in rows:
            if row.get("record_id") == record_id:
                for key in ("audit_status", "play_count", "star_valid_play",
                            "share_amount", "est_income", "publish_time",
                            "grab_time"):
                    if key in fields and fields[key] not in (None, ""):
                        row[key] = fields[key] if key in ("audit_status",
                            "grab_time", "publish_time") else _num(fields[key])
                row.setdefault("grab_time", _now_iso())
                hit = True
        if hit:
            self._rewrite(rows)
        return hit

    @staticmethod
    def _work_name_of(star: dict) -> str:
        """星图导出表头未知，按关键字定位「作品名」列（撞不上就跳过）。"""
        for key in star:
            if any(tok in str(key) for tok in ("作品", "标题", "名称", "work")):
                return str(star[key]).strip()
        return ""

    def import_star_rows(self, star_rows: list) -> int:
        """按 作品名 把星图导出行并入台账；返回并入条数（撞不上就跳过）。"""
        merged = 0
        for star in star_rows:
            target = self._work_name_of(star)
            if not target:
                continue
            fields = star_fields_from_row(star)
            for row in self.rows():
                if str(row.get("work_name", "")).strip() == target:
                    self.merge_star(row["record_id"], **fields)
                    merged += 1
                    break
        return merged

    def _rewrite(self, rows: list) -> None:
        tmp = self.records_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(self.records_path)

    # --- 扁平 Excel -------------------------------------------------------
    def export_rows(self) -> list:
        ordered = sorted(self.rows(), key=lambda r: _num(r.get("play_count")),
                         reverse=True)
        table = [list(EXPORT_HEADERS)]
        for r in ordered:
            account = r.get("account_name", "")
            if r.get("account_id"):
                account = f"{account}（{r['account_id']}）"
            table.append([
                account, r.get("work_name", ""),
                r.get("publish_time") or r.get("submit_time", ""),
                r.get("audit_status", ""), _num(r.get("play_count")),
                _num(r.get("star_valid_play")), _num(r.get("share_amount")),
                ("" if not _num(r.get("est_income")) else _num(r.get("est_income")))])
        table.append([
            "合计", f"{len(ordered)} 条", "", "",
            sum(_num(r.get("play_count")) for r in ordered),
            sum(_num(r.get("star_valid_play")) for r in ordered),
            round(sum(_num(r.get("share_amount")) for r in ordered), 2),
            round(sum(_num(r.get("est_income")) for r in ordered), 2)])
        return table

    def export_flat_xlsx(self, path=None) -> Path:
        path = Path(path) if path else (self.layout.out_reports / "发布与后台数据.xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        write_xlsx(path, self.export_rows(), sheet_name="发布与后台数据")
        return path

    # --- 按需取数：心跳 + 单次投递 ----------------------------------------
    def _scoped(self, url: str) -> str:
        if self.customer and "?" not in url:
            return url + "?customer=" + urllib.parse.quote(self.customer)
        return url

    def _identity(self) -> dict:
        fp = fingerprint()
        lic = read_json(self.layout.license_file, default=None) or {}
        license_id = ""
        if isinstance(lic, dict):
            license_id = str(lic.get("license_id") or lic.get("customer_id") or "")
        return {"machine_id": fp["machine_id"], "license_id": license_id}

    def build_heartbeat(self) -> dict:
        """只带机器指纹 + 授权号（问「是否有取数指令」），**不含任何数据**。"""
        payload = {"schema": SCHEMA, "kind": "heartbeat", **self._identity(),
                   "ts": _now_iso()}
        _assert_no_secrets(payload)
        return payload

    def heartbeat(self, *, timeout: float = 10.0) -> dict:
        """轻量心跳：不带数据，只问「是否有取数指令」；有指令才传这张表一次。

        对客户不可见：不写任何客户可见的日志 / 面板；结果仅供我方调用方（daemon）吞掉。
        """
        if not self.enabled:
            return {"ok": False, "skipped": True, "reason": "disabled"}
        body = _canonical(self.build_heartbeat())
        request = urllib.request.Request(
            self._scoped(self.heartbeat_url), data=body, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8",
                     SIGNATURE_HEADER: sign_payload(body, self.key)})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                doc = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                TimeoutError, ValueError) as exc:
            return {"ok": False, "error": f"heartbeat unavailable: {exc}"}
        if not doc.get("fetch"):
            return {"ok": True, "fetch": False}
        return {"ok": True, "fetch": True,
                "upload": self.upload(token=doc.get("token"), timeout=timeout)}

    def build_payload(self) -> dict:
        ident = self._identity()
        rows = []
        for r in self.rows():
            rows.append({
                "account_name": r.get("account_name", ""),
                "account_id": r.get("account_id", ""),
                "work_name": r.get("work_name", ""),
                "publish_time": r.get("submit_time", ""),
                "result": r.get("result", ""),
                "audit_status": r.get("audit_status", ""),
                "play_count": _num(r.get("play_count")),
                "star_valid_play": _num(r.get("star_valid_play")),
                "share_amount": _num(r.get("share_amount")),
                "est_income": _num(r.get("est_income")),
                "grab_time": r.get("grab_time", ""),
            })
        payload = {"schema": SCHEMA, "kind": "table", **ident,
                   "ts": _now_iso(), "rows": rows}
        _assert_no_secrets(payload)
        return payload

    def upload(self, *, token=None, retries: int = 4, timeout: float = 15.0) -> dict:
        """收到取数指令后把这张表传**一次**（网络抖动按退避重试，仍是同一次投递）。

        不做任何本地留痕（不写客户可见日志 / 状态文件）；返回结果字典（不抛）。
        """
        payload = self.build_payload()
        body = _canonical(payload)
        headers = {"Content-Type": "application/json; charset=utf-8",
                   SIGNATURE_HEADER: sign_payload(body, self.key)}
        if token:
            headers[FETCH_TOKEN_HEADER] = str(token)
        backoff = [5, 15, 45, 135]
        last_error = ""
        for attempt in range(1, retries + 1):
            request = urllib.request.Request(self._scoped(self.url), data=body,
                                             method="POST", headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as resp:
                    text = resp.read().decode("utf-8", "replace")
                    return {"ok": True, "status": resp.status, "at": _now_iso(),
                            "rows": len(payload["rows"]), "resp": text}
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}"
                # 4xx 是服务端拒收（含错签名）——重试无意义，直接返回失败。
                if 400 <= exc.code < 500:
                    return {"ok": False, "status": exc.code, "at": _now_iso(),
                            "error": last_error}
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_error = f"network error: {exc}"
            if attempt < retries:
                time.sleep(backoff[min(attempt - 1, len(backoff) - 1)])
        return {"ok": False, "status": None, "at": _now_iso(), "error": last_error}
