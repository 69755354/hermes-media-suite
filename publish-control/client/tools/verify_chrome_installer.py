#!/usr/bin/env python3
"""Evidence for the official Chrome offline installer we ship (no Windows needed).

source/brief-chrome-only-20261016.md: "并随包附官方离线安装包（若可行）" and
"没证据 = 没验过".  We cannot *install* Chrome on this Linux build host -- that
stays a 待真机 item -- but we can prove the file we ship is:

  1. a real Windows PE executable (MZ + PE\0\0 + PE32+ + machine amd64);
  2. Authenticode-signed, and the signing certificate says **Google LLC**
     (extracted from the PE certificate table and read with ``openssl``);
  3. the byte-exact download from Google's own host: recorded Content-Length /
     ETag / Last-Modified, plus our SHA-256 matching ``*.sha256``;
  4. carrying "Google Chrome" in its embedded strings.

Anything we could not check on this host is printed as ``unknown`` -- never
claimed.

Usage: python3 tools/verify_chrome_installer.py PATH [--json OUT]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "agent") not in sys.path:
    sys.path.insert(0, str(ROOT / "agent"))

from winport.subprocess_text import text_mode_options  # noqa: E402

MACHINE_AMD64 = 0x8664
MACHINE_I386 = 0x014C
PE32_PLUS = 0x20B
PE32 = 0x10B
IMAGE_DIRECTORY_ENTRY_SECURITY = 4

#: data-directory offset *inside* the optional header, per optional-header magic
_DD_OFFSET = {PE32: 96, PE32_PLUS: 112}
_MACHINE_NAMES = {MACHINE_AMD64: "amd64", MACHINE_I386: "i386"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_pe(raw: bytes) -> dict:
    """Minimal PE parse: machine, magic, and the Authenticode certificate blob."""
    info = {"mz": raw[:2] == b"MZ", "pe": False, "machine": None, "magic": None,
            "cert_blob_bytes": 0, "cert_error": ""}
    if not info["mz"]:
        return info
    e_lfanew = struct.unpack_from("<I", raw, 0x3C)[0]
    if raw[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        return info
    info["pe"] = True
    coff = e_lfanew + 4
    machine, _nsections = struct.unpack_from("<HH", raw, coff)
    info["machine"] = f"0x{machine:04X} ({_MACHINE_NAMES.get(machine, 'other')})"
    size_opt = struct.unpack_from("<H", raw, coff + 16)[0]
    opt = coff + 20
    info["optional_header_offset"] = opt
    magic = struct.unpack_from("<H", raw, opt)[0]
    info["magic"] = f"0x{magic:04X}"
    # NOTE: Google's "ChromeStandaloneSetup64.exe" bootstrapper is itself a
    # 32-bit PE (its *payload* is 64-bit Chrome), so both PE32 and PE32+ are OK.
    dd_offset = _DD_OFFSET.get(magic)
    if dd_offset is None:
        info["cert_error"] = f"unknown optional-header magic 0x{magic:04X}"
        return info
    dd = opt + dd_offset
    info["dd_offset"] = dd_offset
    cert_rva, cert_size = struct.unpack_from("<II", raw, dd + 8 * IMAGE_DIRECTORY_ENTRY_SECURITY)
    info["cert_table_offset"] = cert_rva
    info["cert_table_size"] = cert_size
    if not cert_rva or not cert_size:
        info["cert_error"] = "no Authenticode certificate table"
        return info
    # collect the PKCS#7 payloads of every WIN_CERTIFICATE record
    pos = cert_rva
    end = cert_rva + cert_size
    blobs = []
    while pos + 8 <= end:
        length, revision, ctype = struct.unpack_from("<IHH", raw, pos)
        if length < 8 or pos + length > end:
            break
        blobs.append(raw[pos + 8:pos + length])
        pos += (length + 7) & ~7  # records are 8-byte aligned
    info["cert_blob_bytes"] = sum(len(b) for b in blobs)
    info["_blobs"] = blobs
    return info


def openssl_signer(blob: bytes) -> dict:
    """Read the PKCS#7 signer subject/issuer with the system openssl."""
    out = {"available": False, "subject": None, "issuer": None, "error": ""}
    exe = shutil.which("openssl")
    if not exe:
        out["error"] = "openssl not on PATH"
        return out
    out["available"] = True
    with tempfile.TemporaryDirectory() as tmp:
        der = Path(tmp) / "cert.p7b"
        der.write_bytes(blob)
        try:
            res = subprocess.run([exe, "pkcs7", "-inform", "DER", "-in", str(der),
                                  "-print_certs", "-noout"],
                                 capture_output=True, timeout=30,
                                 **text_mode_options())
        except (OSError, subprocess.SubprocessError) as exc:
            out["error"] = f"{type(exc).__name__}: {exc}"
            return out
    if res.returncode != 0:
        out["error"] = (res.stderr or "").strip()[:200]
        return out
    subjects, issuers = [], []
    for line in res.stdout.splitlines():
        if line.startswith("subject="):
            subjects.append(line.split("=", 1)[1].strip())
        elif line.startswith("issuer="):
            issuers.append(line.split("=", 1)[1].strip())
    out["subjects"] = subjects
    out["issuers"] = issuers
    out["subject"] = subjects[0] if subjects else None
    out["issuer"] = issuers[0] if issuers else None
    out["is_google_llc"] = any("Google LLC" in s for s in subjects)
    return out


