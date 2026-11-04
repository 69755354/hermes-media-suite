"""B · 失败留证：每一步失败都落 截图 + HTML 快照 + 结构化说明。

source/design-refs-mainstream.md B: 平台改版时，光有一行日志查不出问题，
必须留下「当时那个页面长什么样」。所以每个失败点（起浏览器 / 登录检查 /
上传 / 填表 / 抓数）都调 ``capture(...)``：

  * 文件名带时间与环境：``20261016T051530_env_1_upload__RATE_LIMITED.png``；
  * 目录固定在**客户机侧的数据区** ``<Data>/evidence/``（随登录态、账本一起在
    客户机，绝不外传 cookie）；
  * 每条追加一行到 ``<Data>/evidence/INDEX.jsonl``，报告里引用索引即可；
  * 保留策略：默认保留 ``retention_days``（settings，默认 14）天，``prune()`` 删除
    超期证据；``INDEX`` 也同步裁剪。清理策略写进客户说明书。

诚实的取舍：这个模块**不伪造**截图。真实驱动（Playwright）失败时会把
``page.screenshot()`` 的字节和 ``page.content()`` 传进来；在只能静态验证的
构建机上没有浏览器，于是 ``screenshot_available=false`` / ``html_available=false``
被如实写进记录与索引 —— 报告里不会出现"已截图"的假话。
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

INDEX_NAME = "INDEX.jsonl"
DEFAULT_RETENTION_DAYS = 14

STEPS = ("browser", "login_check", "upload", "fill", "collect", "publish",
         "downlink", "license", "state", "general")

_SLUG_OK = re.compile(r"[^A-Za-z0-9._-]+")

RETAINED_SUFFIXES = (".png", ".html", ".txt", ".json")


def _slug(text, *, fallback="step", limit=48) -> str:
    text = _SLUG_OK.sub("-", str(text or "").strip()).strip("-.")
    return (text or fallback)[:limit]


def _stamp(now=None) -> str:
    return time.strftime("%Y%m%dT%H%M%S", time.localtime(now) if now else time.localtime())


class EvidenceStore:
    """Per-installation failure evidence directory (客户机侧)."""

    def __init__(self, layout, *, retention_days=None, settings=None):
        self.layout = layout
        from .customer_paths import layout_dir
        self.root = layout_dir(layout, "evidence", "evidence")
        if retention_days is None:
            retention_days = (settings or {}).get("retention_days",
                                                  DEFAULT_RETENTION_DAYS)
        try:
            self.retention_days = int(retention_days)
        except (TypeError, ValueError):
            self.retention_days = DEFAULT_RETENTION_DAYS

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_NAME

    def ensure(self) -> "EvidenceStore":
        self.root.mkdir(parents=True, exist_ok=True)
        return self

    def _write_index(self, record: dict) -> None:
        self.ensure()
        with self.index_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def capture(self, step: str, *, env_id=None, channel_id=None, platform=None,
                error=None, note=None, screenshot=None, html=None, extra=None,
                now=None) -> dict:
        """Record one failure.  ``screenshot`` bytes|Path, ``html`` str|bytes."""
        self.ensure()
        stamp = _stamp(now)
        sequence = 0
        base = f"{stamp}__{_slug(env_id, fallback='noenv')}__{_slug(step)}"
        while True:
            stem = base if not sequence else f"{base}-{sequence}"
            png = self.root / f"{stem}.png"
            if not png.exists() and not (self.root / f"{stem}.json").exists():
                break
            sequence += 1

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z",
                                time.localtime(now) if now else time.localtime()),
            "step": step,
            "env_id": env_id,
            "channel_id": channel_id,
            "platform": platform,
            "error": (str(error)[:2000] if error is not None else None),
            "note": note,
            "screenshot": None,
            "html": None,
            "screenshot_available": False,
            "html_available": False,
            "retention_days": self.retention_days,
        }
        png_path = self.root / f"{stem}.png"
        if screenshot is not None:
            try:
                if isinstance(screenshot, (bytes, bytearray)):
                    png_path.write_bytes(bytes(screenshot))
                else:
                    shutil.copyfile(Path(screenshot), png_path)
                record["screenshot"] = png_path.name
                record["screenshot_available"] = True
            except OSError as exc:
                record["note"] = ((record["note"] or "") +
                                  f" [screenshot 写入失败: {exc}]").strip()
        html_path = self.root / f"{stem}.html"
        if html is not None:
            try:
                payload = html if isinstance(html, (bytes, bytearray)) else \
                    str(html).encode("utf-8")
                html_path.write_bytes(payload)
                record["html"] = html_path.name
                record["html_available"] = True
            except OSError as exc:
                record["note"] = ((record["note"] or "") +
                                  f" [html 写入失败: {exc}]").strip()
        if extra:
            record["extra"] = extra
        meta_path = self.root / f"{stem}.json"
        meta_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        record["meta"] = meta_path.name
        self._write_index(record)
        return record

    def list_entries(self) -> list:
        if not self.index_path.exists():
            return []
        rows = []
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        return rows

    def prune(self, *, days=None, now=None) -> dict:
        """Delete evidence older than ``days`` (default retention_days)."""
        days = self.retention_days if days is None else int(days)
        cutoff = (now or time.time()) - days * 86400
        removed, kept = [], []
        if self.root.exists():
            for path in sorted(self.root.iterdir()):
                if path.name == INDEX_NAME or not path.is_file():
                    continue
                if path.suffix.lower() not in RETAINED_SUFFIXES:
                    continue
                if path.stat().st_mtime < cutoff:
                    try:
                        path.unlink()
                        removed.append(path.name)
                    except OSError:
                        kept.append(path.name)
        rows = self.list_entries()
        fresh = [r for r in rows if _entry_ts(r) >= cutoff]
        if len(fresh) != len(rows):
            self.ensure()
            tmp = self.index_path.with_name(INDEX_NAME + ".tmp")
            tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                   for r in fresh), encoding="utf-8")
            tmp.replace(self.index_path)
        return {"days": days, "removed": removed,
                "removed_count": len(removed),
                "index_entries_before": len(rows),
                "index_entries_after": len(fresh),
                "root": str(self.root)}

    def describe(self) -> dict:
        rows = self.list_entries()
        return {"root": str(self.root), "retention_days": self.retention_days,
                "entries": len(rows),
                "last": rows[-1] if rows else None}


def _entry_ts(record: dict) -> float:
    text = str(record.get("ts", ""))[:19]
    try:
        return time.mktime(time.strptime(text, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return 0.0


def failure_evidence(layout, step, result, *, env_id=None, channel_id=None,
                     platform=None, screenshot=None, html=None, settings=None):
    """Convenience wrapper: turn a step's *result dict* into one evidence record.

    A result is a "failure" when it carries ``error`` or its ``reason`` is not a
    success marker; the callback is a no-op for DRY_RUN so a dry run never
    litters the evidence directory.
    """
    result = result or {}
    reason = result.get("reason") or ""
    if reason == "DRY_RUN":
        return None
    reason_uppercase = str(reason).upper()
    if reason_uppercase in ("OPENED", "REUSED_ENV_WINDOW"):
        return None
    error = result.get("error") or result.get("message")
    if not error and not result.get("opened"):
        error = reason or "step failed"
    store = EvidenceStore(layout, settings=settings)
    return store.capture(step, env_id=env_id or result.get("env_id"),
                         channel_id=channel_id or result.get("channel_id"),
                         platform=platform, error=error, screenshot=screenshot,
                         html=html,
                         extra={"reason": reason, "result": _redacted(result)})


def _redacted(result: dict) -> dict:
    from .logutil import redact
    out = {}
    for key, value in result.items():
        if key == "command":
            out[key] = [redact(str(v)) for v in (value or [])]
        elif isinstance(value, str):
            out[key] = redact(value)
        else:
            out[key] = value
    return out
