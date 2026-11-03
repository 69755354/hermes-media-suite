"""Xingtu task (star order) selection, attachment checks and local dedup.

Selection happens inside the Douyin publish page: the caller supplies a task
name and no Xingtu backend list is needed.  Duplicate protection is local:
the publish flow checks the used-task ledger before submit and appends to it
only after a confirmed publish.  Post-publish backend list read-back was
removed because Xingtu itself rejects duplicate submissions.  This module
never contains a task name, order id, demander or customer name.  Task type is
display/filter data only; it is not a code branch.

The pure parsers at the top are used by the Linux test suite.  The live
functions at the bottom drive the already signed-in Chrome page through
Playwright and fail closed.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .errors import GateRed

try:  # POSIX cross-process lock
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:  # Windows cross-process lock
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

CREATOR_URL = "https://www.xingtu.cn/sup/creator"
STAR_AD_URL = "https://www.xingtu.cn/sup/creator/star-ad-unite"
TASK_MENU_SELECTOR = 'a[href="/sup/user/task"]'
TASK_URL = "https://www.xingtu.cn/sup/creator/user/task"
DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_PUBLISH_URL = "https://creator.douyin.com/creator-micro/content/post/video"

STATUS_FOUND = "FOUND"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_UNKNOWN = "UNKNOWN"

#: Local ledger of task names we have already published.  It lives under the
#: publish-worker data directory (``<data>/run/xingtu_used_tasks.json``).
USED_TASKS_FILENAME = "xingtu_used_tasks.json"
USED_TASKS_VERSION = 1
USED_TASKS_LOCK_TIMEOUT_SECONDS = 10.0
USED_TASKS_LOCK_POLL_SECONDS = 0.05

#: Material keyword -> star task name shown in the Douyin picker.
#: Kept identical to ``feishu_publish_bot.bot.XINGTU_TASK_LABELS``: dates are
#: deliberately excluded because the backend renames tasks over time.
XINGTU_TASK_LABELS = (
    ("\u514d\u8d39-\u65b0\u7801", ("\u514d\u8d39",)),
    ("\u6fc0\u52b1-\u65b0\u7801", ("\u6fc0\u52b1",)),
    ("APP\u79cd\u8349", ("APP\u79cd\u8349", "\u79cd\u8349")),
    ("\u5267\u96c6\u526a\u8f91", ("\u5267\u96c6", "\u526a\u8f91")),
)

_ORDER_RE = re.compile(
    r"(?:order_id|orderId|orderid|order%5Fid|task_id|taskId|taskid)"
    r"[=:%3D]+([A-Za-z0-9_-]{6,64})",
    re.IGNORECASE,
)
_DETAIL_ID_RE = re.compile(r"/detail/([A-Za-z0-9_-]{6,64})")
_DETAIL_ID_LINE_RE = re.compile(
    r"(?:\u4efb\u52a1ID|\u8ba2\u5355\u53f7|\u8ba2\u5355ID|task_id|order_id)"
    r"\s*[:=\uff1a]?\s*([A-Za-z0-9_-]{6,64})",
    re.IGNORECASE,
)
_ACTION_WORDS = (
    "\u67e5\u770b\u8be6\u60c5", "\u53bb\u6295\u7a3f", "\u7acb\u5373\u6295\u7a3f",
    "\u6295\u7a3f", "\u53c2\u4e0e\u4efb\u52a1", "\u7acb\u5373\u53c2\u4e0e",
)
_UNAVAILABLE_WORDS = (
    "\u5df2\u7ed3\u675f", "\u5df2\u4e0b\u7ebf", "\u5df2\u62a2\u5149",
    "\u5df2\u6ee1", "\u65e0\u5269\u4f59", "\u4e0d\u53ef\u6295\u7a3f",
)
_EMPTY_SUBMISSION_WORDS = (
    "\u6682\u65e0\u6295\u7a3f", "\u8fd8\u672a\u6295\u7a3f", "\u6682\u65e0\u4f5c\u54c1",
    "\u672a\u6295\u7a3f", "\u65e0\u6295\u7a3f\u8bb0\u5f55",
)
_EMPTY_LIST_WORDS = (
    "\u6682\u65e0\u4efb\u52a1", "\u6682\u65e0\u6570\u636e", "\u6682\u65e0\u5185\u5bb9",
    "\u6ca1\u6709\u4efb\u52a1", "\u6682\u65e0\u76f8\u5173\u4efb\u52a1", "\u4efb\u52a1\u4e3a\u7a7a",
)
_LOGIN_WORDS = (
    "\u626b\u7801\u767b\u5f55", "\u624b\u673a\u53f7\u767b\u5f55", "\u5bc6\u7801\u767b\u5f55",
    "\u767b\u5f55\u661f\u56fe", "\u7acb\u5373\u767b\u5f55", "\u8bf7\u5148\u767b\u5f55",
    "\u8d26\u53f7\u767b\u5f55",
)
_SUBMIT_ACTION_WORDS = ("\u8ffd\u52a0\u6295\u7a3f", "\u4e0a\u4f20\u89c6\u9891",
                        "\u53bb\u4e0a\u4f20")
_DETAIL_ACTION = "\u67e5\u770b\u8be6\u60c5"
_ROW_VIDEO_STATUSES = ("\u89c6\u9891\u5df2\u4e0a\u4f20",
                       "\u5f85\u4e0a\u4f20\u89c6\u9891")
_DETAIL_NAME_LABELS = ("\u521b\u610f\u63cf\u8ff0", "\u4efb\u52a1\u540d\u79f0",
                       "\u4efb\u52a1\u6807\u9898", "\u4efb\u52a1\u540d")

_LABELS = {
    "task_name": ("\u4efb\u52a1\u540d\u79f0", "\u4efb\u52a1\u540d", "\u4efb\u52a1\u6807\u9898",
                  "\u4efb\u52a1"),
    "demander": ("\u9700\u6c42\u65b9", "\u5ba2\u6237\u540d\u79f0", "\u54c1\u724c\u540d\u79f0",
                 "\u5e7f\u544a\u4e3b", "\u5408\u4f5c\u65b9"),
    "task_type": ("\u4efb\u52a1\u7c7b\u578b", "\u4efb\u52a1\u5f62\u5f0f",
                  "\u4efb\u52a1\u73a9\u6cd5", "\u5408\u4f5c\u7c7b\u578b"),
    "remaining_quota": ("\u5269\u4f59\u914d\u989d", "\u5269\u4f59\u540d\u989d",
                        "\u53ef\u6295\u7a3f\u6b21\u6570", "\u5269\u4f59\u53ef\u6295\u7a3f",
                        "\u5269\u4f59\u91cf", "\u5269\u4f59\u4f4d"),
    "order_id": ("\u8ba2\u5355\u53f7", "\u8ba2\u5355ID", "order_id", "orderId"),
    "task_id": ("\u4efb\u52a1ID", "task_id", "taskId"),
}
_LABEL_TO_FIELD = {label: field for field, labels in _LABELS.items()
                   for label in labels}
_GENERIC_TASK_LABEL = "\u4efb\u52a1"


class XingtuError(Exception):
    """Base class for a Xingtu operation that must stop the publish."""


class XingtuTaskUnavailable(XingtuError):
    """The backend list could not be read or yielded no attributable tasks."""


class XingtuNotSignedIn(XingtuTaskUnavailable):
    """The backend showed a login page; the operator must sign in again."""


class XingtuTaskListEmpty(XingtuTaskUnavailable):
    """The backend loaded a real task list, but it contained no tasks."""


class XingtuTaskDetailUnreadable(XingtuTaskUnavailable):
    """Task rows exist, but their detail pages did not yield an order id."""


class XingtuTaskNotAttached(XingtuError):
    """The upload page does not show the selected task; never click publish."""


class XingtuAlreadySubmitted(XingtuError):
    """This order id + video already appears in the task submission list."""


class XingtuDuplicateCheckUnavailable(XingtuError):
    """The duplicate check could not be completed; do not risk a second submit."""


class XingtuDuplicateLocal(GateRed):
    """The local ledger already contains this task name or order id."""

    code = "xingtu.duplicate_local"

    def __init__(self, task_name, matched=None):
        matched = matched if isinstance(matched, dict) else {}
        name = _text(task_name) or _text(matched.get("task_name")) \
            or _text(matched.get("order_id"))
        self.matched = matched
        super().__init__(
            "xingtu.duplicate_local: 本地已投过同名任务 " + name,
            code=self.code)


class XingtuDedupLedgerError(GateRed):
    """The local used-task ledger is unreadable or unwritable; fail closed."""

    code = "xingtu.dedup.ledger_error"

    def __init__(self, message, code=None):
        if code:
            self.code = str(code)
        super().__init__("xingtu.dedup.ledger_error: " + str(message),
                         code=self.code)


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _normal(value) -> str:
    return re.sub(r"\s+", "", _text(value)).replace(":", "").replace("\uff1a", "")


def normalize_task_name(value) -> str:
    """Normalize a task name for strict equality, never substring matching."""
    text = _text(value).replace("\u200b", "")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D_]", "-", text)
    return re.sub(r"^\u4efb\u52a1[:\uff1a]?", "", text)


def normalize_order_id(value) -> str:
    """Normalize an order id for ledger comparison."""
    text = unicodedata.normalize("NFKC", _text(value)).replace("\u200b", "")
    return re.sub(r"\s+", "", text)


def used_tasks_path(layout) -> Path:
    """Return the ledger path under the publish-worker ``run`` directory."""
    run_dir = getattr(layout, "run", None) if layout is not None else None
    if run_dir is None:
        raise XingtuDedupLedgerError("publish data run directory unavailable")
    return Path(run_dir) / USED_TASKS_FILENAME


def _empty_ledger() -> dict:
    return {"version": USED_TASKS_VERSION, "tasks": []}


def _ledger_label(path) -> str:
    """Return a log-safe ledger name; never expose the absolute path."""
    name = os.path.basename(str(path).rstrip("/\\"))
    return name or "<ledger>"


def _ledger_error_text(path, exc) -> str:
    """Strip the full ledger path from an exception message."""
    full = str(path)
    text = str(exc)
    if full:
        text = text.replace(full, _ledger_label(path))
    return text


class _UsedTasksLock:
    """Cross-process exclusive lock held for the whole read-modify-write."""

    def __init__(self, path, timeout=None):
        self.path = Path(path)
        self.lock_path = Path(str(path) + ".lock")
        self.timeout = (USED_TASKS_LOCK_TIMEOUT_SECONDS if timeout is None
                        else max(0.0, float(timeout)))
        self.handle = None
        self._mode = ""
        self._owned_path = False

    def _try_lock(self):
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._mode = "fcntl"
            return
        if msvcrt is not None:
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            self._mode = "msvcrt"
            return
        fd = os.open(str(self.lock_path),
                     os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        self._owned_path = True
        self._mode = "exclusive"

    def _unlock(self):
        try:
            if self._mode == "fcntl" and fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            elif self._mode == "msvcrt" and msvcrt is not None:
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            if self._owned_path:
                try:
                    self.lock_path.unlink()
                except OSError:
                    pass
                self._owned_path = False

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            if fcntl is not None or msvcrt is not None:
                self.handle = self.lock_path.open("a+b")
                if msvcrt is not None:
                    self.handle.seek(0, os.SEEK_END)
                    if self.handle.tell() == 0:
                        self.handle.write(b"\0")
                        self.handle.flush()
        except Exception as exc:
            self._close_handle()
            raise XingtuDedupLedgerError(
                "cannot open lock %s: %s" % (
                    _ledger_label(self.lock_path),
                    _ledger_error_text(self.lock_path, exc)),
                code="xingtu.dedup.ledger_lock_error") from exc
        while True:
            try:
                self._try_lock()
                return self
            except OSError as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._close_handle()
                    raise XingtuDedupLedgerError(
                        "ledger lock timeout on %s after %.1fs: %s" % (
                            _ledger_label(self.lock_path), self.timeout,
                            _ledger_error_text(self.lock_path, exc)),
                        code="xingtu.dedup.ledger_lock_timeout") from exc
                time.sleep(min(USED_TASKS_LOCK_POLL_SECONDS, remaining))

    def _close_handle(self):
        if self.handle is not None:
            try:
                self.handle.close()
            except OSError:
                pass
            self.handle = None

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._mode:
                self._unlock()
        finally:
            self._mode = ""
            self._close_handle()
        return False


def _write_ledger_atomic(path, payload) -> None:
    """Write JSON through a temp file in the same directory, then os.replace."""
    path = Path(path)
    tmp_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    except (OSError, TypeError, ValueError) as exc:
        raise XingtuDedupLedgerError(
            "cannot write %s: %s" % (
                _ledger_label(path), _ledger_error_text(path, exc))) from exc
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _load_used_tasks(path) -> dict:
    """Read and validate the ledger; caller must hold the ledger lock."""
    path = Path(path)
    try:
        if not path.exists():
            payload = _empty_ledger()
            _write_ledger_atomic(path, payload)
            return payload
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except XingtuDedupLedgerError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise XingtuDedupLedgerError(
            "cannot read %s: %s" % (
                _ledger_label(path), _ledger_error_text(path, exc))) from exc
    if not isinstance(payload, dict):
        raise XingtuDedupLedgerError(
            "%s is not a JSON object" % _ledger_label(path))
    if payload.get("version") != USED_TASKS_VERSION:
        raise XingtuDedupLedgerError(
            "%s has unsupported version %r" % (
                _ledger_label(path), payload.get("version")))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise XingtuDedupLedgerError(
            "%s tasks is not a list" % _ledger_label(path))
    for entry in tasks:
        if not isinstance(entry, dict):
            raise XingtuDedupLedgerError(
                "%s contains a non-object task entry" % _ledger_label(path))
        if not isinstance(entry.get("task_name", ""), str) or \
                not isinstance(entry.get("order_id", ""), str):
            raise XingtuDedupLedgerError(
                "%s contains an invalid task entry" % _ledger_label(path))
        if "media_sha256" in entry and \
                not isinstance(entry.get("media_sha256"), str):
            raise XingtuDedupLedgerError(
                "%s contains an invalid media fingerprint" % _ledger_label(path))
    return payload


def load_used_tasks(path) -> dict:
    """Read and validate the ledger; create the empty ledger when absent."""
    path = Path(path)
    with _UsedTasksLock(path):
        return _load_used_tasks(path)


def find_used_task(path, task, media_sha256="") -> tuple[dict, str] | tuple[None, str]:
    """Return ``(entry, matched_by)`` when this task was already published.

    ``task_name`` is often a campaign keyword (for example ``APP种草``) that
    several videos in the same batch share, so a name match alone must never
    block a publish.  A duplicate is the same task identity carrying the same
    media fingerprint; legacy entries without a fingerprint keep blocking only
    on an exact order id, the narrowest safe fallback.
    """
    payload = load_used_tasks(path)
    task = task if isinstance(task, dict) else {}
    target_name = normalize_task_name(task.get("task_name"))
    target_order = normalize_order_id(task.get("order_id"))
    target_media = normalize_order_id(media_sha256)
    for entry in payload["tasks"]:
        entry_name = normalize_task_name(entry.get("task_name"))
        entry_order = normalize_order_id(entry.get("order_id"))
        entry_media = normalize_order_id(entry.get("media_sha256"))
        same_name = bool(target_name and entry_name and target_name == entry_name)
        same_order = bool(target_order and entry_order and target_order == entry_order)
        if not (same_name or same_order):
            continue
        matched_by = "order_id" if same_order else "task_name"
        if target_media and entry_media:
            if target_media == entry_media:
                return entry, matched_by + "+media"
            continue
        if not entry_media:
            if same_order:
                return entry, "order_id"
            continue
        return entry, matched_by
    return None, ""


def append_used_task(path, task, *, attempt_id="", published_at=None,
                     media_sha256="") -> dict:
    """Append one successful publish to the ledger with an atomic write."""
    path = Path(path)
    with _UsedTasksLock(path):
        payload = _load_used_tasks(path)
        task = task if isinstance(task, dict) else {}
        entry = {
            "task_name": _text(task.get("task_name")),
            "order_id": _text(task.get("order_id")),
            "media_sha256": _text(media_sha256).lower(),
            "published_at": _text(published_at) or datetime.now(
                timezone.utc).replace(microsecond=0).isoformat().replace(
                    "+00:00", "Z"),
            "attempt_id": _text(attempt_id),
        }
        payload["tasks"].append(entry)
        _write_ledger_atomic(path, payload)
        return entry


# Shared browser-side definition used by both the backend read-back click and
# the publish-page picker/read-back.  The name is the visible card text after
# removing recognised action controls and recognised metadata fields.  Only
# CSS-visual hiding is treated as hidden: aria-hidden text still participates,
# so it cannot be used to append a visible suffix.  CSS-generated content and
# shadow roots cannot be compared from the text tree, so such cards fail
# closed.
XINGTU_VISIBLE_CARD_NAME_JS = r"""
  const __xingtuNormalize = value => {
    let text = String(value || '').replace(/\u200b/g, '');
    try { text = text.normalize('NFKC'); } catch (err) {}
    text = text.replace(/\s+/g, '')
        .replace(/[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D_]/g, '-')
        .replace(/^任务[:\uff1a]?/, '');
    return text;
  };
  const __xingtuVisible = el => {
    if (!el) return false;
    try {
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' ||
          Number(style.opacity || 1) === 0) return false;
    } catch (err) {
      return false;
    }
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  };
  const __xingtuMetaFields = ['客户名称', '需求方名称', '客户方', '需求方',
      '任务类型', '剩余额度', '任务状态', '任务时间', '发布时间', '创建时间',
      '更新时间', '客户', '状态', '时间'];
  const __xingtuMetaField = '(?:' + __xingtuMetaFields.join('|') + ')';
  const __xingtuEscapeReg = value => String(value || '')
      .replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const __xingtuMetaValuePattern = label => {
    if (label === '时间' || /时间$/.test(label)) {
      return '(?:\\d{4}[-/.年]\\d{1,2}[-/.月]\\d{1,2}日?'
          + '(?:\\s+\\d{1,2}:\\d{2}(?::\\d{2})?)?'
          + '|\\d{1,2}:\\d{2}(?::\\d{2})?)';
    }
    if (label.indexOf('额度') >= 0) return '\\d+(?:\\.\\d+)?';
    return '\\S+';
  };
  const __xingtuControlWords = ['更换', '删除', '查看详情', '取消', '确定'];
  const __xingtuIsControl = el => {
    if (!el) return false;
    const text = __xingtuNormalize(el.innerText || el.textContent || '');
    return !!text && __xingtuControlWords.indexOf(text) >= 0;
  };
  const __xingtuHasHiddenAncestor = (el, card) => {
    for (let node = el; node && node !== card.parentElement;
         node = node.parentElement) {
      if (node === card) break;
      try {
        const style = window.getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden' ||
            Number(style.opacity || 1) === 0) return true;
      } catch (err) {
        return true;
      }
      const tag = String(node.tagName || '').toLowerCase();
      if (tag === 'script' || tag === 'style' || tag === 'template' ||
          tag === 'noscript') return true;
    }
    return false;
  };
  const __xingtuControlAncestor = (node, card) => {
    for (let el = node.parentElement; el && el !== card.parentElement;
         el = el.parentElement) {
      if (el === card) break;
      if (__xingtuIsControl(el)) return el;
    }
    return null;
  };
  const __xingtuVisibleNodes = card => {
    if (!card) return [];
    const out = [];
    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || !__xingtuVisible(parent)) continue;
      if (__xingtuHasHiddenAncestor(parent, card)) continue;
      if (__xingtuControlAncestor(node, card)) continue;
      out.push({node: node, el: parent, text: node.nodeValue || ''});
    }
    return out;
  };
  const __xingtuVisibleChunks = card =>
      __xingtuVisibleNodes(card).map(item => item.text);
  const __xingtuVisibleText = card =>
      __xingtuVisibleChunks(card).join('');
  const __xingtuMetaLabelOnly = value => {
    const text = String(value || '').trim();
    for (const label of __xingtuMetaFields) {
      if (new RegExp('^' + __xingtuEscapeReg(label)
              + '\\s*[:：]?\\s*$').test(text)) return label;
    }
    return '';
  };
  const __xingtuMetaLabelInText = value => {
    const text = String(value || '');
    return new RegExp('(?:' + __xingtuMetaFields.map(__xingtuEscapeReg).join('|')
        + ')\\s*[:：]').test(text);
  };
  const __xingtuInlineMetadata = value => {
    // Same text node: only remove label + a value with a recognised shape.
    // Anything else is unassignable and must leave the card name non-empty.
    const text = String(value || '');
    for (const label of __xingtuMetaFields) {
      const field = __xingtuEscapeReg(label);
      const shape = __xingtuMetaValuePattern(label);
      let match = text.match(new RegExp(
          '^\\s*' + field + '\\s*[:：]\\s*(' + shape + ')\\s*$'));
      if (match) return {kept: '', label: label};
      match = text.match(new RegExp(
          '^(.*?\\S)\\s*' + field + '\\s*[:：]\\s*(' + shape + ')\\s*$'));
      if (match) return {kept: match[1], label: label};
    }
    return null;
  };
  const __xingtuMetaValueOwned = (label, value) => {
    const text = String(value || '').trim();
    if (!text) return false;
    return new RegExp('^' + __xingtuMetaValuePattern(label) + '$').test(text);
  };
  const __xingtuSameContainer = (left, right) => !!left && !!right &&
      (left === right || left.parentElement === right.parentElement ||
       left === right.parentElement || right === left.parentElement);
  const __xingtuCardNameChunks = card => {
    const nodes = __xingtuVisibleNodes(card);
    const skipped = new Set();
    let unresolved = false;
    for (let index = 0; index < nodes.length; index++) {
      if (skipped.has(index)) continue;
      const item = nodes[index];
      const inline = __xingtuInlineMetadata(item.text);
      if (inline) {
        item.text = inline.kept;
        continue;
      }
      const label = __xingtuMetaLabelOnly(item.text);
      if (!label) {
        if (__xingtuMetaLabelInText(item.text)) unresolved = true;
        continue;
      }
      let valueIndex = index + 1;
      while (valueIndex < nodes.length &&
             !String(nodes[valueIndex].text || '').trim()) valueIndex++;
      if (valueIndex >= nodes.length) {
        unresolved = true;
        continue;
      }
      const value = nodes[valueIndex];
      if (__xingtuMetaLabelOnly(value.text) ||
          !__xingtuMetaValueOwned(label, value.text) ||
          !__xingtuSameContainer(item.el, value.el)) {
        unresolved = true;
        continue;
      }
      skipped.add(index);
      skipped.add(valueIndex);
      index = valueIndex;
    }
    if (unresolved) return [];
    return nodes.filter((_item, index) => !skipped.has(index))
        .map(item => item.text);
  };
  const __xingtuInsideControl = (el, card) => {
    for (let node = el; node && node !== card.parentElement;
         node = node.parentElement) {
      if (node !== card && __xingtuIsControl(node)) return true;
      if (node === card) break;
    }
    return false;
  };
  const __xingtuPseudoHasContent = value => {
    const text = String(value || '').trim();
    return !(text === '' || text === 'none' || text === 'normal' ||
             text === '""' || text === "''" || text === 'initial' ||
             text === 'inherit');
  };
  const __xingtuNameUnsafe = card => {
    if (!card) return true;
    const nodes = [card].concat(Array.from(card.querySelectorAll('*')));
    for (const el of nodes) {
      if (el !== card && __xingtuInsideControl(el, card)) continue;
      if (el !== card && __xingtuHasHiddenAncestor(el, card)) continue;
      if (!__xingtuVisible(el)) continue;
      if (el.shadowRoot) return true;
      try {
        if (__xingtuPseudoHasContent(
                window.getComputedStyle(el, '::before').content) ||
            __xingtuPseudoHasContent(
                window.getComputedStyle(el, '::after').content)) {
          return true;
        }
      } catch (err) {
        return true;
      }
    }
    return false;
  };
  const __xingtuCardName = card => {
    if (!card || __xingtuNameUnsafe(card)) return '';
    return __xingtuNormalize(__xingtuCardNameChunks(card).join(''));
  };
  const __xingtuOrderAttrs = [
    'data-order-id', 'data-orderid', 'data-order', 'data-order_id',
    'data-task-id', 'data-taskid', 'data-task_id'
  ];
  const __xingtuOrderValuesShallow = el => {
    const out = [];
    if (!el || !el.getAttribute) return out;
    for (const name of __xingtuOrderAttrs) {
      const value = String(el.getAttribute(name) || '').trim();
      if (value) out.push(value);
    }
    if (String(el.tagName || '').toLowerCase() === 'a') {
      try {
        const url = new URL(el.href, window.location.href);
        for (const key of ['order_id', 'orderId', 'task_id', 'taskId']) {
          const value = String(url.searchParams.get(key) || '').trim();
          if (value) out.push(value);
        }
      } catch (err) {}
    }
    return out;
  };
  const __xingtuUnique = values => Array.from(new Set(values));
  const __xingtuOrderValuesDeep = root => {
    if (!root) return [];
    const out = [];
    const nodes = [root].concat(Array.from(root.querySelectorAll('*')));
    for (const el of nodes) out.push(...__xingtuOrderValuesShallow(el));
    return __xingtuUnique(out);
  };
  const __xingtuCardOrderIds = card => {
    const out = __xingtuOrderValuesDeep(card);
    for (let node = card && card.parentElement;
         node && node !== document.body;
         node = node.parentElement) {
      const own = __xingtuOrderValuesShallow(node);
      if (own.length) {
        out.push(...own);
        break;
      }
    }
    return __xingtuUnique(out);
  };
