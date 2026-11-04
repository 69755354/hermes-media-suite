"""Fail-closed scan for credentials and customer-facing build leaks.

The scanner is intentionally independent of the build code so it can be used
by tests, the bundler and a release operator on either a tree or a finished zip.
It never prints secret file contents.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

SKIP_PARTS = {".git", "__pycache__", ".pytest_cache"}
SENSITIVE_NAMES = {
    "relay_key", "client_key", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    "known_hosts", "token", "session.json", "activation.json",
    "credentials.json", ".env",
}
SENSITIVE_SUFFIXES = {".key", ".p12", ".pfx", ".jks", ".keystore"}
#: A public trust store is not a credential.  Pin the one third-party CA bundle
#: shipped inside the Python runtime; any other .pem file is still rejected.
PUBLIC_CA_ALLOWLIST = {
    "runtime/Lib/site-packages/pip/_vendor/certifi/cacert.pem",
}
BINARY_SUFFIXES = {
    ".exe", ".dll", ".pyd", ".so", ".dylib", ".bin", ".mp4", ".mov",
    ".webm", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".whl",
}
_KEY_HEAD = b"-----BEGIN "
_KEY_TAIL = b"PRIVATE KEY-----"
PRIVATE_MARKERS = tuple(
    _KEY_HEAD + kind + _KEY_TAIL
    for kind in (b"OPENSSH ", b"RSA ", b"EC ", b"DSA ", b"PGP ", b"ENCRYPTED ")
)
MAX_TEXT_SCAN = 2 * 1024 * 1024

CUSTOMER_DOCS = (
    "README.md", "VERIFY.md", "MATERIALS.md", "CUSTOMER_README.txt",
    "REMOTE_CHANNEL.md", "config/remote-channel-package.json",
)
FORBIDDEN_CUSTOMER_TEXT = (
    "127.0.0.1", "114.132.214.10", "43.160.200.21", "/tmp/", "/home/",
    "output/bundle_", "win-port", "remote-debugging-port", "9223", "9224",
)


def _sensitive_name(name):
    lowered = name.lower()
    return (lowered in SENSITIVE_NAMES or lowered.endswith(".pem") or
            any(lowered.endswith(s) for s in SENSITIVE_SUFFIXES))


#: The auto-enrolment config is a *designed* customer-side credential: it holds a
#: single-use, machine-bound enrolment token and nothing else.  It is allowed by
#: exact path AND only when its content is exactly {endpoint, enrollment_token}
#: with an https endpoint and a >=32 char token -- never a private key, never a
#: second secret.  Revocation is server-side (delete the entitlement row).
ENTITLEMENT_ALLOWLIST = {"config/activation.json"}


def _allowlisted_entitlement(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return any(rel == item or rel.endswith("/" + item) for item in ENTITLEMENT_ALLOWLIST)


def _valid_entitlement_file(data: bytes) -> bool:
    if not data or len(data) > 4096 or b"PRIVATE KEY" in data:
        return False
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except Exception:
        return False
    if not isinstance(obj, dict) or set(obj) != {"endpoint", "enrollment_token"}:
        return False
    endpoint = str(obj.get("endpoint") or "")
    token = str(obj.get("enrollment_token") or "")
    return endpoint.startswith("https://") and len(token) >= 32 and " " not in token


def _allowlisted_public_ca(rel):
    rel = rel.replace("\\", "/")
    return any(rel == item or rel.endswith("/" + item)
               for item in PUBLIC_CA_ALLOWLIST)


def _private_key_text(data):
    if not data or b"\x00" in data or len(data) > MAX_TEXT_SCAN:
        return None
    for marker in PRIVATE_MARKERS:
        if marker in data:
            return marker.decode("ascii", "replace")
    return None


def scan_tree(root):
    root = Path(root)
    findings = []
    if not root.exists():
        return {"ok": False, "root": str(root), "findings": [
            {"path": str(root), "reason": "root_missing"}]}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if _sensitive_name(path.name) and not _allowlisted_public_ca(rel):
            if _allowlisted_entitlement(rel) and _valid_entitlement_file(path.read_bytes()):
                pass
            else:
                findings.append({"path": rel, "reason": "sensitive_file_name"})
        if any(part.startswith(("evidence", "channel_fix_evidence"))
               for part in path.relative_to(root).parts[:-1]):
            findings.append({"path": rel, "reason": "debug_evidence_artifact"})
        if path.suffix.lower() in BINARY_SUFFIXES or path.stat().st_size > MAX_TEXT_SCAN:
            continue
        try:
            marker = _private_key_text(path.read_bytes())
        except OSError:
            marker = None
        if marker:
            findings.append({"path": rel, "reason": "private_key_body"})
    return {"ok": not findings, "root": str(root), "findings": findings}


def scan_zip(path):
    path = Path(path)
    findings = []
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        return {"ok": False, "zip": str(path), "findings": [
            {"path": str(path), "reason": "zip_unreadable:" + type(exc).__name__}]}
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            rel = info.filename
            name = rel.rsplit("/", 1)[-1]
            if _sensitive_name(name) and not _allowlisted_public_ca(rel):
                if _allowlisted_entitlement(rel) and _valid_entitlement_file(archive.read(info)):
                    pass
                else:
                    findings.append({"path": rel, "reason": "sensitive_file_name"})
            if any(part.startswith(("evidence", "channel_fix_evidence"))
                   for part in rel.split("/")[:-1]):
                findings.append({"path": rel, "reason": "debug_evidence_artifact"})
            if name.lower().endswith(tuple(BINARY_SUFFIXES)) or info.file_size > MAX_TEXT_SCAN:
                continue
            try:
                data = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                data = b""
            if _private_key_text(data):
                findings.append({"path": rel, "reason": "private_key_body"})
    return {"ok": not findings, "zip": str(path), "findings": findings}


def scan_customer_docs(root):
    root = Path(root)
    findings = []
    for rel in CUSTOMER_DOCS:
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for needle in FORBIDDEN_CUSTOMER_TEXT:
            if needle in text:
                findings.append({"path": rel, "reason": "customer_text_leak",
                                 "pattern": needle})
    return {"ok": not findings, "root": str(root), "findings": findings}


def scan(root):
    tree = scan_tree(root)
    docs = scan_customer_docs(root)
    findings = tree["findings"] + docs["findings"]
    return {"ok": not findings, "root": str(root), "findings": findings}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="package_secret_scan")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--root", type=Path)
    source.add_argument("--zip", type=Path)
    parser.add_argument("--customer-docs", action="store_true")
    args = parser.parse_args(argv)
    if args.zip:
        result = scan_zip(args.zip)
    elif args.customer_docs:
        result = scan_customer_docs(args.root)
    else:
        result = scan(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
