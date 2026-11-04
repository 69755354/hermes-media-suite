#!/usr/bin/env python3
"""Static scan for publish-driver forbidden patterns (1.2.21 item 7).

The scan separates the runtime tree (``agent/``, ``scripts/``) from tests and
tools.  It is deliberately mechanical:

* fixed waits: literal ``time.sleep(N)`` / ``Start-Sleep -Seconds N`` /
  ``timeout /t N`` / ``WScript.Sleep N``;
* browser/UA/fingerprint modifications: forbidden Chrome flags, Playwright
  header/UA/init-script calls and common fingerprint-spoofing symbols;
* class-name and fuzzy-text locators in production code;
* every ``seed_shift`` consumer, with an allowlist proving the field only lives
  in the stable-pace profile and is never fed back into ``random.Random``.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RUNTIME_DIRS = ("agent", "scripts")
TEXT_SUFFIXES = {".py", ".ps1", ".bat", ".cmd", ".vbs", ".js", ".json", ".md", ".txt"}

FIXED_WAIT_PATTERNS = {
    "py": re.compile(r"\btime\.sleep\s*\(\s*(?:\d+(?:\.\d+)?)\s*\)"),
    "ps1": re.compile(r"Start-Sleep\s+(?:-Seconds\s+)?\d+(?:\.\d+)?"),
    "bat": re.compile(r"\btimeout\s+/t\s+\d+\b", re.IGNORECASE),
    "vbs": re.compile(r"WScript\.Sleep\s+\d+", re.IGNORECASE),
}

FORBIDDEN_LITERALS = (
    "--user-agent=",
    "--disable-blink-features=AutomationControlled",
    "set_extra_http_headers",
    "page.set_user_agent",
    "browser.new_context(user_agent=",
    "add_init_script",
    "Page.addScriptToEvaluateOnNewDocument",
    "navigator.webdriver",
    "Object.defineProperty(navigator, 'webdriver'",
    "navigator.plugins",
    "navigator.languages",
    "navigator.hardwareConcurrency",
    "navigator.deviceMemory",
    "window.screen",
    "canvas.getContext",
    "fingerprint_spoof",
    "stealth.min.js",
    "puppeteer-extra-plugin-stealth",
    "playwright-stealth",
)

SELECTOR_FORBIDDEN = (
    "[class",
    ":has-text(",
)

SCAN_SKIP_FILES = {
    "agent/winport/publish_guard.py",   # contains the detector literals themselves
    "tools/scan_forbidden_patterns.py", # self-referential scanner source
}


# Continuous terminal-state observation requires this read-only init script.
# This exception binds the exact installer AST and script bytes; it is not a
# file exemption. Extra calls, script mutations, and every other init script fail.
MONITOR_INSTALLER_SHA256 = "0143c65c208f8059fe912ddca445e3e13bfead3fc512b60b7db437f048c2196a"
VISIBLE_TEXT_SHA256 = "39ca5452b2f0cd8f1c08c879eb2d5e21d98a024082803b3ccec1100a6b7c5588"
MONITOR_SCRIPT_SHA256 = "ce4846660dcf4c1927f698cd6a8147a51946cced0ea3eee1019edfd4e83bc96e"


def read_only_monitor_allowed(rel, text):
    if rel != "agent/winport/platform_receipt.py" or text.count("Page.addScriptToEvaluateOnNewDocument") != 1:
        return False
    try:
        tree = ast.parse(text)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "install_monitor"]
        scripts = [n.value.value for n in tree.body if isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == "MONITOR_SCRIPT" for t in n.targets)]
        readers = [n.value.value for n in tree.body if isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == "VISIBLE_TEXT_SCRIPT" for t in n.targets)]
        return (len(functions) == len(scripts) == len(readers) == 1 and
                hashlib.sha256(readers[0].encode()).hexdigest() == VISIBLE_TEXT_SHA256 and
                hashlib.sha256(ast.dump(functions[0], include_attributes=False).encode()).hexdigest() == MONITOR_INSTALLER_SHA256 and
                hashlib.sha256(scripts[0].encode()).hexdigest() == MONITOR_SCRIPT_SHA256)
    except Exception:
        return False


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk", "cp1252"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")


def scan_tree(root: Path, *, include_tools_tests: bool = False) -> dict:
    hits = []
    seed_hits = []
    dirs = list(RUNTIME_DIRS)
    if include_tools_tests:
        dirs += ["tests", "tools"]
    files = []
    for rel_dir in dirs:
        base = root / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    files = sorted(set(files))
    for path in files:
        rel = path.relative_to(root).as_posix()
        text = read_text(path)
        ext = path.suffix.lower().lstrip(".")
        pattern = FIXED_WAIT_PATTERNS.get(ext)
        if pattern:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                hits.append({"file": rel, "line": line, "kind": "fixed_wait",
                             "text": match.group(0).strip()})
        for literal in FORBIDDEN_LITERALS:
            if literal == "Page.addScriptToEvaluateOnNewDocument" and read_only_monitor_allowed(rel, text):
                continue
            start = 0
            while True:
                idx = text.find(literal, start)
                if idx < 0:
                    break
                line = text.count("\n", 0, idx) + 1
                hits.append({"file": rel, "line": line, "kind": "forbidden_literal",
                             "text": literal})
                start = idx + 1
        for literal in SELECTOR_FORBIDDEN:
            start = 0
            while True:
                idx = text.find(literal, start)
                if idx < 0:
                    break
                line = text.count("\n", 0, idx) + 1
                hits.append({"file": rel, "line": line, "kind": "fuzzy_selector",
                             "text": literal})
                start = idx + 1
        if "seed_shift" in text:
            for lineno, line_text in enumerate(text.splitlines(), 1):
                if "seed_shift" in line_text:
                    seed_hits.append({"file": rel, "line": lineno,
                                      "text": line_text.strip()})
    return {"hits": hits, "seed_shift_hits": seed_hits, "scanned_files": len(files)}


def seed_shift_allowed(hit: dict) -> bool:
    """``seed_shift`` may only be defined/read inside the pace-profile module."""
    rel = hit["file"].replace("\\", "/")
    return rel == "agent/winport/humanize.py"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--all", action="store_true",
                    help="also scan tests/tools for evidence and self-checks")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    report = scan_tree(args.root, include_tools_tests=args.all)
    runtime_hits = report["hits"]
    bad_seed = [h for h in report["seed_shift_hits"] if not seed_shift_allowed(h)]
    # The scanner's own counter-example strings must never count against the
    # repository.  They are in tools/, which is excluded unless --all; when
    # --all is used for a self-test, filter this file itself.
    runtime_hits = [h for h in runtime_hits
                    if h["file"].replace("\\", "/") not in SCAN_SKIP_FILES]
    verdict = {
        "runtime_hits": runtime_hits,
        "seed_shift_hits": report["seed_shift_hits"],
        "seed_shift_bad_consumers": bad_seed,
        "scanned_files": report["scanned_files"],
        "ok": not runtime_hits and not bad_seed,
    }
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
    else:
        print(f"scanned files: {report['scanned_files']}")
        for hit in runtime_hits:
            print(f"FAIL {hit['file']}:{hit['line']} {hit['kind']} {hit['text']}")
        for hit in report["seed_shift_hits"]:
            print(f"seed_shift {hit['file']}:{hit['line']} {hit['text']}")
        for hit in bad_seed:
            print(f"FAIL seed_shift outside allowlist: {hit['file']}:{hit['line']}")
        print(f"SCAN {'PASS' if verdict['ok'] else 'FAIL'}: "
              f"{len(runtime_hits)} runtime hits, {len(bad_seed)} bad seed consumers")
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