"""


def _label_field(line: str) -> str | None:
    norm = _normal(line)
    if not norm:
        return None
    for label, field in sorted(_LABEL_TO_FIELD.items(),
                               key=lambda item: len(item[0]), reverse=True):
        label_norm = _normal(label)
        # The bare "\u4efb\u52a1" label must match exactly: list tables also render
        # "\u4efb\u52a1\u65f6\u95f4" / "\u4efb\u52a1\u72b6\u6001", which are not the task name.
        if norm == label_norm or (label_norm != _GENERIC_TASK_LABEL
                                  and norm.startswith(label_norm)):
            return field
    return None


def _label_value_inline(line: str) -> tuple[str, str] | None:
    text = _text(line)
    for sep in (":", "\uff1a"):
        if sep in text:
            left, right = text.split(sep, 1)
            field = _label_field(left)
            if field and _text(right):
                return field, _text(right)
    return None


def _is_action(line: str) -> bool:
    norm = _normal(line)
    return any(norm == _normal(word) or norm.endswith(_normal(word))
               for word in _ACTION_WORDS)


def parse_value_above(lines) -> dict:
    """Parse indicator cards whose value sits ABOVE its label.

    ``lines`` is one card's visible text, top to bottom.  For every recognised
    label the value is the nearest non-empty line above it that is not itself a
    label or an action button.  A label followed by its value on the same line
    (``name: value``) is also accepted because some backends render it that way.
    """
    rows = [_text(line) for line in (lines or []) if _text(line)]
    out: dict[str, str] = {}
    used: set[int] = set()
    for index, line in enumerate(rows):
        inline = _label_value_inline(line)
        if inline:
            field, value = inline
            out.setdefault(field, value)
            continue
        field = _label_field(line)
        if not field:
            continue
        for back in range(index - 1, -1, -1):
            if back in used:
                continue
            candidate = rows[back]
            if _label_field(candidate) or _is_action(candidate):
                continue
            out.setdefault(field, candidate)
            used.add(back)
            break
    return out


def extract_order_id(value) -> str:
    """Return an order id from a URL, href, attribute text or plain token."""
    text = _text(value)
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        query = parse_qs(parsed.query or "")
        for key in ("order_id", "orderId", "orderid",
                    "task_id", "taskId", "taskid"):
            hits = query.get(key) or []
            if hits and _text(hits[0]):
                return _text(hits[0])
    except Exception:
        pass
    match = _ORDER_RE.search(text)
    if match:
        return _text(match.group(1))
    match = _DETAIL_ID_RE.search(text)
    if match:
        return _text(match.group(1))
    if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", text):
        return text
    return ""


def _detail_name(lines) -> str:
    """Task name from a detail page: creative description first, else title."""
    rows = [_text(line) for line in (lines or []) if _text(line)]
    for index, line in enumerate(rows):
        for label in _DETAIL_NAME_LABELS:
            label_norm = _normal(label)
            for sep in (":", "\uff1a"):
                if sep in line:
                    left, right = line.split(sep, 1)
                    if _normal(left) == label_norm and _text(right):
                        return _text(right)
            if _normal(line) == label_norm and index + 1 < len(rows):
                candidate = rows[index + 1]
                if not _label_field(candidate) and not _is_action(candidate):
                    return candidate
    for line in rows[:3]:
        if line.endswith(" - \u5de8\u91cf\u661f\u56fe"):
            candidate = _text(line[:-len(" - \u5de8\u91cf\u661f\u56fe")])
            if _normal(candidate) not in ("\u4efb\u52a1\u8be6\u60c5",
                                          "\u4efb\u52a1\u8be6\u60c5\u9875"):
                return candidate
    return ""


def _detail_remaining(lines, text) -> str:
    """Remaining submission quota from the detail page text."""
    rows = [_text(line) for line in (lines or []) if _text(line)]
    patterns = (
        r"\u5269\u4f59\u6295\u7a3f\s*[:\uff1a]?\s*(\d+)\s*\u6761?",
        r"\u5269\u4f59\u53ef\u6295\u7a3f\s*[:\uff1a]?\s*(\d+)",
        r"\u5269\u4f59(?:\u6295\u7a3f)?(?:\u6b21\u6570|\u989d\u5ea6|\u914d\u989d)?"
        r"\s*[:\uff1a]?\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            return _text(match.group(1))
    for index, line in enumerate(rows):
        if _normal(line) in ("\u5269\u4f59\u6295\u7a3f", "\u5269\u4f59\u914d\u989d",
                             "\u5269\u4f59\u540d\u989d") and index + 1 < len(rows):
            match = re.fullmatch(r"\d+", _text(rows[index + 1]))
            if match:
                return _text(rows[index + 1])
    return ""


def _detail_can_submit(lines) -> bool:
    """True when the detail page exposes a submit button label."""
    rows = [_text(line) for line in (lines or []) if _text(line)]
    for line in rows:
        norm = _normal(line)
        if norm in _SUBMIT_ACTION_WORDS:
            return True
        if len(norm) <= 12 and any(norm.startswith(word)
                                   for word in _SUBMIT_ACTION_WORDS):
            return True
    return False


def parse_detail_task(url, text) -> dict:
    """Parse one Xingtu task detail page from its URL and visible innerText.

    The list page often carries no order id.  Opening "view details" gives a
    URL whose ``task_id`` (also called ``order_id``) is the id the Douyin
    upload page needs, while the page text carries the real task name and the
    remaining submission quota.  This function is deliberately browser-free so
    the real detail fixture can be checked offline.
    """
    url = _text(url)
    raw = _text(text)
    rows = [_text(line) for line in re.split(r"\r?\n", raw) if _text(line)]
    order_id = extract_order_id(url)
    task_id = order_id
    if not order_id:
        body_match = _DETAIL_ID_LINE_RE.search(raw)
        if body_match:
            order_id = _text(body_match.group(1))
            task_id = order_id
    task_name = _detail_name(rows)
    remaining = _detail_remaining(rows, raw)
    buttons = [line for line in rows if _detail_can_submit([line])]
    return {
        "task_name": task_name,
        "demander": "",
        "task_type": "",
        "remaining_quota": remaining,
        "order_id": order_id,
        "task_id": task_id,
        "upload_url": "",
        "lines": rows,
        "index": None,
        "buttons": buttons,
        "can_submit": _detail_can_submit(rows),
    }


def _first_line(lines) -> str:
    for line in lines or []:
        text = _text(line)
        if not text or _label_field(text) or _is_action(text):
            continue
        return text
    return ""


def row_video_status(lines) -> str:
    """Return the row's video status without depending on row-local buttons."""
    rows = [_text(line) for line in (lines or []) if _text(line)]
    for wanted in _ROW_VIDEO_STATUSES:
        wanted_norm = _normal(wanted)
        if any(_normal(line) == wanted_norm for line in rows):
            return wanted
    for line in rows:
        line_norm = _normal(line)
        for wanted in _ROW_VIDEO_STATUSES:
            if _normal(wanted) in line_norm:
                return wanted
    return ""


