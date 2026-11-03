"""Python side of the offline bootstrap (called by scripts/bootstrap.ps1).

Idempotent and re-runnable: creates the data area, seeds config templates only
when absent (never overwrites login state / ledger / settings), verifies that
the bundled offline artefacts are present, then runs the self-test.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .errors import EXIT_CONFIG, EXIT_OK, EXIT_STORAGE
from .jsonio import write_json
from .paths import Layout
from .selftest import print_selftest, run_selftest

# Offline artefacts that MUST be inside the package (no network fetch at install).
REQUIRED_BUNDLE = (
    "runtime/python.exe",
    "browsers",
    "wheels",
    "bin/ffmpeg.exe",
)


def verify_bundle(program: Path):
    missing = []
    for rel in REQUIRED_BUNDLE:
        if not (program / rel).exists():
            missing.append(rel)
    return missing


def seed_config(layout: Layout, program: Path) -> list:
    """Copy *.tmpl templates to real files only if the target is absent."""
    seeded = []
    tpl_dir = program / "config"
    pairs = [("settings.json.tmpl", layout.settings_file),
             ("accounts.json.tmpl", layout.accounts_file),
             ("channels.json.tmpl", layout.channels_file)]
    for tpl_name, target in pairs:
        tpl = tpl_dir / tpl_name
        if target.exists():
            continue
        if tpl.exists():
            shutil.copyfile(tpl, target)
        else:
            write_json(target, {})
        seeded.append(str(target))
    return seeded


def run_bootstrap(program=None, data=None, *, static=None, verbose=True) -> int:
    layout = Layout(program=program, data=data)
    try:
        layout.ensure()
    except Exception as exc:
        print(f"BOOTSTRAP FAILED (storage): {exc}")
        return EXIT_STORAGE

    missing = verify_bundle(layout.program)
    seeded = seed_config(layout, layout.program)
    if verbose:
        print(f"program area : {layout.program}")
        print(f"data area    : {layout.data}")
        print(f"config seeded: {seeded or 'none (already present)'}")
        if missing:
            print(f"bundle missing (offline install incomplete): {missing}")

    result = run_selftest(layout, static=static)
    if verbose:
        print_selftest(result)
    # A missing offline bundle is fatal only on the real Windows install; on the
    # static host it is reported (see VERIFY.md).
    if missing and (static is False or (static is None and sys.platform == "win32")):
        return EXIT_CONFIG
    return result["exit_code"]


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="winport.bootstrap")
    parser.add_argument("--program")
    parser.add_argument("--data")
    parser.add_argument("--static", action="store_true")
    args = parser.parse_args(argv)
    return run_bootstrap(program=Path(args.program) if args.program else None,
                         data=Path(args.data) if args.data else None,
                         static=True if args.static else None)


if __name__ == "__main__":
    raise SystemExit(main())
