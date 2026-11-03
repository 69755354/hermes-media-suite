"""按冻结目录把内部产物重新渲染为客户视图。"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


FORBIDDEN = [
    (re.compile(r"/home/ubuntu/", re.I), "内部路径"),
    (re.compile(r"/tmp/projects/", re.I), "临时路径"),
    (re.compile(r"(?:^|\s)MEDIA\s*[:/]", re.I | re.M), "内部媒体前缀"),
    (re.compile(r"\bT-[A-Z0-9_-]+"), "内部轨名"),
    (re.compile(r"节点\s*\d+", re.I), "内部节点号"),
    (re.compile(r"(?<![A-Za-z])(codex|claude|deepseek)(?![A-Za-z])", re.I), "内部执行器名"),
    (re.compile(r"执行者", re.I), "内部执行标记"),
]


def assert_client_safe(text: str) -> None:
    for pattern, label in FORBIDDEN:
        if pattern.search(text):
            raise ValueError(f"客户视图安全检查失败：{label}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalog(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("meta", {}).get("export_rules", {}).get("render_mode") != "whitelist_rerender":
        raise RuntimeError("客户视图目录未声明白名单重渲染")
    return data


def _safe_text(value: Any) -> str:
    if value is None:
        return "待核验"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).strip()
    assert_client_safe(text)
    return html.escape(text, quote=True)


def _render_value(value: Any) -> str:
    if isinstance(value, dict):
        rows = "".join(
            f"<dt>{_safe_text(key)}</dt><dd>{_render_value(item)}</dd>"
            for key, item in value.items()
        )
        return f'<dl class="view-kv">{rows}</dl>'
    if isinstance(value, list):
        if not value:
            return '<span class="muted">暂无</span>'
        return "<ul>" + "".join(f"<li>{_render_value(item)}</li>" for item in value) + "</ul>"
    text = _safe_text(value)
    parsed = urlparse(html.unescape(text))
    if parsed.scheme:
        if parsed.scheme != "https":
            raise ValueError("客户视图只允许 https 外链")
        return f'<a href="{text}" target="_blank" rel="noopener noreferrer">查看来源</a>'
    return text.replace("\n", "<br>")


def render_client_view(catalog: dict[str, Any], view_id: str, fields: dict[str, Any], destination: Path) -> str:
    spec = catalog.get("views", {}).get(view_id)
    if not spec:
        raise KeyError(view_id)
    required = spec["required_fields"]
    missing = [name for name in required if name not in fields]
    if missing:
        raise ValueError(f"客户视图缺少白名单字段：{','.join(missing)}")
    sections = "".join(
        f'<section class="client-field"><h3>{_safe_text(name)}</h3><div>{_render_value(fields[name])}</div></section>'
        for name in required
    )
    rendered = (
        '<article class="client-view" data-view-version="'
        + _safe_text(spec["version"])
        + '"><div class="client-view-grid">'
        + sections
        + "</div></article>"
    )
    assert_client_safe(rendered)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    return sha256_file(destination)


def safe_json_response(value: Any) -> None:
    assert_client_safe(json.dumps(value, ensure_ascii=False))