def _task_info_name(card: dict) -> str:
    """Task name from the list's ``\u4efb\u52a1\u4fe1\u606f`` block, in row order."""
    card = card if isinstance(card, dict) else {}
    for key in ("task_name", "name", "title"):
        value = _text(card.get(key))
        if value:
            return value
    info = card.get("task_info")
    if isinstance(info, dict):
        for key in ("task_name", "name", "title", "text"):
            value = _text(info.get(key))
            if value:
                return value
    elif isinstance(info, (list, tuple)):
        for value in info:
            value = _text(value)
            if value:
                return value
    cells = card.get("cells") or []
    if cells:
        value = _first_line(re.split(r"\r?\n", _text(cells[0])))
        if value:
            return value
    return _first_line(card.get("lines") or [])


def parse_card(card: dict) -> dict:
    """Turn one raw card (``lines``/``hrefs``/``attrs``) into a task dict."""
    card = card if isinstance(card, dict) else {}
    lines = list(card.get("lines") or [])
    values = parse_value_above(lines)
    order_id = _text(values.get("order_id"))
    upload_url = ""
    for href in card.get("hrefs") or []:
        found = extract_order_id(href)
        if found:
            order_id = order_id or found
            if "creator.douyin.com" in _text(href):
                upload_url = _text(href)
    for attr in card.get("attrs") or []:
        found = extract_order_id(attr)
        if found:
            order_id = order_id or found
    for line in lines:
        found = extract_order_id(line)
        if found:
            order_id = order_id or found
    task = {
        "task_name": (_task_info_name(card) or _text(values.get("task_name"))
                      or _first_line(lines)),
        "demander": _text(values.get("demander")),
        "task_type": _text(values.get("task_type")),
        "remaining_quota": _text(values.get("remaining_quota")),
        "status": (_text(card.get("status")) or row_video_status(lines)),
        "order_id": order_id,
        "task_id": _text(values.get("task_id")),
        "upload_url": upload_url,
        "lines": lines,
        "index": card.get("index"),
        "buttons": list(card.get("buttons") or []),
    }
    return task


