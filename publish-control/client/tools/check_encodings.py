#!/usr/bin/env python3
"""HARD build guard: encoding policy for every Windows-read text file.

Why this exists (source/brief-encoding-20261016.md, customer field failure):
a package built with BOM-less UTF-8 ``.ps1``/``.bat``/``.vbs`` files works on a
developer box (pwsh 7 / UTF-8 locale) and then dies on a Chinese customer's
Windows.  PowerShell 5.1 -- the ``powershell.exe`` every double-click entry
calls -- reads a BOM-less script with the system ANSI code page (GBK).  A UTF-8
Chinese character is 3 bytes; GBK re-partitions the byte stream, so the last
byte of a Chinese character can pair with the FOLLOWING ASCII byte and swallow
it.  When that ASCII byte is a quote or a brace, the parser reports
"unexpected token" / "missing closing brace" -- exactly what the customer saw.

The rule, enforced here and wired into the build (a violation FAILS the build):

  * .ps1 .psm1 .psd1                 -> UTF-8 WITH BOM (or UTF-16 with BOM, or pure ASCII)
  * .bat .cmd                        -> pure ASCII, or ANSI/GBK (no BOM)
  * .vbs .vbe .wsf .js .jse          -> pure ASCII, or ANSI/GBK, or UTF-16 with BOM
  * any other project text file      -> if it holds a non-ASCII byte it MUST carry a
                                        BOM (UTF-8 or UTF-16): no "BOM-less UTF-8
                                        Chinese" anywhere in the deliverable.
  * .ps1 .psm1 .psd1 .bat .cmd .vbs  -> CRLF line endings; a delivered script must
    .vbe .wsf .js .jse                  never be LF-only (cmd.exe / wscript /
                                        PowerShell 5.1 mis-parse it -- the real-machine
                                        failure that opened the CRLF ticket).

Deliberate exemptions (reported, never failed):
  * vendor material trees (runtime/ browsers/ bin/ wheels/) -- third-party bytes
    are not ours to rewrite;
  * Python sources (.py) -- Python 3 reads source as UTF-8 by default, no BOM
    needed (and a BOM there is discouraged).

Two modes:
  --root DIR     scan a built deliverable and fail on any violation
  --self-test    prove the detector actually bites: build a tiny corpus that
                 CONTAINS a BOM-less UTF-8 Chinese .ps1 (and .bat/.vbs/.txt) and
                 assert they are rejected -- "it passed" only means something if
                 a known-bad file is caught.

Exit codes: 0 = clean, 1 = violations found, 2 = self-test did not bite / bad
usage (the guard itself is broken).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

BOM8 = b"\xef\xbb\xbf"
BOM16LE = b"\xff\xfe"
BOM16BE = b"\xfe\xff"

PS_SUFFIXES = {".ps1", ".psm1", ".psd1"}
CMD_SUFFIXES = {".bat", ".cmd"}
WSH_SUFFIXES = {".vbs", ".vbe", ".wsf", ".js", ".jse"}
SCRIPT_SUFFIXES = PS_SUFFIXES | CMD_SUFFIXES | WSH_SUFFIXES

#: every text extension the guard looks at (scripts first; then data/docs)
TEXT_SUFFIXES = SCRIPT_SUFFIXES | {
    ".txt", ".md", ".json", ".xml", ".tmpl", ".hex", ".cfg", ".ini", ".csv",
    ".yaml", ".yml", ".html", ".htm", ".css", ".rst", ".log", ".py",
}

#: relative path prefixes whose bytes are third-party and must not be rewritten
VENDOR_PREFIXES = ("runtime/", "browsers/", "bin/", "wheels/")
#: Python source is UTF-8 by default in Python 3 -- BOM not required
PY_SUFFIXES = {".py"}


def classify(data: bytes) -> str:
    """Byte-level encoding fingerprint (never trusts the extension)."""
    if data.startswith(BOM8):
        return "utf8-bom"
    if data.startswith(BOM16LE):
        return "utf16le-bom"
    if data.startswith(BOM16BE):
        return "utf16be-bom"
    if all(b < 0x80 for b in data):
        return "ascii"
    try:
        data.decode("utf-8")
        # a BOM-less byte string that is valid UTF-8 and has non-ASCII bytes:
        # this is the exact "无 BOM 的 UTF-8 中文" the ticket bans.
        return "utf8-nobom"
    except UnicodeDecodeError:
        pass
    try:
        data.decode("gbk")
        return "gbk"
    except UnicodeDecodeError:
        return "binary"


def policy_for(suffix: str, cls: str):
    """Return (ok, why) for one file.  `ok=None` means exempt (report only)."""
    if suffix in PS_SUFFIXES:
        ok = cls in ("utf8-bom", "utf16le-bom", "utf16be-bom", "ascii")
        if not ok:
            return False, ("PowerShell script must be UTF-8 WITH BOM "
                           f"(got {cls}); PS 5.1 would decode it as ANSI/GBK")
        return True, f"{cls}"
    if suffix in CMD_SUFFIXES:
        ok = cls in ("ascii", "gbk")
        if not ok:
            return False, ("cmd script must be pure ASCII or ANSI/GBK "
                           f"(got {cls}); cmd.exe reads it as ANSI/GBK")
        return True, f"{cls}"
    if suffix in WSH_SUFFIXES:
        ok = cls in ("ascii", "gbk", "utf16le-bom", "utf16be-bom")
        if not ok:
            return False, ("WSH script must be ASCII, ANSI/GBK or UTF-16+BOM "
                           f"(got {cls}); WSH reads it as ANSI/GBK")
        return True, f"{cls}"
    # everything else (project data/docs): a non-ASCII file MUST carry a BOM
    ok = cls in ("ascii", "utf8-bom", "utf16le-bom", "utf16be-bom")
    if not ok:
        return False, ("text file holds non-ASCII bytes without a BOM "
                       f"(got {cls}); BOM-less UTF-8 Chinese is banned")
    return True, f"{cls}"


def _rel_posix(rel: str) -> str:
    return rel.replace(os.sep, "/")


def is_exempt(rel: str) -> str:
    """'' if enforced; otherwise the reason this file is report-only."""
    r = _rel_posix(rel)
    if r.startswith(VENDOR_PREFIXES):
        return "vendor material tree (not ours to rewrite)"
    if Path(r).suffix.lower() in PY_SUFFIXES:
        return "Python source (UTF-8 by default; BOM not required)"
    return ""


def scan(root: Path):
    """Walk `root`, return every text file with its verdict."""
    root = Path(root)
    findings = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in TEXT_SUFFIXES:
            continue
        rel = _rel_posix(str(path.relative_to(root)))
        data = path.read_bytes()
        cls = classify(data)
        exempt_reason = is_exempt(rel)
        if exempt_reason:
            findings.append({"path": rel, "suffix": suffix, "encoding": cls,
                             "ok": None, "exempt": exempt_reason,
                             "why": f"exempt: {exempt_reason}"})
            continue
        ok, why = policy_for(suffix, cls)
        # 1.2.5 round-16 (review advice): make the CRLF rule a BUILD GATE.  A
        # green byte check on one build must not be the only thing between us
        # and the next LF-only build, so the guard fails any delivered script
        # that is LF-only.
        if ok is True and suffix in SCRIPT_SUFFIXES:
            lf, crlf = data.count(b"\n"), data.count(b"\r\n")
            if lf > crlf:
                ok = False
                why = (f"LF-only line endings (LF={lf} CRLF={crlf}); Windows "
                       "cmd / wscript / PowerShell 5.1 need CRLF")
        findings.append({"path": rel, "suffix": suffix, "encoding": cls,
                         "ok": ok, "exempt": "", "why": why})
    return findings


def violations(findings):
    return [f for f in findings if f["ok"] is False]


# --------------------------------------------------------------------------- #
# counter-example corpus: prove the detector bites
# --------------------------------------------------------------------------- #
def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build_selftest_corpus(root: Path) -> None:
    cn = "中文测试字符串"
    utf8_nobom = cn.encode("utf-8")
    gbk = cn.encode("gbk")
    # -- known GOOD (must pass) --
    _write(root / "good.ps1", BOM8 + utf8_nobom)
    _write(root / "ascii.ps1", b"Write-Host ok\r\n")
    _write(root / "good.bat", b"@echo off\r\necho " + gbk + b"\r\n")
    _write(root / "good.vbs", gbk)
    _write(root / "good.txt", BOM8 + utf8_nobom)
    _write(root / "utf16.ps1", BOM16LE + cn.encode("utf-16-le"))
    _write(root / "runtime" / "lib.js", utf8_nobom)           # exempt vendor
    _write(root / "pkg" / "mod.py", utf8_nobom)                  # exempt python
    # -- known BAD (must be caught) --
    _write(root / "bad.ps1", utf8_nobom)
    _write(root / "bad.bat", utf8_nobom)
    _write(root / "bad.vbs", utf8_nobom)
    _write(root / "bad.txt", utf8_nobom)
    _write(root / "bad_lf.bat", b"@echo off\necho " + gbk + b"\n")
    _write(root / "bad_lf.ps1", BOM8 + b"Write-Host ok\n")


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="enc-guard-") as tmp:
        root = Path(tmp)
        build_selftest_corpus(root)
        findings = {f["path"]: f for f in scan(root)}
        must_fail = {"bad.ps1", "bad.bat", "bad.vbs", "bad.txt",
                     "bad_lf.bat", "bad_lf.ps1"}
        must_pass = {"good.ps1", "ascii.ps1", "good.bat", "good.vbs", "good.txt",
                     "utf16.ps1"}
        problems = []
        for rel in must_fail:
            f = findings.get(rel)
            if f is None:
                problems.append(f"{rel}: not scanned at all")
            elif f["ok"] is not False:
                problems.append(f"{rel}: NOT caught (ok={f['ok']}, {f['why']})")
        for rel in must_pass:
            f = findings.get(rel)
            if f is None:
                problems.append(f"{rel}: not scanned at all")
            elif f["ok"] is not True:
                problems.append(f"{rel}: false positive (ok={f['ok']}, {f['why']})")
        # vendor + python must be exempt, never failed
        for rel in ("runtime/lib.js", "pkg/mod.py"):
            f = findings.get(rel)
            if f is None or f["ok"] is not None:
                problems.append(f"{rel}: should be exempt, got {f}")

        print("=" * 72)
        print("ENCODING GUARD -- counter-example self-test")
        print("=" * 72)
        for rel, f in sorted(findings.items()):
            mark = {True: "PASS", False: "FAIL", None: "EXEMPT"}[f["ok"]]
            print(f"  [{mark:6}] {rel:24} {f['encoding']:12} {f['why']}")
        print("-" * 72)
        if problems:
            print("RESULT: BROKEN -- the guard did NOT bite where it must:")
            for p in problems:
                print(f"  - {p}")
            return 2
        print("RESULT: OK -- the BOM-less UTF-8 Chinese .ps1/.bat/.vbs/.txt were")
        print("        all caught; BOM'd/GBK/ASCII files passed; vendor+py exempt.")
        return 0


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", help="deliverable directory to scan")
    ap.add_argument("--log", help="also write a plain-text report here")
    ap.add_argument("--json", dest="json_out", help="also write the report as JSON")
    ap.add_argument("--self-test", action="store_true",
                    help="run the counter-example proof and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.root:
        ap.error("--root is required (or use --self-test)")
    root = Path(args.root)
    if not root.is_dir():
        print(f"BLOCKED: --root not a directory: {root}")
        return 1

    findings = scan(root)
    bad = violations(findings)
    enforced = [f for f in findings if f["ok"] is not None]
    exempt = [f for f in findings if f["ok"] is None]

    lines = []
    lines.append("=" * 72)
    lines.append("ENCODING GUARD -- deliverable scan")
    lines.append(f"root    : {root}")
    lines.append(f"scanned : {len(findings)} text files "
                 f"({len(enforced)} enforced, {len(exempt)} exempt)")
    lines.append("=" * 72)
    for f in enforced:
        if f["ok"]:
            lines.append(f"  [ OK ] {f['path']:48} {f['encoding']}")
    for f in bad:
        lines.append(f"  [FAIL] {f['path']:48} {f['encoding']}  <- {f['why']}")
    if exempt:
        lines.append("-" * 72)
        lines.append(f"  exempt (reported, not enforced): {len(exempt)} files")
        seen = {}
        for f in exempt:
            seen[f["exempt"]] = seen.get(f["exempt"], 0) + 1
        for reason, n in sorted(seen.items()):
            lines.append(f"    - {n:5}  {reason}")
    lines.append("-" * 72)
    if bad:
        lines.append(f"RESULT: FAIL -- {len(bad)} file(s) violate the encoding policy")
    else:
        lines.append("RESULT: OK -- every .ps1/.bat/.cmd/.vbs and every "
                     "project text file obeys the policy")
    text = "\n".join(lines) + "\n"
    print(text, end="")

    if args.log:
        Path(args.log).write_text(text, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"root": str(root), "scanned": len(findings),
                        "enforced": len(enforced), "exempt": len(exempt),
                        "violations": bad, "findings": findings},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
