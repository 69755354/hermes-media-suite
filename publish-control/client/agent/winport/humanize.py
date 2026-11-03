"""Humanized, configurable interaction timing for real-browser publishing.

Every visible action delay is randomized from a persistent per-environment
``PaceProfile``.  No production interaction path should call ``time.sleep``
with a hard-coded constant; it should call this module and log the actual
delay.  The profile is stored under ``<Data>/config/pace_profiles.json`` so
each account keeps its own rhythm across restarts.

The six required behaviours:
  1. random inter-step pauses (log-normal-ish, 200-1200 ms) + occasional
     0.8-2.5 s "thinking" pauses before key actions;
  2. character-by-character typing, 40-180 ms per char, a 0.3-1.2 s pause
     every 8-15 chars, and a 3% typo/backspace probability;
  3. Bézier mouse movement (3-5 control points), ±6 px landing offset, and a
     200-600 ms hover before click;
  4. inertial scrolling split into 2-4 segments with randomized speed;
  5. 0.8-3 s post-load stay and 1-3 s pre-submit stay;
  6. per-environment pace profiles (fast/medium/slow + typing + pause habits).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .jsonio import read_json, write_json

PROFILE_PATH = "pace_profiles.json"

DEFAULT_PROFILE = {
    "pace": "medium",
    "step_pause_ms": [200, 1200],
    "think_pause_ms": [800, 2500],
    "type_char_ms": [40, 180],
    "type_block_min": 8,
    "type_block_max": 15,
    "type_block_pause_ms": [300, 1200],
    "typo_probability": 0.03,
    "hover_ms": [200, 600],
    "landing_jitter_px": 6,
    "bezier_points": [3, 5],
    "scroll_segments": [2, 4],
    "page_load_ms": [800, 3000],
    "pre_submit_ms": [1000, 3000],
    "poll_jitter_ms": [150, 400],
}

PACE_MULTIPLIERS = {
    "fast": {"step": 0.75, "type": 0.8, "think": 0.8},
    "medium": {"step": 1.0, "type": 1.0, "think": 1.0},
    "slow": {"step": 1.3, "type": 1.25, "think": 1.35},
}

PACE_NAMES = {
    "fast": "快",
    "medium": "中",
    "slow": "慢",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _profile_digest(env_id: str) -> str:
    return hashlib.sha256(str(env_id or "default").encode("utf-8")).hexdigest()[:16]


def default_profile_for_env(env_id: str) -> dict:
    """Deterministic initial pace assignment for a new environment.

    The digest keeps the initial assignment stable across restarts, while the
    persisted file is still the authoritative source afterwards.
    """
    digest = int(_profile_digest(env_id), 16)
    pace = ("fast", "medium", "slow")[digest % 3]
    profile = dict(DEFAULT_PROFILE)
    profile["pace"] = pace
    profile["seed_shift"] = digest % 65536
    return profile


@dataclass
class PaceProfile:
    """Persistent, per-environment parameters used by :class:`Humanizer`."""

    pace: str = "medium"
    step_pause_ms: list[int] = field(default_factory=lambda: [200, 1200])
    think_pause_ms: list[int] = field(default_factory=lambda: [800, 2500])
    type_char_ms: list[int] = field(default_factory=lambda: [40, 180])
    type_block_min: int = 8
    type_block_max: int = 15
    type_block_pause_ms: list[int] = field(default_factory=lambda: [300, 1200])
    typo_probability: float = 0.03
    hover_ms: list[int] = field(default_factory=lambda: [200, 600])
    landing_jitter_px: int = 6
    bezier_points: list[int] = field(default_factory=lambda: [3, 5])
    scroll_segments: list[int] = field(default_factory=lambda: [2, 4])
    page_load_ms: list[int] = field(default_factory=lambda: [800, 3000])
    pre_submit_ms: list[int] = field(default_factory=lambda: [1000, 3000])
    poll_jitter_ms: list[int] = field(default_factory=lambda: [150, 400])
    seed_shift: int = 0

    @classmethod
    def from_dict(cls, raw: dict | None, *, env_id: str = "default") -> "PaceProfile":
        raw = dict(raw or {})
        base = default_profile_for_env(env_id)
        data = {**base, **raw}
        try:
            return cls(**{k: data.get(k, v) for k, v in cls().to_dict().items()})
        except (TypeError, ValueError):
            return cls(**base)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def pace_label(self) -> str:
        return PACE_NAMES.get(self.pace, self.pace)


def load_pace_profiles(path) -> dict:
    """Read the persisted profile file, returning a dict of env_id -> profile."""
    raw = read_json(Path(path), default=None)
    return raw if isinstance(raw, dict) else {}


def get_pace_profile(layout, env_id: str) -> PaceProfile:
    """Load, or deterministically create, a persistent pace profile for one env."""
    path = Path(getattr(layout, "config", layout.data / "config")) / PROFILE_PATH
    profiles = load_pace_profiles(path)
    key = str(env_id or "default")
    if key in profiles and isinstance(profiles[key], dict):
        return PaceProfile.from_dict(profiles[key], env_id=key)
    base = default_profile_for_env(key)
    existing_paces = {
        value.get("pace") for value in profiles.values()
        if isinstance(value, dict) and value.get("pace")
    }
    if base["pace"] in existing_paces:
        for candidate in ("fast", "medium", "slow"):
            if candidate not in existing_paces:
                base["pace"] = candidate
                break
    profile = PaceProfile.from_dict(base, env_id=key)
    profiles[key] = profile.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, profiles)
    return profile


class Humanizer:
    """Produces and executes randomized timing/action plans.

    ``seed`` is optional and mainly for deterministic tests.  In production it
    is left unset, so the OS entropy source makes every run different while the
    persisted profile keeps the account's broad pace stable.
    """

    def __init__(self, profile: PaceProfile | dict | None = None, *,
                 env_id: str = "default", seed: int | None = None,
                 logger: Callable[[str, dict], None] | None = None):
        if isinstance(profile, PaceProfile):
            self.profile = profile
        elif isinstance(profile, dict):
            self.profile = PaceProfile.from_dict(profile, env_id=env_id)
        else:
            self.profile = PaceProfile.from_dict(None, env_id=env_id)
        self.rng = random.Random(seed)
        self.logger = logger or (lambda label, extra: None)
        self.delay_log: list[dict[str, Any]] = []
        self.action_seq = 0
        self.env_id = env_id
        self.profile_digest = hashlib.sha256(json.dumps(asdict(self.profile),
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        self._mouse_position = (0.0, 0.0)

    # ---- primitives -----------------------------------------------------
    def _range(self, pair: Iterable[int]) -> tuple[float, float]:
        values = list(pair)
        return float(values[0]), float(values[1])

    def _log(self, label: str, seconds: float, **extra) -> float:
        record = {"label": label, "seconds": round(seconds, 4),
                  "ms": round(seconds * 1000, 1), **extra}
        self.delay_log.append(record)
        self.logger(label, record)
        return seconds

    def _uniform_ms(self, pair, multiplier: float = 1.0) -> float:
        low, high = self._range(pair)
        return _clamp(self.rng.uniform(low * multiplier, high * multiplier),
                      low * multiplier, high * multiplier) / 1000.0

    def _log_normal_ms(self, pair, multiplier: float = 1.0) -> float:
        low, high = self._range(pair)
        low, high = low * multiplier, high * multiplier
        if high <= low:
            return low / 1000.0
        median = math.sqrt(low * high)
        sigma = math.log(high / median) / 2.0
        value = math.exp(self.rng.gauss(math.log(median), max(sigma, 0.05)))
        return _clamp(value, low, high) / 1000.0

    def sleep(self, seconds: float, *, label: str = "pause", **extra) -> float:
        sampled_ms = round(max(0.0, float(seconds)) * 1000.0, 1)
        started = time.monotonic()
        time.sleep(max(0.0, float(seconds)))
        finished = time.monotonic()
        realised_ms = round((finished - started) * 1000.0, 1)
        self.action_seq += 1
        return self._log(
            label, max(0.0, float(seconds)),
            sampled_ms=sampled_ms, realised_ms=realised_ms,
            started_monotonic=round(started, 6), finished_monotonic=round(finished, 6),
            action_seq=self.action_seq, profile_digest=self.profile_digest,
            **extra)

    def step_pause(self, *, reason: str = "step") -> float:
        seconds = self._log_normal_ms(self.profile.step_pause_ms)
        return self.sleep(seconds, label=reason, kind="step_pause")

    def think_pause(self, *, reason: str = "关键动作前思考") -> float:
        seconds = self._log_normal_ms(self.profile.think_pause_ms)
        return self.sleep(seconds, label=reason, kind="think")

    def page_load_pause(self) -> float:
        return self.sleep(self._uniform_ms(self.profile.page_load_ms),
                          label="页面加载后停留", kind="page_load")

    def pre_submit_pause(self) -> float:
        return self.sleep(self._uniform_ms(self.profile.pre_submit_ms),
                          label="提交前停留", kind="pre_submit")

    def hover_pause(self) -> float:
        return self.sleep(self._uniform_ms(self.profile.hover_ms),
                          label="点击前悬停", kind="hover")

    def poll_pause(self) -> float:
        return self.sleep(self._uniform_ms(self.profile.poll_jitter_ms),
                          label="DOM 轮询间隔", kind="poll")

    def backoff_pause(self, seconds: float, *, reason: str = "backoff") -> float:
        """Humanized backoff wrapper; callers still own the backoff schedule."""
        return self.sleep(max(0.0, float(seconds)), label=reason, kind="backoff")

    # ---- typing ---------------------------------------------------------
    def typing_plan(self, text: str) -> list[tuple[str, Any]]:
        """Return executable typing events for one string.

        Events are ``("char", ch)``, ``("typo", ch)``, ``("backspace", None)``
        or ``("block_pause", seconds)``.  The caller executes them against the
        focused page/element.
        """
        text = str(text)
        if not text:
            return []
        events: list[tuple[str, Any]] = []
        pending = 0
        for char in text:
            events.append(("char", char))
            pending += 1
            if pending >= self.rng.randint(self.profile.type_block_min,
                                           self.profile.type_block_max):
                if self.rng.random() < max(0.0, min(1.0,
                                                    self.profile.typo_probability)):
                    wrong = char if self.rng.random() < 0.4 else self.rng.choice(
                        [c for c in "abcdefghijklmnopqrstuvwxyz" if c != char])
                    events.append(("typo", wrong))
                    events.append(("backspace", None))
                    pending = 0
                seconds = self._uniform_ms(self.profile.type_block_pause_ms)
                events.append(("block_pause", seconds))
                pending = 0
        return events

    def char_delays(self, text: str) -> list[float]:
        """Return the per-character delays only (useful for statistics)."""
        return [self._uniform_ms(self.profile.type_char_ms) for _ in str(text)]

    def type_into(self, page, text: str, locator=None) -> dict:
        """Type ``text`` char-by-char using Playwright-like page/keyboard APIs.

        ``locator`` may be omitted; the caller must have focused the target.
        Returns a summary and appends every actual pause to ``delay_log``.
        """
        if locator is not None:
            locator.click()
        events = self.typing_plan(text)
        stats = {"chars": len(text), "typos": 0, "block_pauses": 0,
                 "duration_ms": 0.0}
        started = time.monotonic()
        for kind, value in events:
            if kind in ("char", "typo"):
                page.keyboard.insert_text(value)
            elif kind == "backspace":
                page.keyboard.press("Backspace")
            elif kind == "block_pause":
                stats["block_pauses"] += 1
                self.sleep(float(value), label="逐字输入段落停顿", kind="typing_block")
                continue
            if kind == "typo":
                stats["typos"] += 1
            seconds = self._uniform_ms(self.profile.type_char_ms)
            self.sleep(seconds, label="逐字输入", kind="typing_char", action=kind)
        stats["duration_ms"] = (time.monotonic() - started) * 1000.0
        return stats

    # ---- mouse ----------------------------------------------------------
    def bezier_points(self, start: tuple[float, float],
                      end: tuple[float, float]) -> list[tuple[float, float]]:
        """Generate ``n+1`` points (3-5 control points) along a Bézier path."""
        count = self.rng.randint(self.profile.bezier_points[0],
                                 self.profile.bezier_points[1])
        controls = [start]
        for _ in range(count - 2):
            controls.append((self.rng.uniform(min(start[0], end[0]),
                                              max(start[0], end[0])),
                             self.rng.uniform(min(start[1], end[1]),
                                              max(start[1], end[1]))))
        controls.append(end)
        out = []
        for step in range(26):
            t = step / 25.0
            points = list(controls)
            while len(points) > 1:
                points = [((1 - t) * x1 + t * x2, (1 - t) * y1 + t * y2)
                          for (x1, y1), (x2, y2) in zip(points, points[1:])]
            out.append((round(points[0][0], 1), round(points[0][1], 1)))
        return out

    def move_mouse(self, page, x: float, y: float, *, reason: str = "mouse") -> dict:
        """Move the mouse along a randomized Bézier path, then hover."""
        jitter = self.profile.landing_jitter_px
        target = (x + self.rng.uniform(-jitter, jitter),
                  y + self.rng.uniform(-jitter, jitter))
        points = self.bezier_points(self._mouse_position, target)
        started = time.monotonic()
        sampled = self._uniform_ms(self.profile.hover_ms)
        try:
            for px, py in points:
                page.mouse.move(px, py)
                time.sleep(sampled / len(points))
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
        self._mouse_position = target
        finished = time.monotonic()
        self.action_seq += 1
        self._log("鼠标贝塞尔", sampled, kind="mouse", path_points=len(points),
                  sampled_ms=sampled * 1000, realised_ms=(finished-started)*1000,
                  started_monotonic=started, finished_monotonic=finished,
                  action_seq=self.action_seq, profile_digest=self.profile_digest)
        self.hover_pause()
        return {"ok": True, "target": target, "path_points": len(points)}

    def click(self, page, locator, *, reason="click", before_click=None):
        """Actionability trial before authorization; one actual click only.

        2026-10-29: the creator-center tab can be throttled to ~2 rAF/s when it
        is occluded (the user is working on the same laptop).  Playwright's
        actionability gate then needs seconds, not milliseconds, so the old
        1 s / 3 s budgets produced "Timeout ... waiting for element to be
        visible, enabled and stable" while the button was plainly clickable.
        Bring the page to the front first and allow a realistic budget.
        """
        try:
            page.bring_to_front()
        except Exception:
            pass
        try:
            locator.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        box = locator.bounding_box()
        if not box:
            return {"ok": False, "reason": "bounding_box missing"}
        moved = self.move_mouse(page, box["x"] + box["width"]/2,
                                box["y"] + box["height"]/2, reason=reason)
        if not moved.get("ok"):
            return moved
        try:
            locator.click(trial=True, timeout=15000)
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
        if before_click is not None:
            before_click()
        try:
            locator.click(timeout=15000)
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
        return {"ok": True}

    # ---- scrolling ------------------------------------------------------
    def scroll(self, page, *, direction: int = 1, distance: int = 600) -> dict:
        """Scroll in 2-4 inertial segments with randomized speed."""
        segments = self.rng.randint(self.profile.scroll_segments[0],
                                    self.profile.scroll_segments[1])
        total = max(1, int(distance or 600))
        base = direction * total / segments
        events = []
        for index in range(segments):
            # inertia: early segments carry more distance
            scale = 1.0 - index * 0.18
            delta = int(base * max(0.35, scale))
            page.mouse.wheel(0, delta)
            self.sleep(self._uniform_ms(self.profile.poll_jitter_ms),
                       label="惯性滚动", kind="scroll",
                       segment=index + 1, delta=delta)
            events.append(delta)
        return {"segments": segments, "deltas": events}

    # ---- series for verification ---------------------------------------
    def delay_series(self, rounds: int = 3) -> list[dict]:
        """Generate observable sequences without sleeping for the full pauses.

        Used by the acceptance report to prove the distributions are not fixed.
        """
        rounds = max(1, int(rounds))
        out = []
        for index in range(rounds):
            text = "测试发布文案"
            char_delays = self.char_delays(text)
            events = self.typing_plan(text)
            out.append({
                "round": index + 1,
                "pace": self.profile.pace,
                "step_pause_ms": round(self._log_normal_ms(
                    self.profile.step_pause_ms) * 1000, 1),
                "think_pause_ms": round(self._log_normal_ms(
                    self.profile.think_pause_ms) * 1000, 1),
                "page_load_ms": round(self._uniform_ms(
                    self.profile.page_load_ms) * 1000, 1),
                "pre_submit_ms": round(self._uniform_ms(
                    self.profile.pre_submit_ms) * 1000, 1),
                "char_delays_ms": [round(v * 1000, 1) for v in char_delays],
                "typing_events": len(events),
                "typos": sum(1 for event in events if event[0] == "typo"),
            })
        return out


def summarize_series(series: list[dict]) -> dict:
    """Compute mean/min/max/std for the delay series (used in the report)."""

    def _stats(values: list[float]) -> dict:
        if not values:
            return {"count": 0, "mean": None, "min": None, "max": None, "std": None}
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return {"count": len(values), "mean": round(mean, 2),
                "min": round(min(values), 2), "max": round(max(values), 2),
                "std": round(math.sqrt(variance), 2)}

    all_chars = [value for row in series for value in row.get("char_delays_ms", [])]
    return {
        "rounds": len(series),
        "step_pause_ms": _stats([row["step_pause_ms"] for row in series]),
        "think_pause_ms": _stats([row["think_pause_ms"] for row in series]),
        "page_load_ms": _stats([row["page_load_ms"] for row in series]),
        "pre_submit_ms": _stats([row["pre_submit_ms"] for row in series]),
        "char_delays_ms": _stats(all_chars),
        "typo_counts": [row.get("typos", 0) for row in series],
    }


ALLOWED_DELAY_KINDS = {
    "step_pause", "think", "typing_block", "typing_char", "mouse",
    "hover", "scroll", "poll", "backoff", "page_load", "pre_submit",
}


def validate_delay_records(records: list[dict], *, tolerance_ms: float = 5.0) -> list[str]:
    """Return reasons a delay log is not auditable.

    Each record must carry the sampled/realised pair, monotonic start/end,
    action sequence, kind and profile digest.  The realised time must match
    the monotonic interval and be at least the sampled duration (within clock
    tolerance); a forged or missing ``realised_ms`` must fail.
    """
    reasons: list[str] = []
    if not records:
        return ["EMPTY_DELAY_LOG"]
    for index, record in enumerate(records):
        prefix = f"[{index}]"
        for key in ("sampled_ms", "realised_ms", "started_monotonic",
                    "finished_monotonic", "action_seq", "kind", "profile_digest"):
            if key not in record:
                reasons.append(f"{prefix} MISSING_{key.upper()}")
        if any(reason.startswith(prefix) for reason in reasons):
            continue
        try:
            sampled = float(record["sampled_ms"])
            realised = float(record["realised_ms"])
            started = float(record["started_monotonic"])
            finished = float(record["finished_monotonic"])
        except (TypeError, ValueError):
            reasons.append(f"{prefix} NON_NUMERIC_TIME")
            continue
        interval_ms = (finished - started) * 1000.0
        if abs(interval_ms - realised) > tolerance_ms:
            reasons.append(f"{prefix} REALISED_INTERVAL_MISMATCH")
        if realised + tolerance_ms < sampled:
            reasons.append(f"{prefix} REALISED_BELOW_SAMPLED")
        if finished <= started:
            reasons.append(f"{prefix} MONOTONIC_ORDER")
        try:
            if int(record["action_seq"]) <= 0:
                reasons.append(f"{prefix} ACTION_SEQ_INVALID")
        except (TypeError, ValueError):
            reasons.append(f"{prefix} ACTION_SEQ_INVALID")
        if record.get("action_seq") != index + 1:
            reasons.append(f"{prefix} ACTION_SEQ_DISCONTINUOUS")
        for key in ("sampled_ms", "realised_ms", "started_monotonic", "finished_monotonic"):
            try:
                if not math.isfinite(float(record[key])):
                    reasons.append(f"{prefix} NONFINITE_{key}")
            except (KeyError, ValueError, TypeError):
                reasons.append(f"{prefix} INVALID_{key}")
        if record["kind"] not in ALLOWED_DELAY_KINDS:
            reasons.append(f"{prefix} UNKNOWN_KIND")
    return reasons


if __name__ == "__main__":  # pragma: no cover - acceptance tool
    import argparse

    parser = argparse.ArgumentParser(prog="humanize")
    parser.add_argument("--env", default="default")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--pace", choices=["fast", "medium", "slow"], default=None)
    args = parser.parse_args()
    profile = default_profile_for_env(args.env)
    if args.pace:
        profile["pace"] = args.pace
    humanizer = Humanizer(PaceProfile.from_dict(profile, env_id=args.env))
    series = humanizer.delay_series(args.rounds)
    print(json.dumps({"profile": profile, "series": series,
                      "summary": summarize_series(series)},
                     ensure_ascii=False, indent=2))