def task_available(task: dict) -> bool:
    if task.get("can_submit") is False:
        return False
    text = " ".join(_text(task.get(key)) for key in
                    ("task_name", "remaining_quota", "task_type", "lines"))
    if any(word in text for word in _UNAVAILABLE_WORDS):
        return False
    quota = _text(task.get("remaining_quota"))
    if quota and re.fullmatch(r"\d+", quota) and int(quota) <= 0:
        return False
    return bool(_text(task.get("task_name")))


def dedupe_tasks(tasks) -> list:
    out, seen = [], set()
    for task in tasks or []:
        if not task_available(task):
            continue
        key = (_text(task.get("order_id")), _normal(task.get("task_name")))
        if key in seen:
            continue
        seen.add(key)
        out.append(task)
    return out


def parse_task_cards(cards, *, task_names=None) -> list:
    """Parse list rows and align task names by row order.

    The list's first column is headed ``\u4efb\u52a1\u4fe1\u606f``.  Its visible task
    title is the authoritative list-side name; the customer column is not.
    ``task_names`` lets a caller pass the column's names separately while
    keeping row order.  Detail-page names are checked later by
    :func:`_detail_from_row`.
    """
    raw = list(cards or [])
    names = list(task_names or [])
    tasks = []
    for index, card in enumerate(raw):
        card = card if isinstance(card, dict) else {}
        name = _text(names[index]) if index < len(names) else ""
        name = name or _task_info_name(card)
        source = dict(card)
        if name:
            source["task_name"] = name
        task = parse_card(source)
        if name:
            task["task_name"] = name
        tasks.append(task)
    return dedupe_tasks(tasks)


