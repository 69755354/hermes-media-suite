"""Single source of truth for product identity and version.

Kept ASCII-only for technical paths (the plan forbids Chinese characters in
technical directory names: source/win-local-agent-package-plan.md section 1.2).
The user-visible Chinese name lives in APP_NAME_DISPLAY only.
"""

import os


def _detect_version() -> str:
    """Return the shipped build version, never a hard-coded stale one.

    The bundle ships ``VERSION`` at the program root; this module lives at
    ``<program>/agent/winport/version.py``, so the file sits two levels up.
    A missing file (source-tree run) falls back to the constant below.
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(os.path.dirname(here))
        with open(os.path.join(root, "VERSION"), "r", encoding="utf-8-sig") as fh:
            text = fh.read().strip()
        if text:
            return text
    except OSError:
        pass
    return "1.2.42"


VERSION = _detect_version()

VENDOR = "HuolongAgent"
APP_NAME = "publish-assistant"
APP_NAME_DISPLAY = "漫剧发布助手"

BUNDLE_SCHEMA = "1.0"

#: Increment when the licence payload/verification rules change.  The control
#: plane records this so an old agent never silently accepts a new contract.
LICENCE_SCHEMA = "1.0"

#: Minimum agent version that understands each channel-plugin contract
#: (source/extra-requirements-update.md section 3 - compatibility matrix).
CHANNEL_PLUGIN_MIN_AGENT = "1.1.0"
