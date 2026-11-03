"""Licence: Ed25519-signed JSON bound to a machine fingerprint.

Field set and behaviour mirror the Mac plan section 6.1 / Windows plan 9.x:
  customer_id, machine_id, accounts[], plan, quota, features[],
  issued_at, expires_at, grace_days, signature

The cloud only validates licences / counts quota / aggregates read-only
reports; it never holds the customer cookie, login state, media or a browser
instance (hard constraint, background.md section 3).
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone

from . import ed25519_pure
from .errors import ConfigError

STATUS_OK = "OK"
STATUS_MACHINE_MISMATCH = "MACHINE_MISMATCH"
STATUS_EXPIRED = "EXPIRED"
STATUS_GRACE = "GRACE"
STATUS_BAD_SIGNATURE = "SIGNATURE_INVALID"
STATUS_BAD_SCHEMA = "SCHEMA_INVALID"
STATUS_CRYPTO_UNAVAILABLE = "CRYPTO_UNAVAILABLE"
STATUS_WEAK_FINGERPRINT = "WEAK_FINGERPRINT"
STATUS_CLOCK_ROLLBACK = "CLOCK_ROLLBACK"

#: Explicit clock-state verdicts (1.2.8, GPT_REVIEW_1.2.7 必修 1).  The guard
#: used to answer only with a bool, so a caller could not tell "the clock is
#: fine" from "the clock state is unreadable" -- both looked like "no rollback"
#: to a display that only read ``rollback``.  We now name the state.
CLOCK_OK = "CLOCK_OK"
CLOCK_ROLLBACK = "CLOCK_ROLLBACK"
CLOCK_STATE_UNREADABLE = "CLOCK_STATE_UNREADABLE"
CLOCK_STATE_INVALID = "CLOCK_STATE_INVALID"
CLOCK_WRITE_FAILED = "CLOCK_WRITE_FAILED"
CLOCK_BLOCKING_STATUSES = (CLOCK_ROLLBACK, CLOCK_STATE_UNREADABLE,
                           CLOCK_STATE_INVALID, CLOCK_WRITE_FAILED)


def canonical_payload(license_obj: dict) -> bytes:
    """Deterministic bytes that the vendor signs (signature field excluded)."""
    body = {k: v for k, v in license_obj.items() if k != "signature"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def parse_time(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def validate_schema(license_obj: dict) -> list:
    required = ("customer_id", "machine_id", "plan", "issued_at", "expires_at",
                "signature")
    missing = [k for k in required if not license_obj.get(k)]
    errors = [f"missing field: {k}" for k in missing]
    # 1.2.5 (GPT review item 9): a per-seat object used to be accepted with any
    # value types -- ``enabled`` as the STRING "false" is truthy after bool(),
    # and a garbage ``expires_at`` produced ``days_left=None`` and was allowed.
    # We now reject the shape outright so publish_gate sees BAD_SCHEMA.
    if license_obj.get("accounts") is not None:
        accounts = license_obj["accounts"]
        if not isinstance(accounts, list):
            errors.append("accounts must be a list")
        else:
            errors.extend(_validate_accounts(accounts))
    if license_obj.get("features") is not None:
        feats = license_obj["features"]
        if not isinstance(feats, list) or any(not isinstance(f, str) for f in feats):
            errors.append("features must be a list of strings")
    if license_obj.get("quota") is not None and not isinstance(
            license_obj["quota"], dict):
        errors.append("quota must be an object")
    if "seats" in license_obj and license_obj["seats"] is not None:
        try:
            seats = int(license_obj["seats"])
        except (TypeError, ValueError):
            errors.append("seats must be an integer")
        else:
            if seats < 0:
                errors.append("seats must be >= 0")
    for field in ("issued_at", "expires_at"):
        if license_obj.get(field):
            try:
                parse_time(license_obj[field])
            except (ValueError, TypeError, AttributeError):
                errors.append(f"{field} is not ISO-8601")
    if "grace_days" in license_obj and license_obj["grace_days"] is not None:
        try:
            value = float(license_obj["grace_days"])
        except (TypeError, ValueError):
            errors.append("grace_days is not a number")
        else:
            if not math.isfinite(value):
                errors.append("grace_days must be a finite number")
    if "signature" in license_obj and license_obj["signature"] is not None \
            and not isinstance(license_obj["signature"], str):
        errors.append("signature must be a hex string")
    return errors


def _validate_accounts(accounts: list) -> list:
    """Type-strict checks for the accounts[] seats (GPT review 1.2.5 item 9)."""
    errors = []
    for i, entry in enumerate(accounts):
        if isinstance(entry, str):
            if not entry.strip():
                errors.append(f"accounts[{i}] is an empty string")
            continue
        if not isinstance(entry, dict):
            errors.append(f"accounts[{i}] must be a string or object")
            continue
        aid = entry.get("account_id")
        if not isinstance(aid, str) or not aid.strip():
            errors.append(f"accounts[{i}].account_id missing or not a string")
        if "enabled" in entry and not isinstance(entry["enabled"], bool):
            errors.append(f"accounts[{i}].enabled must be a boolean")
        expires = entry.get("expires_at")
        if expires is not None:
            if not isinstance(expires, str):
                errors.append(f"accounts[{i}].expires_at must be ISO-8601")
            else:
                try:
                    parse_time(expires)
                except (ValueError, TypeError, AttributeError):
                    errors.append(f"accounts[{i}].expires_at is not ISO-8601")
        for name in ("platform", "nickname"):
            if name in entry and entry[name] is not None \
                    and not isinstance(entry[name], str):
                errors.append(f"accounts[{i}].{name} must be a string")
    return errors


def grace_days_of(license_obj) -> float:
    """Grace period in days; a missing / null / bad value falls back to the
    default.  1.2.5 (GPT review item 9): ``validate_schema`` used to SKIP
    ``grace_days=None`` while ``check_license`` then ran ``float(None)``."""
    value = (license_obj or {}).get("grace_days")
    if value is None:
        return 14.0
    try:
        days = float(value)
    except (TypeError, ValueError):
        return 14.0
    return days if days >= 0 else 14.0


def check_license(license_obj, public_key: bytes, machine_id: str, *,
                  now=None, verify_signature=True, fingerprint_info=None) -> dict:
    """Return {'status', 'reason', 'days_left', 'features', 'quota'}."""
    now = now or datetime.now(timezone.utc)
    errors = validate_schema(license_obj)
    if errors:
        return {"status": STATUS_BAD_SCHEMA, "reason": "; ".join(errors)}

    # A weak fingerprint (fewer than 2 stable components) hashes almost the same
    # on every machine -> binding would be meaningless and clones would pass.
    if fingerprint_info is not None and fingerprint_info.get("weak"):
        return {"status": STATUS_WEAK_FINGERPRINT,
                "reason": "machine fingerprint has <2 stable components; "
                          "refusing to bind (clone risk)"}

    if verify_signature:
        try:
            signature = bytes.fromhex(license_obj["signature"])
        except ValueError:
            return {"status": STATUS_BAD_SCHEMA, "reason": "signature not hex"}
        if not ed25519_pure.verify(signature, canonical_payload(license_obj),
                                   public_key):
            return {"status": STATUS_BAD_SIGNATURE,
                    "reason": "signature does not verify with vendor key"}

    if license_obj["machine_id"] != machine_id:
        return {"status": STATUS_MACHINE_MISMATCH,
                "reason": "机器指纹不符，请联系换签"}

    expires = parse_time(license_obj["expires_at"])
    days_left = (expires - now).total_seconds() / 86400.0
    grace_days = grace_days_of(license_obj)
    if days_left < 0:
        if days_left >= -grace_days:
            return {"status": STATUS_GRACE, "days_left": days_left,
                    "reason": f"offline grace, {-days_left:.1f} days used",
                    "features": license_obj.get("features", []),
                    "quota": license_obj.get("quota", {})}
        return {"status": STATUS_EXPIRED, "days_left": days_left,
                "reason": "expired beyond grace"}

    return {"status": STATUS_OK, "days_left": days_left,
            "features": license_obj.get("features", []),
            "quota": license_obj.get("quota", {})}


def feature_allowed(license_obj: dict, feature: str) -> bool:
    return feature in (license_obj.get("features") or [])


def license_seats(license_obj: dict | None) -> int:
    """The self-service account ceiling encoded in a licence.

    1.2.18: a licence may carry ``seats`` (default 4).  A missing, null or
    invalid value falls back to the default; the customer-visible limit is
    always capped at 4 by the caller.
    """
    if not isinstance(license_obj, dict) or "seats" not in license_obj:
        return 4
    try:
        seats = int(license_obj["seats"])
    except (TypeError, ValueError):
        return 4
    return seats if seats >= 0 else 4

def _normalise_accounts(license_obj: dict) -> dict:
    """accounts[] may be plain ids or objects; normalise to {id: {...}}.

    Per-号 authorisation (source/extra-requirements-update.md section 4): one
    account = one seat.  A list that holds both a platform and an enabled flag
    lets multiple platforms / multiple accounts be counted and disabled
    separately, without touching anyone else's seat.
    """
    out = {}
    for entry in (license_obj.get("accounts") or []):
        if isinstance(entry, str):
            out[entry] = {"account_id": entry, "enabled": True}
        elif isinstance(entry, dict) and entry.get("account_id"):
            out[entry["account_id"]] = {
                "account_id": entry["account_id"],
                "platform": entry.get("platform"),
                "nickname": entry.get("nickname"),
                "enabled": bool(entry.get("enabled", True)),
                "expires_at": entry.get("expires_at"),
            }
    return out


def authorized_accounts(license_obj: dict) -> dict:
    return _normalise_accounts(license_obj)


def account_authorization(license_obj: dict, account_id: str, *,
                          now=None) -> dict:
    """Per-seat verdict, so one expired/disabled seat never blocks the rest."""
    now = now or datetime.now(timezone.utc)
    seats = _normalise_accounts(license_obj)
    seat = seats.get(account_id)
    if seat is None:
        return {"account_id": account_id, "authorized": False, "enabled": False,
                "reason": f"该号未授权（{account_id} 不在授权名单里），请联系我们加号"}
    if not seat.get("enabled", True):
        return {"account_id": account_id, "authorized": True, "enabled": False,
                "reason": f"该号已停用（{account_id}），其它平台不受影响"}
    expires_at = seat.get("expires_at") or license_obj.get("expires_at")
    if expires_at:
        try:
            days_left = (parse_time(expires_at) - now).total_seconds() / 86400.0
        except ValueError:
            days_left = None
        if days_left is not None and days_left < 0:
            return {"account_id": account_id, "authorized": True, "enabled": False,
                    "days_left": days_left,
                    "reason": f"该号授权已过期（{account_id}），请联系我们续签"}
        seat["days_left"] = days_left
    return {"account_id": account_id, "authorized": True, "enabled": True,
            "platform": seat.get("platform"), "days_left": seat.get("days_left"),
            "reason": "已授权"}


def account_quota(license_obj: dict) -> dict:
    """Count seats by platform -- report only; never a silent upsell."""
    seats = _normalise_accounts(license_obj)
    per_platform = {}
    for seat in seats.values():
        key = seat.get("platform") or "(未标注平台)"
        per_platform[key] = per_platform.get(key, 0) + 1
    quota = dict(license_obj.get("quota") or {})
    quota.setdefault("accounts", 0)
    return {"quota": quota, "seats_total": len(seats),
            "seats_enabled": sum(1 for s in seats.values() if s.get("enabled", True)),
            "per_platform": per_platform,
            "seats": list(seats.values())}


#: fixed, non-overridable location of the trust root inside the program tree.
VENDOR_PUBKEY_RELATIVE = "config/vendor_pubkey.hex"

#: separate, fixed trust root for approval receipts.  Receipts are signed by
#: the control plane with a key that is NOT the licence vendor key, so a
#: missing / leaked vendor private key cannot mint publish approvals.
RECEIPT_PUBKEY_RELATIVE = "config/receipt_pubkey.hex"


def _load_public_key(path, label: str) -> bytes:
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"{label} missing: {p}")
    text = p.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ConfigError(f"{label} is empty: {p}")
    try:
        key = bytes.fromhex(text)
    except ValueError:
        raise ConfigError(f"{label} is not hex: {p}")
    if len(key) != 32:
        raise ConfigError(f"{label} must be 32 bytes, got {len(key)}: {p}")
    return key


def load_vendor_public_key(path) -> bytes:
    return _load_public_key(path, "vendor public key")


def require_vendor_public_key(program=None) -> bytes:
    """Load the trust root from its FIXED in-package location.

    When ``program`` is omitted the root is derived from ``paths.install_root()``
    -- the directory this code actually runs from -- so neither ``--program`` nor
    ``WINPORT_PROGRAM`` can point the crypto trust chain at another directory
    (GPT review 1.2.5 item 3).  Raises ConfigError when the key is missing /
    empty / malformed -- never returns a soft "allow".
    """
    from pathlib import Path
    if program is None:
        from .paths import install_root
        program = install_root()
    return load_vendor_public_key(Path(program) / VENDOR_PUBKEY_RELATIVE)


def require_receipt_public_key() -> bytes:
    """Load the approval-receipt trust root from its FIXED in-package location.

    This intentionally takes no path/program/key argument: the receipt trust
    root is always ``install_root()/config/receipt_pubkey.hex``.  Missing,
    empty, non-hex or non-32-byte files raise ``ConfigError`` (fail closed).
    """
    from pathlib import Path
    from .paths import install_root
    return _load_public_key(Path(install_root()) / RECEIPT_PUBKEY_RELATIVE,
                            "receipt public key")


# ------------------------------------------------------------------ clock (E)
#: How far the clock may drift backwards before we call it a rollback.  Windows
#: time sync (w32time) and DST-style corrections stay well under this.
CLOCK_ROLLBACK_TOLERANCE_SECONDS = 300


def clock_guard(state_path, *, now=None,
                tolerance_seconds=CLOCK_ROLLBACK_TOLERANCE_SECONDS) -> dict:
    """Monotonic-time guard against "wind the clock back to revive a lapsed licence".

    We record the highest UTC time we have ever trusted in a small state file and
    refuse the *publish* path when the current clock is meaningfully BEHIND that
    high-water mark.  This defeats a pure "change the system clock" attack.

    Threat boundary (documented, and deliberately honest -- see README/VERIFY):
    an attacker with full local control can also roll this state file back, and
    an OFFLINE client cannot prevent that.  The real authority is the server-side
    signed issued_at / short lease; this guard is defence-in-depth, not a promise
    of tamper-proofness.
    """
    from .jsonio import write_json
    from pathlib import Path
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    path = Path(state_path)
    state_ok = True
    reason = ""
    last = None
    status = CLOCK_OK
    # 1.2.5 (GPT review item 4): distinguish "no state yet" (a genuine FIRST run
    # on a fresh install) from "state present but NOT usable".  A present but
    # empty / null / unparseable / key-missing file is treated as TAMPERED:
    # fail closed AND do not rewrite it, so a retry cannot "repair" the trust
    # by overwriting the corrupt file with the current (attacker-set) time.
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:               # unreadable state file
            text = None
            state_ok = False
            status = CLOCK_STATE_UNREADABLE
            reason = f"时钟状态文件无法读取：{exc}"
        if text is not None:
            stripped = text.strip()
            if not stripped:
                state_ok = False
                status = CLOCK_STATE_INVALID
                reason = "时钟状态文件为空（可能被清空或篡改），拒绝发布"
            else:
                try:
                    state = json.loads(stripped)
                except ValueError as exc:
                    state = None
                    state_ok = False
                    status = CLOCK_STATE_INVALID
                    reason = f"时钟状态文件已损坏：{exc}"
                if state_ok and not isinstance(state, dict):
                    state_ok = False
                    status = CLOCK_STATE_INVALID
                    reason = "时钟状态文件不是 JSON 对象，拒绝发布"
                if state_ok:
                    raw = state.get("last_seen_utc")
                    if not isinstance(raw, str) or not raw.strip():
                        state_ok = False
                        status = CLOCK_STATE_INVALID
                        reason = "时钟高水位记录缺失或为空，无法判断是否回拨，拒绝发布"
                    else:
                        try:
                            last = parse_time(raw)
                        except (ValueError, TypeError, AttributeError):
                            state_ok = False
                            status = CLOCK_STATE_INVALID
                            reason = "时钟高水位记录不是有效时间，无法判断是否回拨，拒绝发布"
                            last = None
    rollback = bool(last is not None
                    and now < last - timedelta(seconds=tolerance_seconds))
    high = now if (last is None or now > last) else last
    if state_ok:
        try:
            write_json(path, {"last_seen_utc": high.isoformat(),
                              "updated_at": now.isoformat(),
                              "rollback_detected": rollback})
        except OSError as exc:               # cannot persist the new high-water
            state_ok = False
            status = CLOCK_WRITE_FAILED
            reason = reason or f"时钟状态无法写入（磁盘满/无权限）：{exc}"
    # 1.2.8 (GPT_REVIEW_1.2.7 必修 1): the verdict is a NAMED state, not just a
    # bool.  A display that only read ``rollback`` could not tell "clock fine"
    # from "clock state unreadable"; now both the panel and the self-test show
    # the reason in Chinese.
    if status == CLOCK_OK and rollback:
        status = CLOCK_ROLLBACK
    # Fail CLOSED: if we cannot trust the clock state we treat it as a rollback,
    # so "cannot check" never becomes "no rollback" (GPT review 1.2.5 item 4).
    return {"rollback": bool(rollback or not state_ok),
            "state_ok": state_ok,
            "status": status,
            "reason": reason,
            "now": now.isoformat(),
            "last_seen": last.isoformat() if last else None,
            "high_water": high.isoformat(),
            "tolerance_seconds": tolerance_seconds}


# ---------------------------------------------------------------- expiry (E)
#: 授权到期提醒 + 「到期只停新增发布，不影响已有数据与抓数」(design-refs C/E).
#: Publish is the only thing that stops: collect / report / downlink keep
#: working, because the customer's login state and their historical data are
#: theirs and must not be held hostage by a lapsed seat.
DEFAULT_NOTICE_THRESHOLDS = (30, 7, 1)

#: Statuses that forbid a NEW publish (collect / report / evidence still run).
#: 1.2.5: a detected clock rollback also forbids a NEW publish (see clock_guard).
PUBLISH_BLOCKING = (STATUS_EXPIRED, STATUS_MACHINE_MISMATCH, STATUS_BAD_SIGNATURE,
                    STATUS_BAD_SCHEMA, STATUS_WEAK_FINGERPRINT,
                    STATUS_CRYPTO_UNAVAILABLE, STATUS_CLOCK_ROLLBACK)

NOTICE_TEXT = {
    30: "授权还有 30 天到期，请安排续期（不影响现在的发布与抓数）。",
    7: "授权还有 7 天到期，请尽快续期；到期后只停新增发布，抓数与历史数据不受影响。",
    1: "授权 1 天内到期！请立刻续期；到期后新增发布会被暂停，抓数与已有数据不受影响。",
}


def expiry_notices(license_obj: dict, *, now=None,
                   thresholds=DEFAULT_NOTICE_THRESHOLDS) -> dict:
    """Return the expiry reminder for a licence (E).

    ``level`` is the tightest threshold already reached ("none"/"30"/"7"/"1"/
    "grace"/"expired"); ``notices`` is the ordered list of human sentences to
    show in the tray + panel.
    """
    now = now or datetime.now(timezone.utc)
    errors = validate_schema(license_obj)
    if errors:
        return {"level": "invalid", "days_left": None,
                "notices": ["授权文件不完整：" + "；".join(errors)],
                "expiry_blocks_publish": True, "collect_allowed": True,
                "renew_url": "", "reason": "SCHEMA_INVALID"}
    try:
        expires = parse_time(license_obj["expires_at"])
    except (ValueError, TypeError, AttributeError):
        return {"level": "invalid", "days_left": None,
                "notices": ["授权到期时间不是 ISO-8601，无法计算剩余天数"],
                "expiry_blocks_publish": True, "collect_allowed": True,
                "renew_url": "", "reason": "BAD_EXPIRES_AT"}
    days_left = (expires - now).total_seconds() / 86400.0
    grace_days = grace_days_of(license_obj)
    notices = []
    level = "none"
    if days_left >= 0:
        # ascending: pick the TIGHTEST threshold the licence has already reached
        # (days_left=3 with thresholds 30/7/1 must say "7", not "30").
        for threshold in sorted({int(t) for t in thresholds}):
            if days_left <= threshold:
                level = str(threshold)
                notices.append(NOTICE_TEXT.get(
                    threshold,
                    f"授权还有 {threshold} 天到期，请安排续期。"))
                break
    elif days_left >= -grace_days:
        level = "grace"
        notices.append(
            f"授权已过期 {-days_left:.1f} 天，处于离线宽限期内；尽快续期，"
            "宽限期结束后新增发布会暂停（抓数与历史数据不受影响）。")
    else:
        level = "expired"
        notices.append("授权已过期，新增发布已暂停；抓数与历史数据仍可用，续期后自动恢复。")
    return {
        "level": level,
        "days_left": round(days_left, 2),
        "expires_at": license_obj["expires_at"],
        "notices": notices,
        # 1.2.5 (GPT review item 1): this flag speaks ONLY about expiry -- it is
        # deliberately NOT called "publish_allowed" so a diagnostic can never show
        # a competing "allowed" next to the real, full publish gate.
        "expiry_blocks_publish": level in ("expired", "invalid"),
        "collect_allowed": True,
        "renew_url": license_obj.get("renew_url", ""),
        "reason": "ok" if level not in ("expired", "invalid") else level,
    }


def publish_gate(license_obj, public_key: bytes, machine_id: str, *,
                 now=None, account_id=None, fingerprint_info=None,
                 clock_rollback=False) -> dict:
    """Decide whether a NEW publish may start (E).

    Data / collect are never gated here: this function only answers the publish
    question, so a lapsed licence can never take away 抓数 or 历史数据.

    ``fingerprint_info`` (from ``fingerprint.fingerprint()``) turns on the weak-
    fingerprint clone check; ``clock_rollback`` (from ``clock_guard``) blocks a
    publish attempt made after the system clock was wound back.
    """
    result = check_license(license_obj, public_key, machine_id, now=now,
                           fingerprint_info=fingerprint_info)
    notice = expiry_notices(license_obj, now=now)
    seat = None
    if account_id:
        seat = account_authorization(license_obj, account_id, now=now)
    allowed = result["status"] not in PUBLISH_BLOCKING
    reasons = []
    if not allowed:
        reasons.append(f"授权状态 {result['status']}：{result.get('reason', '')}")
    if seat is not None and not seat.get("enabled", True):
        allowed = False
        reasons.append(seat.get("reason", "该号未授权或已停用"))
    if clock_rollback:
        allowed = False
        reasons.append("检测到系统时间被回拨（CLOCK_ROLLBACK）：为防绕过授权到期，"
                       "新增发布已暂停；请校准系统时间后重试。")
    return {
        "publish_allowed": bool(allowed),
        "collect_allowed": True,
        "status": result["status"],
        "days_left": notice.get("days_left"),
        "level": notice.get("level"),
        "notices": notice.get("notices", []),
        "seat": seat,
        "clock_rollback": bool(clock_rollback),
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# 14 天自动试用（1.2.40）：安装后未导入 license.json 时自动开通，绑定本机。
# 目的是让客户/测试方装完即可登录、排期、发布，不必先等人工签发；
# 正式授权导入后以 license.json 为准（status=OK），试用文件不再生效。
# ---------------------------------------------------------------------------
TRIAL_DAYS = 14


def trial_state(layout, now=None):
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    import json as _json
    from .fingerprint import fingerprint

    try:
        mid = fingerprint().get("machine_id")
        root = Path(getattr(layout, "system", Path(layout.data)))
        path = root / "trial.json"
        now = now or datetime.now(timezone.utc)
        data = None
        if path.exists():
            try:
                data = _json.loads(path.read_text("utf-8"))
            except Exception:
                data = None
        if not isinstance(data, dict) or data.get("machine") != mid:
            data = {"machine": mid, "issued": now.isoformat(), "days": TRIAL_DAYS}
            root.mkdir(parents=True, exist_ok=True)
            path.write_text(_json.dumps(data, ensure_ascii=False), "utf-8")
        issued = datetime.fromisoformat(data["issued"])
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=timezone.utc)
        left = (issued + timedelta(days=int(data.get("days", TRIAL_DAYS))) - now).total_seconds() / 86400.0
        if left <= 0:
            return None
        return {
            "status": "TRIAL",
            "license_status": "TRIAL",
            "publish_allowed": True,
            "collect_allowed": True,
            "days_left": round(left, 1),
            "level": "ok",
            "seat": None,
            "notices": ["试用授权：剩余 %d 天，导入正式授权后自动切换。" % int(left)],
            "reasons": [],
            "clock_rollback": False,
            "license_path": str(path),
            "source": "trial",
        }
    except Exception:
        return None