def match_xingtu_task_name(value) -> str:
    """Map a material file name/path to a task name from the fixed labels.

    The rule is the same one used by the Feishu publishing bot: the first
    matching label wins, with the more specific ``APP\u79cd\u8349`` checked before the
    generic ``\u79cd\u8349`` keyword.  An unmatched name returns ``""``; callers must
    not guess a task.
    """
    text = _normal(value).upper()
    if not text:
        return ""
    for label, keywords in XINGTU_TASK_LABELS:
        for keyword in keywords:
            if _normal(keyword).upper() in text:
                return label
    return ""


def _plan_material_names(plan: dict) -> list:
    plan = plan if isinstance(plan, dict) else {}
    piece = plan.get("piece") if isinstance(plan.get("piece"), dict) else {}
    task = plan.get("xingtu_task") if isinstance(plan.get("xingtu_task"), dict) else {}
    names = []
    for source in (piece, plan, task):
        for key in ("file_name", "media_path", "file_path", "path",
                    "material_name"):
            value = _text(source.get(key))
            if value:
                names.append(value)
    return names


def derive_xingtu_task_name(plan: dict) -> str:
    """Derive one task name from the material file name, or return ``""``.

    Multiple different labels are ambiguous and therefore not derived: the
    publish must stay blocked instead of picking one at random.
    """
    labels = []
    for name in _plan_material_names(plan):
        label = match_xingtu_task_name(name)
        if label and label not in labels:
            labels.append(label)
    return labels[0] if len(labels) == 1 else ""


def skip_fill_task(plan: dict, mode=None) -> bool:
    """An explicitly empty task name is allowed only for a fill-only run."""
    task = (plan or {}).get("xingtu_task")
    return (str(mode or "") == "fill" and isinstance(task, dict)
            and not normalize_task_name(task.get("task_name")))


def match_picker_rows(rows, task):
    """Return visible matches in DOM order, preferring order ids over titles."""
    order_id = str((task or {}).get("order_id") or "").strip()
    expected = normalize_task_name((task or {}).get("task_name"))
    visible = [row for row in rows if row.get("visible")]
    if order_id:
        exact = []
        for row in visible:
            order_ids = list(row.get("order_ids") or [])
            if (len(order_ids) == 1 and
                    str(order_ids[0] or "").strip() == order_id):
                exact.append(row)
        if exact:
            return {"rows": exact, "reason": "order_id"}
    matched = []
    if expected:
        for row in visible:
            titles = [normalize_task_name(value)
                      for value in (row.get("titles") or [])]
            if expected not in titles:
                continue
            order_ids = list(row.get("order_ids") or [])
            if order_id and order_ids:
                if (len(order_ids) != 1 or
                        str(order_ids[0] or "").strip() != order_id):
                    continue
            matched.append(row)
    return {"rows": matched, "reason": "title"}


def click_picker_element(item) -> bool:
    """Click the DOM element itself, never a possibly covered coordinate."""
    try:
        if not item.is_visible() or not item.is_enabled():
            return False
        if item.get_attribute("aria-disabled") == "true":
            return False
        try:
            item.dispatch_event("click", timeout=2000)
        except TypeError:
            item.dispatch_event("click")
        return True
    except Exception:
        try:
            return bool(item.evaluate("""el => {
                if (!el.isConnected || el.disabled ||
                    el.getAttribute('aria-disabled') === 'true' ||
                    !el.getClientRects().length) return false;
                el.click(); return true;
            }"""))
        except Exception:
            return False


def task_from_plan(plan: dict, *, mode=None) -> dict:
    """Return the selected task, or an empty dict for a normal publish.

    A task name alone is a valid Xingtu selection: the task is chosen inside
    the Douyin publish page, where that name is searched in the task picker.
    A plan that claims to be a Xingtu publish with neither an order id nor a
    task name is still invalid and raises instead of degrading into a normal
    Douyin publish. Fill-only calls may skip an explicitly empty task name.
    """
    plan = plan if isinstance(plan, dict) else {}
    if skip_fill_task(plan, mode):
        return {}
    explicit = (str(plan.get("publish_mode") or "") == "xingtu"
                or "xingtu_task" in plan or "xingtu" in plan)
    task = plan.get("xingtu_task") or plan.get("xingtu")
    if isinstance(task, dict):
        cleaned = {key: _text(task.get(key)) for key in
                   ("order_id", "task_name", "demander", "task_type",
                    "remaining_quota", "task_id", "upload_url")}
        cleaned["mode"] = "xingtu"
        if not cleaned.get("order_id"):
            cleaned["order_id"] = _text(plan.get("order_id"))
        if not cleaned.get("task_name"):
            cleaned["task_name"] = _text(plan.get("xingtu_task_name"))
        if not cleaned.get("task_name"):
            derived = derive_xingtu_task_name(plan)
            if derived:
                cleaned["task_name"] = derived
                cleaned["name_source"] = "material"
        if cleaned.get("order_id") or cleaned.get("task_name"):
            return cleaned
        if explicit:
            raise XingtuTaskNotAttached(
                "xingtu publish plan has neither order_id nor task_name; "
                "refusing normal publish")
        return {}
    order_id = _text(plan.get("order_id"))
    task_name = _text(plan.get("xingtu_task_name"))
    derived_name = ""
    if not task_name:
        derived_name = derive_xingtu_task_name(plan)
        if derived_name:
            task_name = derived_name
    if (order_id or task_name) and str(plan.get("publish_mode") or "") == "xingtu":
        result = {"order_id": order_id, "task_name": task_name,
                  "demander": "", "task_type": "", "remaining_quota": "",
                  "task_id": "", "upload_url": "", "mode": "xingtu"}
        if derived_name:
            result["name_source"] = "material"
        return result
    if explicit and not order_id and not task_name:
        derived = derive_xingtu_task_name(plan)
        if derived:
            return {"order_id": "", "task_name": derived, "demander": "",
                    "task_type": "", "remaining_quota": "", "task_id": "",
                    "upload_url": "", "mode": "xingtu",
                    "name_source": "material"}
        raise XingtuTaskNotAttached(
            "xingtu publish plan has neither order_id nor task_name; "
            "refusing normal publish")
    return {}


