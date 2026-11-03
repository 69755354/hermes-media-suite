"""Control-plane publish preparation and confirmation on the customer machine.

The control plane never gets a shell.  A remote ``publish`` command is one of
two fixed operations:

``prepare``
    scan the customer's own inbox, build plans and dry-run previews, and return
    the plan paths plus confirmation tokens to the bot.

``confirm``
    write the bot-signed receipt into the customer's run directory and invoke
    the normal ``publish --mode approved_publish`` CLI with the normal gates.

No command text is evaluated.  File paths are confined to the customer data
area, and the existing receipt / license / freeze / canary checks stay in the
same CLI path used by the single-customer deployment.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import stat
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .idempotency import material_fingerprint
from .jsonio import write_json
from .secure_io import (assert_no_reparse_chain, copy_hashed_file,
                        is_within, sha256_file, secure_stat)
from .subprocess_text import hidden_window_options

VIDEO_SUFFIXES = (".mp4", ".mov")
CN_TZ = timezone(timedelta(hours=8))


def _layout(config):
    return config.layout.ensure()


def _inside(path, root) -> bool:
    try:
        Path(path).resolve(strict=False).relative_to(
            Path(root).resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _safe_path(value, root, *, suffix=".json"):
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute() or not _inside(path, root):
        raise ValueError("path is outside the customer data area")
    path = path.resolve(strict=False)
    if suffix and path.suffix.lower() != suffix:
        raise ValueError("unexpected file type")
    return path


def _owned_drop_file(layout, value, root_dir):
    """Own regular file inside one publish root (inbox or desktop folder)."""
    raw = Path(str(value or "")).expanduser()
    if not raw.is_absolute():
        return None
    base = Path(os.path.abspath(os.fspath(root_dir)))
    path = Path(os.path.abspath(os.fspath(raw)))
    if not is_within(path, base):
        return None
    inbox = Path(os.path.abspath(os.fspath(layout.inbox)))
    if is_within(path, inbox):
        return _owned_inbox_file(layout, path)
    try:
        assert_no_reparse_chain(path, root=base)
        st = secure_stat(path, root=base)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size <= 0:
        return None
    if path.suffix.lower() not in VIDEO_SUFFIXES:
        return None
    return path


def _owned_inbox_file(layout, value):
    """Return one own regular inbox entry without following any link.

    The path is kept lexical.  Resolving it here would make every later
    reader follow a link that an attacker installs after this check.  The
    actual read path uses :func:`secure_io.secure_open` instead.
    """
    raw = Path(str(value or "")).expanduser()
    if not raw.is_absolute():
        return None
    layout.validate()
    root = Path(os.path.abspath(os.fspath(layout.root)))
    inbox = Path(os.path.abspath(os.fspath(layout.inbox)))
    path = Path(os.path.abspath(os.fspath(raw)))
    if not is_within(inbox, root) or not is_within(path, inbox):
        return None
    try:
        assert_no_reparse_chain(path, root=root)
        st = secure_stat(path, root=root)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size <= 0:
        return None
    if path.suffix.lower() not in VIDEO_SUFFIXES:
        return None
    return path


def _publish_roots(layout):
    """Every folder a customer may drop publish material into.

    The desktop ``发布素材`` folder is the folder customers actually use;
    the data inbox stays supported for existing installs.
    """
    roots = []
    seen = set()
    try:
        roots.append(Path(os.path.abspath(os.fspath(layout.inbox))))
    except OSError:
        pass
    try:
        from .desktop import materials_dir
        folder = materials_dir()
        if folder is not None and Path(folder).is_dir():
            roots.append(Path(os.path.abspath(os.fspath(folder))))
    except Exception:
        pass
    out = []
    for root in roots:
        key = os.path.normcase(str(root))
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _scan_inbox(layout):
    layout.validate()
    files = []
    seen = set()
    seen_keys = set()
    for inbox in _publish_roots(layout):
        try:
            entries = list(inbox.iterdir())
        except OSError:
            continue
        for path in entries:
            try:
                owned = _owned_drop_file(layout, path, inbox)
                if owned is None or owned in seen:
                    continue
                st = secure_stat(owned, root=inbox)
                if not stat.S_ISREG(st.st_mode):
                    continue
                if owned.name.startswith(".") or owned.name.startswith("~$"):
                    continue
                if st.st_size <= 0:
                    continue
                key = (owned.name.lower(), int(st.st_size))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                seen.add(owned)
                files.append((owned, st.st_mtime))
            except OSError:
                continue
    files.sort(key=lambda item: (item[1], item[0].name.lower()))
    return [item[0] for item in files]


def _pick_files(layout, payload):
    layout.validate()
    wanted = payload.get("files")
    if not isinstance(wanted, list) or not wanted:
        return _scan_inbox(layout)
    roots = _publish_roots(layout)
    out = []
    for value in wanted:
        path = None
        root = None
        for candidate in roots:
            try:
                found = _owned_drop_file(layout, value, candidate)
            except (OSError, ValueError):
                found = None
            if found is not None:
                path, root = found, candidate
                break
        if path is None:
            continue
        try:
            st = secure_stat(path, root=root)
            if not stat.S_ISREG(st.st_mode) or st.st_size <= 0:
                continue
            out.append((path, st.st_mtime))
        except (OSError, ValueError):
            continue
    out.sort(key=lambda item: (item[1], item[0].name.lower()))
    return [item[0] for item in out]


def _topics(value):
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        topic = str(item or "").strip()
        if not topic:
            continue
        if not topic.startswith("#"):
            topic = "#" + topic.lstrip("#")
        if topic not in out:
            out.append(topic)
    return out


def _target(envs, channels, payload):
    account_id = str(payload.get("account_id") or "").strip()
    channel_id = str(payload.get("channel_id") or "").strip()
    env_id = str(payload.get("env_id") or "").strip()
    channel = None
    if channel_id:
        channel = next((c for c in channels if c.channel_id == channel_id), None)
    if channel is None and account_id:
        channel = next((c for c in channels if c.account_id == account_id), None)
    if channel is None and env_id:
        channel = next((c for c in channels if c.env_id == env_id), None)
    if channel is None:
        channel = next((c for c in channels if c.platform == "douyin" and c.enabled), None)
    if channel is None:
        raise ValueError("no enabled douyin channel is configured")
    env = next((e for e in envs if e.env_id == channel.env_id), None)
    if env is None:
        raise ValueError("channel environment is not configured")
    return env, channel


def _preview_for(layout, plan, settings, envs, channels, now):
    from .dryrun import build_preview
    from .cli import _licence_gate
    license_info = _licence_gate(layout, plan=plan)
    return build_preview(plan, envs=envs, channels=channels, settings=settings,
                         license_info=license_info, now=now)


DEFAULT_PUBLISH_TITLE = "\u706b\u9f99\u6f2b\u5267\u514d\u8d39\u770b"
TITLE_LIMIT = 30


def _clamp_title(value, limit=TITLE_LIMIT):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        text = text[:limit].rstrip("\uff0c,\u3002.\u3001;\uff1b:\uff1a!\uff01?\uff1f~\uff5e-\u2014_ ")
    return text


def _title_from_path(path):
    """Derive a platform-legal title from a material file name.

    Material names are not titles: a content hash or a long descriptive name
    exceeds the 30-character limit and dry-run rejects the whole batch with
    TITLE_TOO_LONG.  Unreadable names fall back to the operator default;
    readable Chinese names are kept but clamped.
    """
    stem = str(getattr(path, "stem", path) or "").strip()
    if (not stem
            or re.fullmatch(r"[0-9a-fA-F]{16,64}", stem)
            or not re.search(r"[\u4e00-\u9fff]", stem)
            or len(stem) > TITLE_LIMIT):
        return DEFAULT_PUBLISH_TITLE
    return _clamp_title(stem) or DEFAULT_PUBLISH_TITLE


def _item_title(path, override):
    """One title for every item in a batch; the operator's word wins."""
    if override:
        return _clamp_title(override) or DEFAULT_PUBLISH_TITLE
    return _title_from_path(path)


