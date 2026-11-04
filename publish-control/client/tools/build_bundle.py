"""Per-file SHA-256 + MANIFEST.json + SHA256SUMS.txt with read-back verify.

Reuses the Mac build_bundle.py discipline (Mac plan section 5.2).  Run it to
fingerprint the shipped package; the installer verifies the same manifest
before trusting a downloaded update.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}
SKIP_FILES = {"MANIFEST.json", "SHA256SUMS.txt"}
SELF_BINDING_REL = "PACKAGE_BINDING.json"
SELF_BINDING_FIELD = "snapshot_manifest_sha256"
ZERO_SHA256 = "0" * 64


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        # 1.2.5 (GPT review item 5): only the ROOT manifest / sums are excluded;
        # a nested ``agent/MANIFEST.json`` is a real (unexpected) file, not one
        # to skip by basename.
        if path.relative_to(root).as_posix() in SKIP_FILES:
            continue
        yield path


def _canonical_binding_bytes(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True)
            + "\n").encode("utf-8")


def write_self_binding(path: Path, data: dict) -> None:
    """Write the in-package binding in its canonical, hash-stable form."""
    payload = dict(data)
    payload.setdefault(SELF_BINDING_FIELD, ZERO_SHA256)
    Path(path).write_bytes(_canonical_binding_bytes(payload))


def self_binding_digest(path: Path) -> str | None:
    """Hash the binding with its self-referential field zeroed.

    ``PACKAGE_BINDING.json`` must name the SHA-256 of the *finished* app-tree
    MANIFEST.json.  A raw hash of the binding file itself would therefore be
    circular (the manifest records the binding, whose bytes record the manifest
    hash).  The binding is the one file whose manifest entry is defined over its
    canonical form with ``snapshot_manifest_sha256`` zeroed; the final manifest
    still contains all 3203 package entries.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or SELF_BINDING_FIELD not in data:
        return None
    data[SELF_BINDING_FIELD] = ZERO_SHA256
    return hashlib.sha256(_canonical_binding_bytes(data)).hexdigest()


def _entry_digest(root: Path, rel: str, info: dict) -> str:
    if info.get("self_binding"):
        value = self_binding_digest(root / rel)
        if value is None:
            raise RuntimeError("self-binding file is unreadable: " + rel)
        return value
    return sha256_of(root / rel)


def _parse_sums(path: Path) -> dict:
    """Parse the strict ``<sha256>  <relative path>`` format we generate."""
    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, separator, rel = line.partition("  ")
        if separator != "  " or len(digest) != 64 or not rel:
            raise ValueError("invalid SHA256SUMS line: %r" % line)
        if any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise ValueError("invalid SHA256SUMS digest: %r" % line)
        entries[rel] = digest.lower()
    return entries


def _expected_sums(files: dict) -> dict:
    # A self-referential binding cannot appear in a plain sha256sum file
    # without failing the standard checker; its integrity is bound by the
    # manifest's canonical self-binding entry on the next line.
    return {rel: info["sha256"].lower() for rel, info in files.items()
            if not info.get("self_binding")}


def _check_written_manifest(root: Path, out_dir: Path, files: dict) -> None:
    """Read back both indexes and prove they describe the same real bytes."""
    manifest_path = out_dir / "MANIFEST.json"
    sums_path = out_dir / "SHA256SUMS.txt"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("files") != files:
        raise RuntimeError("MANIFEST.json read-back differs from the built file map")
    actual_sums = _parse_sums(sums_path)
    expected_sums = _expected_sums(files)
    if actual_sums != expected_sums:
        raise RuntimeError("SHA256SUMS.txt is not in sync with MANIFEST.json")
    for rel, info in files.items():
        if _entry_digest(root, rel, info) != info["sha256"]:
            raise RuntimeError("read-back hash changed for %s" % rel)


