"""No code may carry a real customer's Windows user name.

The product is sold to many customers; a path like C:\\Users\\<someone>\\...
only works on one machine and silently targets the wrong directory on every
other.  Placeholders (<USER>, example, Public, CLIENT_HOME_NOT_SET) are fine.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCOPES = ("publish-control", "video-factory", "video-team", "scripts")
SUFFIXES = {".py", ".ps1", ".bat", ".cmd", ".vbs", ".sh", ".service"}
ALLOWED = {"<user>", "example", "public", "default", "client_home_not_set", "%username%"}
PATTERN = re.compile(r"[A-Za-z]:(?:\\{1,2}|/)Users(?:\\{1,2}|/)([^\\\"'\s/]+)", re.I)


class NoHardcodedWindowsUserTests(unittest.TestCase):
    def test_code_has_no_real_windows_user_names(self):
        found = []
        for scope in SCOPES:
            base = REPO / scope
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in SUFFIXES:
                    continue
                if "hotfix_" in str(path) or "__pycache__" in str(path) or path.name == Path(__file__).name:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for n, line in enumerate(text.splitlines(), 1):
                    for m in PATTERN.finditer(line):
                        if (m.group(1).lower() not in ALLOWED and not m.group(1).startswith("<")
                                and len(m.group(1)) > 1):  # "x" in usage text is a placeholder
                            found.append("%s:%d %s" % (path.relative_to(REPO), n, m.group(0)))
        self.assertEqual(found, [], "\n".join(found))


if __name__ == "__main__":
    unittest.main()