def prepare(config, payload=None, command_id=None):
    """Build plans + dry-run previews from this customer's inbox."""
    payload = payload if isinstance(payload, dict) else {}
    layout = _layout(config)
    from .platforms import load_registry
    from .settings import load_settings

    settings = load_settings(layout.settings_file)
    envs, channels = load_registry(layout)
    env, channel = _target(envs, channels, payload)
    try:
        files = _pick_files(layout, payload)
    except (OSError, ValueError) as exc:
        return {"ok": False, "stage": "prepare", "error": "unsafe_inbox_path",
                "message": str(exc)}
    if not files:
        return {"ok": False, "stage": "prepare", "error": "inbox_empty",
                "message": "inbox has no publishable .mp4/.mov files"}
    if len(files) > int(payload.get("max_items") or 50):
        return {"ok": False, "stage": "prepare", "error": "too_many_items",
                "message": "too many inbox items for one batch"}

    batch_id = str(payload.get("batch_id") or "").strip()
    if not batch_id:
        batch_id = time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    batch_id = "".join(c if (c.isalnum() or c in "-_") else "_" for c in batch_id)[:64]
    title_override = _clamp_title(payload.get("title") or "")
    topics = _topics(payload.get("topics"))
    item_topics = payload.get("item_topics")
    now = datetime.now(CN_TZ)
    sched = settings.get("schedule") or {}
    try:
        gap_min = max(1, int(sched.get("gap_min", 5)))
        gap_max = max(gap_min, int(sched.get("gap_max", 8)))
    except (TypeError, ValueError):
        gap_min, gap_max = 5, 8
    rng = random.SystemRandom()

    # 1.2.153: schedule into the next legal window instead of now+30s, which
    # always tripped SCHEDULE_OUT_OF_WINDOW when min_lead_minutes > 0.
    from .schedule import next_slot, pick_slots
    try:
        planned = pick_slots(len(files), now, settings=settings)
    except Exception:
        planned = []
    items = []
    for index, path in enumerate(files, 1):
        slot = planned[index - 1] if len(planned) >= index else None
        if slot is None:
            slot = next_slot(now, settings=settings)
        schedule_at = slot.replace(microsecond=0).isoformat()
        title = _item_title(path, title_override)
        item_topic = topics
        if isinstance(item_topics, dict):
            value = item_topics.get(str(index), item_topics.get(index))
            if isinstance(value, list):
                item_topic = _topics(value)
        elif isinstance(item_topics, list) and len(item_topics) >= index:
            value = item_topics[index - 1]
            if isinstance(value, list):
                item_topic = _topics(value)
        item_dir = layout.run / "remote" / batch_id / ("item_%02d" % index)
        source_dir = item_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        staged_source = source_dir / path.name
        allowed_root = layout.root
        try:
            from .desktop import materials_dir as _materials_dir
            _folder = _materials_dir()
            if _folder is not None and _inside(path, Path(_folder)):
                allowed_root = Path(_folder)
        except Exception:
            pass
        try:
            digest, _size = copy_hashed_file(
                path, staged_source, root=allowed_root)
        except OSError as exc:
            return {"ok": False, "stage": "prepare",
                    "error": "unsafe_inbox_path", "message": str(exc)}
        piece = {
            "title": title,
            "copy_body": title,
            "topics": item_topic,
            "file_path": str(staged_source),
            "file_name": path.name,
            "sha256": digest,
            "cover_sha256": {},
            "covers": {"vertical": None, "horizontal": None},
            "platform_account_id": channel.account_id,
        }
        content_hash = material_fingerprint(piece, account_id=channel.account_id)
        plan = {
            "plan_id": "remote-%s-%03d" % (batch_id, index),
            "env_id": env.env_id,
            "channel_id": channel.channel_id,
            "account_id": channel.account_id,
            "platform": channel.platform,
            "schedule_at": schedule_at,
            "piece": piece,
            "compliance": {"content_hash": content_hash},
        }
        plan_path = item_dir / "plan.json"
        preview_path = item_dir / "preview.json"
        preview_md_path = item_dir / "preview.md"
        write_json(plan_path, plan)
        preview = _preview_for(layout, plan, settings, envs, channels, now)
        if preview.get("ok"):
            write_json(preview_path, preview)
            from .dryrun import render_markdown
            preview_md_path.write_text(render_markdown(preview), encoding="utf-8")
        items.append({
            "index": index,
            "name": path.name,
            "title": title,
            "topics": item_topic,
            "plan_path": str(plan_path),
            "preview_path": str(preview_path),
            "preview_md_path": str(preview_md_path),
            "confirm_token": preview.get("confirm_token") if preview.get("ok") else None,
            "plan_id": plan["plan_id"],
            "content_hash": content_hash,
            "schedule_at": schedule_at,
            "plan_data": plan,
            "preview_ok": bool(preview.get("ok")),
            "problems": preview.get("problems") or [],
        })
    failed = [item for item in items if not item["preview_ok"]]
    return {
        "ok": not failed,
        "stage": "prepared",
        "batch_id": batch_id,
        "count": len(items),
        "gap_min": gap_min,
        "gap_max": gap_max,
        "items": items,
        "problems": [{"item": item["index"], "problems": item["problems"]}
                     for item in failed],
        "command_id": command_id,
    }