def build(root: Path, out_dir: Path | None = None, *, version="1.0.0") -> dict:
    root = Path(root)
    out_dir = Path(out_dir) if out_dir else root
    binding_path = out_dir / SELF_BINDING_REL
    if binding_path.exists():
        try:
            binding = json.loads(binding_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            binding = None
        if isinstance(binding, dict) and SELF_BINDING_FIELD in binding:
            binding["version"] = version
            binding[SELF_BINDING_FIELD] = ZERO_SHA256
            write_self_binding(binding_path, binding)
    files = {}
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if rel == SELF_BINDING_REL:
            digest = self_binding_digest(path)
            if digest is not None:
                files[rel] = {"sha256": digest,
                              "bytes": path.stat().st_size,
                              "self_binding": True}
                continue
        files[rel] = {"sha256": sha256_of(path), "bytes": path.stat().st_size}
    manifest = {"schema_version": "1.0", "version": version, "files": files}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    lines = [f"{digest}  {rel}" for rel, digest in
             sorted(_expected_sums(files).items())]
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n",
                                            encoding="utf-8")
    if any(info.get("self_binding") for info in files.values()):
        binding_path = out_dir / SELF_BINDING_REL
        data = json.loads(binding_path.read_text(encoding="utf-8-sig"))
        data["version"] = version
        data[SELF_BINDING_FIELD] = sha256_of(out_dir / "MANIFEST.json")
        write_self_binding(binding_path, data)
        entry = files[SELF_BINDING_REL]
        if self_binding_digest(binding_path) != entry["sha256"]:
            raise RuntimeError("self-binding canonical hash changed")
        if binding_path.stat().st_size != entry["bytes"]:
            raise RuntimeError("self-binding size changed")
    _check_written_manifest(root, out_dir, files)
    return manifest


def verify(root: Path) -> dict:
    """Re-read every file and compare against MANIFEST.json (read-back check).

    1.2.5 (GPT review item 5): this is STRICT in three ways the 1.2.4 reviewer
    found wanting --
      * a MISSING or CHANGED file fails (as before);
      * an EXTRA file anywhere in the tree fails -- the previous version
        exempted a bytecode cache whose ``.py`` source was in the manifest, so a
        rogue ``__pycache__/rogue.pyc`` (or ANY unlisted ``.pyc``) slipped
        through.  "The source exists" does NOT prove the cached bytes are
        trustworthy, so now EVERY unlisted file is a failure (the shipped tree
        never contains ``__pycache__``; bytecode writing is disabled at runtime);
      * an EMPTY manifest fails instead of reporting "0 files, all good".
    """
    root = Path(root)
    manifest_path = root / "MANIFEST.json"
    if not manifest_path.exists():
        return {"ok": False, "reason": "MANIFEST.json missing"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return {"ok": False, "reason": "MANIFEST.json has no files (empty)",
                "mismatches": [], "missing": [], "extras": [],
                "file_count": 0}
    mismatches, missing = [], []
    for rel, info in files.items():
        target = root / rel
        if not target.exists():
            missing.append(rel)
            continue
        if _entry_digest(root, rel, info) != info["sha256"]:
            mismatches.append(rel)
    known = set(files)
    extras = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in known or rel in SKIP_FILES:
            continue
        extras.append(rel)
    sums_errors, sums_missing, sums_mismatches, sums_extras = [], [], [], []
    sums_path = root / "SHA256SUMS.txt"
    try:
        sums = _parse_sums(sums_path)
    except (OSError, ValueError) as exc:
        sums = {}
        sums_errors.append(str(exc))
    expected = _expected_sums(files)
    sums_missing = sorted(set(expected) - set(sums))
    sums_extras = sorted(set(sums) - set(expected))
    sums_mismatches = sorted(rel for rel in set(expected) & set(sums)
                             if expected[rel] != sums[rel])
    binding_errors = []
    binding_path = root / SELF_BINDING_REL
    try:
        binding = json.loads(binding_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        binding = None
        binding_errors.append("PACKAGE_BINDING.json unreadable: %s" % exc)
    actual_manifest_sha256 = sha256_of(manifest_path)
    if isinstance(binding, dict):
        bound = str(binding.get(SELF_BINDING_FIELD) or "").strip().lower()
        if bound != actual_manifest_sha256:
            binding_errors.append(
                "PACKAGE_BINDING.json %s is %r, but MANIFEST.json sha256 is %s"
                % (SELF_BINDING_FIELD, bound or None, actual_manifest_sha256))
    ok = not (mismatches or missing or extras or sums_errors
              or sums_missing or sums_mismatches or sums_extras
              or binding_errors)
    return {"ok": ok, "mismatches": mismatches, "missing": missing,
            "extras": sorted(extras), "file_count": len(files),
            "sums_errors": sums_errors, "sums_missing": sums_missing,
            "sums_mismatches": sums_mismatches, "sums_extras": sums_extras,
            "manifest_sha256": actual_manifest_sha256,
            "binding_errors": binding_errors}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="build_bundle")
    parser.add_argument("action", choices=["build", "verify"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--out")
    parser.add_argument("--version", default="1.0.0")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.action == "build":
        manifest = build(root, Path(args.out) if args.out else None,
                         version=args.version)
        print(f"built MANIFEST.json with {len(manifest['files'])} files")
        return 0
    result = verify(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