def xingtu_upload_url(task: dict) -> str:
    """The Douyin entry page for the selected task.

    With an order id the upload page keeps that id in its query string.  Name
    only selections use the ordinary publish page: the task is picked there,
    so no Xingtu backend list or order id is required.
    """
    order_id = _text((task or {}).get("order_id"))
    if not order_id:
        return DOUYIN_PUBLISH_URL
    upload_url = _text((task or {}).get("upload_url"))
    if upload_url:
        parsed = urlparse(upload_url)
        host = (parsed.hostname or "").lower()
        if host == "creator.douyin.com":
            ids = parse_qs(parsed.query or "").get("order_id") or []
            if ids and _text(ids[0]) == order_id:
                return upload_url
        raise XingtuTaskUnavailable(
            "xingtu entry is not a confirmed Douyin upload link")
    return DOUYIN_UPLOAD_URL + "?order_id=" + quote(order_id, safe="")


def page_has_task(page_text: str, task: dict) -> bool:
    """True only when the selected task name is visible on the upload page."""
    name = _normal((task or {}).get("task_name"))
    body = _normal(page_text)
    if len(name) < 2 or not body:
        return False
    return name in body


def submission_status(text: str, task: dict, *, title: str = "",
                      work_id: str = "") -> str:
    """FOUND / NOT_FOUND / UNKNOWN from a task detail page's visible text."""
    body = _normal(text)
    if not body:
        return STATUS_UNKNOWN
    if work_id and _normal(work_id) in body:
        return STATUS_FOUND
    title_norm = _normal(title)
    # A short title is not enough evidence on a task page: the task name or a
    # generic word can contain it.  Require a real title plus a submission-page
    # marker before claiming the star order was closed.
    if len(title_norm) >= 4 and title_norm in body and any(
            marker in body for marker in (
                "\u6211\u7684\u6295\u7a3f", "\u6295\u7a3f\u8bb0\u5f55",
                "\u6295\u7a3f\u4f5c\u54c1", "\u4f5c\u54c1\u6807\u9898",
                "\u6295\u7a3f\u6210\u529f", "\u5df2\u6295\u7a3f",
                "\u5ba1\u6838\u4e2d", "\u5df2\u5b8c\u6210")):
        return STATUS_FOUND
    order_id = _normal((task or {}).get("order_id"))
    if order_id and order_id in body and any(
            marker in body for marker in ("\u6295\u7a3f\u6210\u529f", "\u5df2\u6295\u7a3f",
                                          "\u5ba1\u6838\u4e2d", "\u5df2\u5b8c\u6210")):
        return STATUS_FOUND
    if any(word in body for word in _EMPTY_SUBMISSION_WORDS):
        return STATUS_NOT_FOUND
    # A readable submission list that does not contain this video means this
    # video has not been submitted to this task yet.  That is different from an
    # unreadable page (UNKNOWN) and lets a second video use the same order.
    if any(marker in body for marker in (
            "\u6211\u7684\u6295\u7a3f", "\u6295\u7a3f\u8bb0\u5f55",
            "\u6295\u7a3f\u4f5c\u54c1", "\u4f5c\u54c1\u6807\u9898")):
        return STATUS_NOT_FOUND
    return STATUS_UNKNOWN


def finalize_readback(result: dict, readback: dict, *, mode: str = "publish") -> dict:
    """Apply the read-back verdict: only FOUND may report publish success.

    ``fill`` stops before the publish button, so no submission record exists.
    A NOT_FOUND/UNKNOWN read-back is therefore not a fill failure; only the
    publish path may turn an unconfirmed record into a failure.
    """
    result = result if isinstance(result, dict) else {}
    readback = readback if isinstance(readback, dict) else {}
    status = _text(readback.get("status")).upper() or STATUS_UNKNOWN
    result["xingtu_readback"] = readback
    result["xingtu_submission_confirmed"] = status == STATUS_FOUND
    if status == STATUS_FOUND:
        result["publish_outcome"] = "CONFIRMED"
        return result
    if str(mode or "").strip().lower() == "fill":
        result["publish_outcome"] = "FILLED"
        return result
    # The platform may have accepted the video, but the star-order loop is not
    # closed.  Keep the platform fact and refuse to call the publish successful.
    result["platform_published"] = bool(
        result.get("platform_published") or result.get("published"))
    result["published"] = False
    result["publish_outcome"] = "UNKNOWN"
    problems = list(result.get("problems") or [])
    problems.append({"code": "XINGTU_READBACK_UNKNOWN",
                     "message": "xingtu submission record could not be read back"})
    result["problems"] = problems
    return result


def _js_task_cards() -> str:
    return r"""() => {
      const out=[], seen=new Set();
      const push=(root)=>{
        if(!root || seen.has(root)) return;
        seen.add(root);
        const idx=out.length;
        root.setAttribute('data-winport-task-card', String(idx));
        const lines=(root.innerText||'').split(/\n/).map(s=>s.trim()).filter(Boolean);
        const hrefs=[...root.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')||'');
        const attrs=[];
        root.querySelectorAll('*').forEach(el=>{
          for(const a of (el.attributes||[])){
            if(/order|task|data-/i.test(a.name)) attrs.push(a.name+'='+a.value);
          }
        });
        const buttons=[...root.querySelectorAll('button,[role=button],a')]
          .map(el=>(el.innerText||'').trim()).filter(Boolean);
        out.push({index:idx, lines:lines, hrefs:hrefs, attrs:attrs, buttons:buttons});
      };
      const labels=[...document.querySelectorAll('.indicator-label')];
      for(const label of labels){
        let root=label;
        for(let i=0;i<8 && root.parentElement;i++){
          root=root.parentElement;
          if(root.querySelectorAll('.indicator-label').length>=2) break;
        }
        push(root);
      }
      if(!out.length){
        const candidates=[...document.querySelectorAll(
          '[class*=task-item],[class*=taskItem],[class*=item-list] > div,[class*=list] > div')];
        for(const node of candidates){
          const text=(node.innerText||'');
          if(text.includes('\u4efb\u52a1') || text.includes('\u9700\u6c42\u65b9')) push(node);
        }
      }
      return out;
    }"""


_JS_CLICK_CARD_TEXT = r"""(arg) => {
  const card=document.querySelector('[data-winport-task-card="'+arg.index+'"]');
  if(!card) return false;
  const nodes=[...card.querySelectorAll('button,[role=button],a')];
  let el=nodes.find(n=>(n.innerText||'').trim()===arg.text);
  if(!el) el=nodes.find(n=>(n.innerText||'').trim().includes(arg.text));
  if(!el) return false;
  el.scrollIntoView({block:'center'});
  el.click();
  return true;
}"""

_JS_CLICK_TEXT = r"""(text) => {
  const norm=s=>(s||'').replace(/\s+/g,'');
  const nodes=[...document.querySelectorAll('button,[role=button],a')];
  let el=nodes.find(n=>norm(n.innerText)===norm(text));
  if(!el) el=nodes.find(n=>norm(n.innerText).includes(norm(text)));
  if(!el) return false;
  el.scrollIntoView({block:'center'});
  el.click();
  return true;
}"""

_JS_CLICK_DETAIL_BY_TASK = r"""(name) => {
""" + XINGTU_VISIBLE_CARD_NAME_JS + r"""
  const wanted=__xingtuNormalize(name);
  const cards=[...document.querySelectorAll('[data-winport-task-card]')];
  const matches=wanted ? cards.filter(c=>__xingtuCardName(c)===wanted) : [];
  if(matches.length!==1) return false;
  const card=matches[0];
  const nodes=[...card.querySelectorAll('button,[role=button],a')];
  let el=nodes.find(n=>__xingtuNormalize(n.innerText)==='\u67e5\u770b\u8be6\u60c5');
  if(!el) return false;
  el.scrollIntoView({block:'center'});
  el.click();
  return true;
}"""


_JS_CLICK_DETAIL_BY_ORDER = r"""(order) => {
""" + XINGTU_VISIBLE_CARD_NAME_JS + r"""
  const value=String(order||'').trim();
  if(!value) return false;
  const cards=[...document.querySelectorAll('[data-winport-task-card]')];
  const matches=cards.filter(c=>{
    const ids=__xingtuCardOrderIds(c);
    return ids.length===1 && ids[0]===value;
  });
  if(matches.length!==1) return false;
  const card=matches[0];
  const nodes=[...card.querySelectorAll('button,[role=button],a')];
  let el=nodes.find(n=>(n.innerText||'').trim()==='\u67e5\u770b\u8be6\u60c5');
  if(!el) el=nodes.find(n=>(n.innerText||'').includes('\u67e5\u770b\u8be6\u60c5'));
  if(!el) return false;
  el.scrollIntoView({block:'center'});
  el.click();
  return true;
}"""