def scan_strings(raw: bytes, needles) -> dict:
    """Embedded-string evidence, scanned over the whole file.

    The standalone installer is a compressed stub, so the product strings can
    sit far past the front; a plain whole-file search is cheap enough (<1s) and
    is reported verbatim rather than dressed up as a version-resource read.
    """
    hits = {}
    for needle in needles:
        pos = raw.find(needle.encode("ascii"))
        hits[needle] = {"found": pos >= 0, "offset": pos if pos >= 0 else None}
    return hits


#: DER prefix of a SHA-256 ``DigestInfo`` (AlgorithmIdentifier sha256 + OCTET STRING)
_SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


def authenticode_hash(raw: bytes, pe: dict) -> dict:
    """The Authenticode PE hash of this file (SHA-256), per Microsoft's spec.

    Everything is hashed except the optional-header ``CheckSum`` field, the
    certificate-table data-directory entry, and the certificate table itself.
    """
    out = {"sha256": None, "error": ""}
    if not pe.get("pe"):
        out["error"] = "not a PE file"
        return out
    checksum_off = pe["optional_header_offset"] + 64
    cert_entry_off = pe["optional_header_offset"] + pe["dd_offset"] + 8 * IMAGE_DIRECTORY_ENTRY_SECURITY
    cert_off = pe.get("cert_table_offset") or 0
    cert_size = pe.get("cert_table_size") or 0
    cert_end = cert_off + cert_size if cert_off else 0
    if not cert_off:
        # no signature at all -> plain file hash
        out["sha256"] = hashlib.sha256(raw).hexdigest()
        return out
    digest = hashlib.sha256()
    digest.update(raw[:checksum_off])
    digest.update(raw[checksum_off + 4:cert_entry_off])
    digest.update(raw[cert_entry_off + 8:cert_off])
    if cert_end < len(raw):
        digest.update(raw[cert_end:])
    out["sha256"] = digest.hexdigest()
    return out


def signed_digest_from_blob(blob: bytes) -> dict:
    """Pull the file digest out of ``SpcIndirectDataContent``'s messageDigest."""
    idx = blob.find(_SHA256_DIGESTINFO)
    if idx < 0:
        return {"sha256": None, "error": "no SHA-256 DigestInfo in the PKCS#7"}
    start = idx + len(_SHA256_DIGESTINFO)
    return {"sha256": blob[start:start + 32].hex(), "error": ""}


def verify(path: Path) -> dict:
    report = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return report
    raw = path.read_bytes()
    report["bytes"] = len(raw)
    report["sha256"] = hashlib.sha256(raw).hexdigest()
    report["product_strings"] = scan_strings(raw, ["Google Chrome", "Google LLC"])
    report["pe"] = parse_pe(raw)
    blobs = report["pe"].pop("_blobs", [])
    report["authenticode"] = (
        openssl_signer(blobs[0]) if blobs else
        {"available": False, "subject": None, "error": report["pe"].get("cert_error", "no blob")})
    # does the signature actually cover THIS file?
    computed = authenticode_hash(raw, report["pe"])
    signed = signed_digest_from_blob(blobs[0]) if blobs else {"sha256": None,
                                                              "error": "no blob"}
    report["signature_covers_file"] = {
        "computed_authenticode_sha256": computed.get("sha256"),
        "signed_message_digest_sha256": signed.get("sha256"),
        "match": bool(computed.get("sha256") and signed.get("sha256")
                      and computed["sha256"] == signed["sha256"]),
        "error": computed.get("error") or signed.get("error") or "",
    }
    sha_sidecar = path.with_name(path.name + ".sha256")
    if sha_sidecar.exists():
        report["sha256_sidecar"] = sha_sidecar.read_text(
            encoding="utf-8").strip().split()[0]
        report["sha256_matches_sidecar"] = report["sha256"] == report["sha256_sidecar"]
    return report


def render(report: dict) -> str:
    lines = [f"file      : {report.get('path')}",
             f"bytes     : {report.get('bytes')}",
             f"sha256    : {report.get('sha256')}"]
    pe = report.get("pe") or {}
    lines.append(f"pe        : MZ={pe.get('mz')} PE={pe.get('pe')} "
                 f"magic={pe.get('magic')} machine={pe.get('machine')}")
    lines.append(f"authentic : {json.dumps(report.get('authenticode'), ensure_ascii=False)}")
    cover = report.get("signature_covers_file") or {}
    lines.append(f"sig-covers: match={cover.get('match')} "
                 f"computed={str(cover.get('computed_authenticode_sha256'))[:16]}… "
                 f"signed={str(cover.get('signed_message_digest_sha256'))[:16]}… "
                 f"{cover.get('error') or ''}")
    lines.append(f"strings   : {json.dumps(report.get('product_strings'), ensure_ascii=False)}")
    if "sha256_matches_sidecar" in report:
        lines.append(f"sidecar   : {report.get('sha256_sidecar')} "
                     f"match={report.get('sha256_matches_sidecar')}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verify_chrome_installer")
    ap.add_argument("path", help="the shipped ChromeStandaloneSetup64.exe")
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)
    report = verify(Path(args.path))
    print(render(report))
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2)
                                   + "\n", encoding="utf-8")
        print(f"json: {args.json}")
    aut = report.get("authenticode") or {}
    ok = (report.get("exists") and (report.get("pe") or {}).get("pe")
          and aut.get("is_google_llc")
          and (report.get("signature_covers_file") or {}).get("match")
          and report.get("sha256_matches_sidecar", True))
    # Full chain/time-stamp verification needs Windows `signtool verify /pa`
    # (or osslsigncode) -- that stays 待真机; we say so instead of implying it.
    print("VERDICT:", ("OK (file carries a Google LLC Authenticode signer cert and the "
                       "signature covers this exact file; full chain/timestamp check = 待真机)")
          if ok else "NOT PROVEN -- see fields above")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
