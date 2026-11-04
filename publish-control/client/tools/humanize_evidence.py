#!/usr/bin/env python3
"""Generate real-delay humanization evidence for 1.2.21 review.

Every pause is actually slept by ``Humanizer.sleep``, so each record contains
sampled_ms/realised_ms, monotonic start/finish, action_seq, kind and
profile_digest.  The fake page only provides keyboard/mouse APIs; no browser is
launched and no publish happens.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from winport import humanize  # noqa: E402
from winport.humanize import Humanizer, PaceProfile, default_profile_for_env  # noqa: E402


class FakeKeyboard:
    def insert_text(self, value):
        return None

    def press(self, value):
        return None


class FakeMouse:
    def move(self, x, y):
        return None

    def wheel(self, dx, dy):
        return None


class FakePage:
    keyboard = FakeKeyboard()
    mouse = FakeMouse()


def one_round(h: Humanizer, page, chars: int) -> dict:
    text = "这是一条用于验证逐字输入随机性的标题，长度足够覆盖段落停顿与纠错行为。" * (
        max(1, chars // 35 + 1)
    )
    text = text[:chars]
    before = len(h.delay_log)
    h.step_pause(reason="打开上传页")
    h.page_load_pause()
    h.think_pause(reason="观察上传入口")
    h.type_into(page, text)
    h.step_pause(reason="标题输入完成")
    h.hover_pause()
    h.move_mouse(page, 120, 220, reason="移动至发布按钮")
    h.scroll(page, distance=160)
    h.poll_pause()
    h.backoff_pause(random.uniform(0.4, 1.2), reason="后台退避")
    h.pre_submit_pause()
    return h.delay_log[before:]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="env_1")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--chars", type=int, default=180)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    base = default_profile_for_env(args.env)
    profile = PaceProfile.from_dict(base, env_id=args.env)
    h = Humanizer(profile, env_id=args.env)
    page = FakePage()
    rounds = []
    for index in range(args.rounds):
        rounds.append({"round": index + 1,
                       "records": one_round(h, page, args.chars)})
    records = [r for item in rounds for r in item["records"]]
    reasons = humanize.validate_delay_records(records)
    counts: dict[str, int] = {}
    for record in records:
        kind = str(record.get("kind"))
        counts[kind] = counts.get(kind, 0) + 1
    char_delays = [r.get("sampled_ms") for r in records if r.get("kind") == "typing_char"]
    summary = {
        "rounds": len(rounds),
        "records": len(records),
        "counts_by_kind": counts,
        "typing_char_sampled_count": len(char_delays),
        "typing_char_ms": {
            "min": round(min(char_delays), 2) if char_delays else None,
            "max": round(max(char_delays), 2) if char_delays else None,
            "mean": round(sum(char_delays) / len(char_delays), 2) if char_delays else None,
        },
        "validation_reasons": reasons,
        "valid": not reasons,
    }
    out = {
        "schema": "humanize_evidence/1.2.21",
        "profile": profile.to_dict(),
        "profile_digest": h.profile_digest,
        "summary": summary,
        "rounds": rounds,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps({"profile_digest": h.profile_digest,
                      "records": len(records), "counts_by_kind": counts,
                      "typing_char_count": len(char_delays),
                      "valid": summary["valid"],
                      "validation_reasons": reasons}, ensure_ascii=False),
          file=sys.stderr)
    return 0 if summary["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