def _js_list_rows() -> str:
    """Tag real task-table rows, excluding Element UI's fixed-column clones."""
    return r"""() => {
      let rows=[...document.querySelectorAll('.el-table__body-wrapper tr.el-table__row')];
      if(!rows.length) rows=[...document.querySelectorAll('tr.el-table__row')];
      const statuses=['\u89c6\u9891\u5df2\u4e0a\u4f20','\u5f85\u4e0a\u4f20\u89c6\u9891'];
      const clean=s=>(s||'').replace(/\s+/g,' ').trim();
      const out=[];
      for(const root of rows){
        if(!root || !root.getClientRects().length) continue;
        const idx=out.length;
        root.setAttribute('data-winport-task-row', String(idx));
        const lines=(root.innerText||'').split(/\n/).map(s=>s.trim()).filter(Boolean);
        const hrefs=[...root.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')||'');
        const attrs=[];
        root.querySelectorAll('*').forEach(el=>{
          for(const a of (el.attributes||[])){
            if(/order|task|data-/i.test(a.name)) attrs.push(a.name+'='+a.value);
          }
        });
        const buttons=[...root.querySelectorAll('button,[role=button],a')]
          .map(el=>(el.innerText||'').trim()).filter(Boolean);
        const titleNode=root.querySelector('.task-title .el-popover__reference') ||
                        root.querySelector('.task-title .xt-popover__content') ||
                        root.querySelector('.task-title');
        let task_name=clean(titleNode ? (titleNode.innerText || titleNode.textContent) : '');
        if(!task_name && lines.length) task_name=lines[0];
        const statusNode=root.querySelector('.author-task-status .xt-status__extra');
        let status=clean(statusNode ? (statusNode.innerText || statusNode.textContent) : '');
        if(!status){
          for(const line of lines){
            const hit=statuses.find(s=>(line||'').replace(/\s+/g,'').includes(s));
            if(hit){ status=hit; break; }
          }
        }
        out.push({index:idx, task_name:task_name, status:status,
                  lines:lines, hrefs:hrefs, attrs:attrs, buttons:buttons});
      }
      return out;
    }"""


_JS_CLICK_ROW_DETAIL = r"""(index) => {
  const norm=s=>(s||'').replace(/\s+/g,'');
  const row=document.querySelector('[data-winport-task-row="'+index+'"]');
  if(!row) return false;
  const nodes=[...row.querySelectorAll('button,[role=button],a')];
  let el=nodes.find(n=>norm(n.innerText)==='\u67e5\u770b\u8be6\u60c5');
  if(!el) el=nodes.find(n=>norm(n.innerText).includes('\u67e5\u770b\u8be6\u60c5'));
  if(!el) return false;
  el.scrollIntoView({block:'center'});
  el.click();
  return true;
}"""


def _context_page(context):
    pages = getattr(context, "pages", None) or []
    for page in pages:
        if "xingtu.cn" in _text(getattr(page, "url", "")):
            return page
    return context.new_page()


