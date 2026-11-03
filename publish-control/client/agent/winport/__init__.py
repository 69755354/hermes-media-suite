"""winport -- Windows port of the Mac "漫剧发布助手" local agent.

Business logic (gate / approval / idempotency / downlink / collection /
report) mirrors the Mac package; the platform-binding layer (lock, focus,
autostart, keep-awake, process identity, fingerprint) is reimplemented for
Windows.  See output/win-port/README.md and the plan at
source/win-local-agent-package-plan.md.
"""

import sys as _sys

# 1.2.5 (GPT review item 5): the startup-chain integrity check FAILS on any
# file the shipped MANIFEST.json does not list, and the shipped tree carries no
# __pycache__.  Disable bytecode writing so a normal run never creates a stray
# .pyc that would look like tampering (the launchers also set
# PYTHONDONTWRITEBYTECODE=1, which is the reliable, pre-interpreter mechanism).
_sys.dont_write_bytecode = True

from .version import VERSION, APP_NAME, VENDOR

__all__ = ["VERSION", "APP_NAME", "VENDOR"]