def _run_cli(config, argv, timeout, runner=None):
    runner = runner or subprocess.run
    env = os.environ.copy()
    layout = _layout(config)
    env["WINPORT_DATA"] = str(layout.root)
    env["WINPORT_SYSTEM"] = str(layout.system)
    env["CUSTOMER_ID"] = config.customer_id
    if config.token:
        env["CUSTOMER_TOKEN"] = config.token
    if config.program_dir:
        env["WINPORT_PROGRAM"] = str(config.program_dir)
    return runner(argv, capture_output=True, text=True, timeout=timeout,
                  env=env, cwd=config.cli_root or None, shell=False,
                  **hidden_window_options(argv))


def _payload_flag(value) -> bool:
    """Accept only an explicit confirmation flag, never a truthy string."""
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def confirm(config, payload=None, command_id=None, runner=None):
    """Write the signed receipt and run the normal approved-publish CLI."""
    payload = payload if isinstance(payload, dict) else {}
    layout = _layout(config)
    if not payload.get("receipt"):
        return {"ok": False, "stage": "confirm", "error": "receipt_missing"}
    plan_path = _safe_path(payload.get("plan"), layout.root)
    preview_path = _safe_path(payload.get("preview"), layout.root)
    token = str(payload.get("confirm_token") or "")
    if not token:
        return {"ok": False, "stage": "confirm", "error": "confirm_token_missing"}
    command_part = re.sub(r"[^A-Za-z0-9._-]", "_",
                          str(command_id or ""))[:80]
    if not command_part or command_part in (".", ".."):
        command_part = uuid.uuid4().hex
    receipt_dir = layout.run / "remote-confirm" / command_part
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / "receipt.json"
    write_json(receipt_path, payload.get("receipt"))

    workspace = Path(config.cli_root) if config.cli_root else None
    argv = [config.cli_python, "-m", "agent.winport.cli", "publish",
            "--data", str(layout.root), "--mode", "approved_publish",
            "--plan", str(plan_path), "--preview", str(preview_path),
            "--confirm-token", token, "--receipt", str(receipt_path)]
    # The two real-publish switches are never implied by ``confirm``.  The
    # control plane must carry the explicit, already-verified confirmation
    # fields; otherwise the CLI stays on its normal preview/approval path.
    allow_submit = _payload_flag(payload.get("allow_submit"))
    canary_armed = _payload_flag(payload.get("canary_armed"))
    if allow_submit:
        argv.append("--allow-submit")
    if canary_armed:
        argv.append("--canary-armed")
    if workspace:
        argv += ["--program", str(workspace)]
    if payload.get("republish_confirmed"):
        argv.append("--republish-confirmed")
    timeout = payload.get("timeout", config.command_timeout)
    try:
        timeout = max(1.0, min(float(timeout), 3600.0))
    except (TypeError, ValueError):
        timeout = config.command_timeout
    try:
        proc = _run_cli(config, argv, timeout, runner=runner)
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "stage": "confirm", "error": "timeout",
                "argv": argv, "stdout": exc.stdout or "", "stderr": exc.stderr or ""}
    except Exception as exc:  # noqa: BLE001 - reported to the control plane
        return {"ok": False, "stage": "confirm", "error": str(exc), "argv": argv}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    parsed = {}
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            parsed = value
            break
    ok = proc.returncode == 0 and bool(parsed.get("published"))
    return {
        "ok": ok,
        "stage": "confirm",
        "exit_code": proc.returncode,
        "published": bool(parsed.get("published")),
        "platform_work_id": parsed.get("platform_work_id"),
        "allow_submit": allow_submit,
        "canary_armed": canary_armed,
        "result": parsed,
        "stdout": stdout[-20000:],
        "stderr": stderr[-20000:],
        "argv": argv,
    }