def _goto_list(page, *, wait_ms: int = 2500):
    page.goto(CREATOR_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(wait_ms)
    page.goto(STAR_AD_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(wait_ms)
    menu = page.locator(TASK_MENU_SELECTOR)
    try:
        if menu.count() and menu.first.is_visible():
            menu.first.click()
            page.wait_for_timeout(wait_ms)
            return page
    except Exception:
        pass
    page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(wait_ms)
    return page


def _click_with_page_fallback(context, page, script, arg, *, timeout_ms=10000):
    """Click in a card and return the new tab (Chrome) or same page (WebKit)."""
    clicked = False
    try:
        with context.expect_page(timeout=timeout_ms) as opened:
            clicked = bool(page.evaluate(script, arg))
        target = opened.value
        try:
            target.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        target.wait_for_timeout(1200)
        return target, True
    except Exception:
        if not clicked:
            return None, False
        page.wait_for_timeout(1200)
        return page, True


def _entry_from_task(context, page, task, *, timeout_ms=10000):
    """Resolve order_id/upload_url by opening this task's detail/entry."""
    order_id = _text(task.get("order_id"))
    upload_url = _text(task.get("upload_url"))
    buttons = list(task.get("buttons") or [])
    index = task.get("index")
    if index is None:
        return task
    wanted = None
    for action in _ACTION_WORDS:
        if any(_normal(btn) == _normal(action) for btn in buttons):
            wanted = action
            break
    if wanted is None:
        return task
    target, clicked = _click_with_page_fallback(
        context, page, _JS_CLICK_CARD_TEXT,
        {"index": index, "text": wanted}, timeout_ms=timeout_ms)
    if not clicked or target is None:
        return task
    same_page_navigation = target is page
    close_target = target is not page
    try:
        url = _text(getattr(target, "url", ""))
        found = extract_order_id(url)
        if found:
            order_id = order_id or found
            if "creator.douyin.com" in url:
                upload_url = upload_url or url
        if not order_id and wanted != "\u53bb\u6295\u7a3f":
            entry_target, entry_clicked = _click_with_page_fallback(
                context, target, _JS_CLICK_TEXT,
                "\u53bb\u6295\u7a3f", timeout_ms=timeout_ms)
            if entry_clicked and entry_target is not None:
                entry_url = _text(getattr(entry_target, "url", ""))
                found = extract_order_id(entry_url)
                if found:
                    order_id = found
                    if "creator.douyin.com" in entry_url:
                        upload_url = entry_url
                if entry_target is not target:
                    try:
                        entry_target.close()
                    except Exception:
                        pass
                try:
                    target.bring_to_front()
                except Exception:
                    pass
    finally:
        if close_target:
            try:
                target.close()
            except Exception:
                pass
        try:
            page.bring_to_front()
        except Exception:
            pass
        if same_page_navigation:
            # WebKit navigates the list tab itself.  Restore the list and
            # re-tag its cards so the next task can still be resolved; Chrome
            # keeps the list tab untouched and does not need this.
            try:
                _goto_list(page)
                page.evaluate(_js_task_cards())
            except Exception:
                pass
    task["order_id"] = order_id
    task["upload_url"] = upload_url
    return task


def _page_text(page) -> str:
    try:
        return _text(page.inner_text("body"))
    except Exception:
        return ""


def _looks_like_login(page, text: str) -> bool:
    url = _text(getattr(page, "url", "")).lower()
    if any(token in url for token in ("login", "passport", "sso")):
        return True
    return any(word in (text or "") for word in _LOGIN_WORDS)


def _looks_like_empty_list(text: str) -> bool:
    return any(word in (text or "") for word in _EMPTY_LIST_WORDS)


def _detail_buttons(page) -> list:
    """Return whole-page buttons whose visible text is ``\u67e5\u770b\u8be6\u60c5``."""
    buttons = []
    try:
        nodes = page.query_selector_all("button")
    except Exception:
        return buttons
    for node in nodes or []:
        try:
            if _text(node.inner_text()) != _DETAIL_ACTION:
                continue
        except Exception:
            continue
        try:
            if not node.is_visible():
                continue
        except Exception:
            pass
        buttons.append(node)
    return buttons


def _new_context_pages(context, before_ids) -> list:
    pages = list(getattr(context, "pages", None) or [])
    return [page for page in pages if id(page) not in before_ids]


def _detail_from_row(context, page, task, *, timeout_ms: int = 12000) -> dict:
    """Open a row's detail page by its whole-page button position.

    On the customer machine Element UI's fixed columns make the detail button
    invisible from ``row.querySelectorAll`` even though the row itself is
    tagged.  The proven path is the Nth whole-page ``\u67e5\u770b\u8be6\u60c5`` button.
    Chrome opens it in a new tab; ``context.pages`` is re-read after a longer
    wait because the popup event can arrive after the click returns.
    """
    index = task.get("index")
    if index is None:
        return task
    try:
        row_no = int(index) + 1
    except (TypeError, ValueError):
        row_no = 1
    current_url = _text(getattr(page, "url", ""))
    buttons = _detail_buttons(page)
    if len(buttons) <= int(index):
        task["detail_error"] = (
            "row %d (index %s): expected whole-page '%s' button at index %s, "
            "found %d; current URL: %s"
            % (row_no, index, _DETAIL_ACTION, index, len(buttons), current_url))
        return task

    before_ids = {id(item) for item in (getattr(context, "pages", None) or [])}
    target = None
    same_page = False
    try:
        button = buttons[int(index)]
        try:
            button.scroll_into_view_if_needed()
        except Exception:
            pass
        try:
            try:
                button.click(timeout=timeout_ms)
            except TypeError:
                button.click()
        except Exception as exc:
            task["detail_error"] = (
                "row %d (index %s): whole-page '%s' click failed (%s: %s); "
                "current URL: %s"
                % (row_no, index, _DETAIL_ACTION, type(exc).__name__, exc,
                   current_url))
            return task

        attempts = max(2, int(timeout_ms) // 4000)
        for attempt in range(attempts):
            page.wait_for_timeout(4000 if attempt == 0 else 3000)
            fresh = _new_context_pages(context, before_ids)
            if fresh:
                with_id = [item for item in fresh
                           if extract_order_id(getattr(item, "url", ""))]
                target = (with_id or fresh)[-1]
                if extract_order_id(getattr(target, "url", "")):
                    break
                continue
            page_url = _text(getattr(page, "url", ""))
            if page_url != current_url and extract_order_id(page_url):
                target = page
                same_page = True
                break

        if target is None:
            task["detail_error"] = (
                "row %d (index %s): no new detail tab after %.1f seconds and "
                "%d context.pages read(s); current URL: %s"
                % (row_no, index, (4000 + 3000 * max(0, attempts - 1)) / 1000.0,
                   attempts, _text(getattr(page, "url", "")) or current_url))
            return task

        same_page = target is page
        try:
            target.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        target.wait_for_timeout(1200)
        url = _text(getattr(target, "url", ""))
        text = _page_text(target)
        detail = parse_detail_task(url, text)
        if not detail.get("order_id"):
            task["detail_error"] = (
                "row %d (index %s): detail page URL has no task_id/order_id: %s"
                % (row_no, index, url or "about:blank"))
            return task
        task.pop("detail_error", None)
        task["order_id"] = detail["order_id"]
        task["task_id"] = detail.get("task_id") or detail["order_id"]
        detail_name = _text(detail.get("task_name"))
        row_name = _text(task.get("task_name"))
        if detail_name:
            task["detail_name"] = detail_name
            if row_name:
                task["list_task_name"] = row_name
            row_norm = _normal(row_name)
            detail_norm = _normal(detail_name)
            if not row_name:
                task["task_name"] = detail_name
                task["name_check"] = "detail_filled_missing_row"
            elif row_norm == detail_norm:
                task["name_check"] = "match"
            elif detail_norm and row_norm.startswith(detail_norm):
                # The detail page truncates long creative descriptions.  Keep
                # the complete list-side name and record that the detail name
                # was only a prefix.
                task["name_check"] = "row_name_kept_detail_truncated"
            else:
                task["task_name"] = detail_name
                task["name_check"] = "detail_overrides_row"
        if detail.get("remaining_quota"):
            task["remaining_quota"] = detail["remaining_quota"]
        task["can_submit"] = bool(detail.get("can_submit"))
        return task
    finally:
        if target is not None and target is not page:
            try:
                target.close()
            except Exception:
                pass
        try:
            page.bring_to_front()
        except Exception:
            pass
        if same_page:
            # WebKit replaced the list tab with the detail page.  Restore and
            # re-tag the table before resolving the next row.
            try:
                _goto_list(page)
                page.evaluate(_js_list_rows())
            except Exception:
                pass


def _final_task_list(tasks, unresolved: int) -> list:
    # A single malformed row must not hide every other writable task.  At the
    # same time a list with no attributable order id is an error, never a
    # reason to fall back to a normal Douyin publish.
    writable = dedupe_tasks([task for task in (tasks or []) if task_available(task)])
    writable = [task for task in writable if task.get("order_id")]
    if writable:
        return writable
    if unresolved:
        details = [_text(task.get("detail_error")) for task in (tasks or [])
                   if _text(task.get("detail_error"))]
        detail_text = ("; " + "; ".join(details)) if details else ""
        raise XingtuTaskDetailUnreadable(
            "xingtu found %d task row(s) but could not read an order id from "
            "their detail pages%s; open a detail page manually, confirm its "
            "URL contains task_id/order_id, then retry"
            % (unresolved, detail_text))
    raise XingtuTaskUnavailable(
        "xingtu task list loaded but has no writable task (all rows are ended, "
        "full or not accepting submissions); nothing to publish")


def list_available_tasks(context, *, max_tasks: int = 20,
                         resolve_entries: bool = True) -> list:
    """Read the live Xingtu task list.  Raises instead of guessing."""
    page = _context_page(context)
    close_page = page not in (getattr(context, "pages", None) or [])
    try:
        _goto_list(page)
        limit = max(1, int(max_tasks))
        rows = page.evaluate(_js_list_rows())
        if rows:
            tasks = parse_task_cards(rows[:limit])
            unresolved = 0
            resolved = []
            for task in tasks:
                if (task_available(task) and resolve_entries
                        and not task.get("order_id")):
                    task = _detail_from_row(context, page, task)
                if task_available(task) and not task.get("order_id"):
                    unresolved += 1
                resolved.append(task)
            return _final_task_list(resolved, unresolved)

        text = _page_text(page)
        if _looks_like_login(page, text):
            raise XingtuNotSignedIn(
                "xingtu is not signed in (a login page is showing); sign in to "
                "Xingtu in this environment, then retry xingtu-tasks")
        if _looks_like_empty_list(text):
            raise XingtuTaskListEmpty(
                "xingtu task list is empty for this account; there are no "
                "tasks to publish")

        cards = page.evaluate(_js_task_cards())
        if not cards:
            raise XingtuTaskUnavailable(
                "xingtu task table was not found after loading; wait for the "
                "page to finish loading, check the list layout, then retry")
        tasks = parse_task_cards(cards[:limit])
        unresolved = 0
        resolved = []
        for task in tasks:
            if task_available(task) and resolve_entries and not task.get("order_id"):
                task = _entry_from_task(context, page, task)
            if task_available(task) and not task.get("order_id"):
                unresolved += 1
            resolved.append(task)
        return _final_task_list(resolved, unresolved)
    finally:
        if close_page:
            try:
                page.close()
            except Exception:
                pass


def _task_card_lookup(task):
    """Return the click script and argument for this task card.

    An order id uniquely identifies the card, so it wins whenever present.
    The task name is only used when no order id was supplied.
    """
    order_id = _text((task or {}).get("order_id"))
    if order_id:
        return _JS_CLICK_DETAIL_BY_ORDER, order_id
    name = _text((task or {}).get("task_name"))
    if name:
        return _JS_CLICK_DETAIL_BY_TASK, name
    return None, None


def _find_task_card(page, task) -> bool:
    script, arg = _task_card_lookup(task)
    if script is None:
        return False
    try:
        return bool(page.evaluate(script, arg))
    except Exception:
        return False


def find_submission(context, task: dict, *, title: str = "", work_id: str = "",
                    attempts: int = 6, delay: float = 4.0) -> dict:
    """Read this task's submission record.  Returns a status dict, never a guess."""
    attempts = max(1, int(attempts))
    last_reason = ""
    for attempt in range(attempts):
        page = _context_page(context)
        close_page = page not in (getattr(context, "pages", None) or [])
        detail = None
        try:
            _goto_list(page)
            # _find_task_card clicks a card tagged by this exact script.  The
            # read-back path runs in a fresh tab, so it must tag the cards
            # here; otherwise every read-back would be UNKNOWN.
            page.evaluate(_js_task_cards())
            script, arg = _task_card_lookup(task)
            if not _find_task_card(page, task):
                last_reason = "task card not found"
            else:
                # Chrome opens task details in a new tab; WebKit navigates the
                # same tab.  The click MUST happen inside expect_page so the new
                # tab is not missed, and the same-page fallback keeps WebKit
                # working.
                detail, clicked = _click_with_page_fallback(
                    context, page, script, arg, timeout_ms=12000)
                if not clicked or detail is None:
                    last_reason = "task detail did not open"
                    detail = None
                if detail is None:
                    continue
                try:
                    detail.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass
                detail.wait_for_timeout(2500)
                text = ""
                try:
                    text = detail.inner_text("body")
                except Exception:
                    text = ""
                status = submission_status(text, task, title=title, work_id=work_id)
                if status == STATUS_FOUND:
                    return {"status": STATUS_FOUND, "text": text[:2000],
                            "attempt": attempt + 1}
                if status == STATUS_NOT_FOUND:
                    return {"status": STATUS_NOT_FOUND, "text": text[:2000],
                            "attempt": attempt + 1}
                last_reason = "submission record not visible"
        except Exception as exc:
            last_reason = "%s: %s" % (type(exc).__name__, exc)
        finally:
            if detail is not None and detail is not page:
                try:
                    detail.close()
                except Exception:
                    pass
            if close_page:
                try:
                    page.close()
                except Exception:
                    pass
        if attempt + 1 < attempts:
            time.sleep(max(0.0, float(delay)))
    return {"status": STATUS_UNKNOWN, "reason": last_reason or "readback unavailable"}


def tasks_json(tasks) -> str:
    return json.dumps({"ok": True, "tasks": tasks}, ensure_ascii=True)
