#!/usr/bin/env python3
"""Refuse a release that is not cut from main (1.2.219).

1.2.215 was tagged on a side branch (rel/1.2.205) and silently dropped fixes
already merged to main.  A release tag must:
  * look like v<VERSION> and match publish-control/client/VERSION at the tag;
  * point at a commit that is already on main (an ancestor of --main);
  * optionally (--manifest/--zip) carry an OTA manifest + patch that pass
    ``ota_patch.py check --simulate`` with a valid vendor signature.

    python3 tools/release_guard.py --tag v1.2.219 [--main origin/main]
        [--manifest manifest.json --zip patch-1.2.219.zip]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import ota_patch  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--main", default="origin/main")
    ap.add_argument("--repo", default=str(TOOLS))
    ap.add_argument("--manifest")
    ap.add_argument("--zip")
    a = ap.parse_args(argv)
    repo = ota_patch.repo_root(Path(a.repo))
    fails = []
    tag = a.tag.removeprefix("refs/tags/")
    if not tag.startswith("v"):
        fails.append("tag %r must be v<version>" % tag)
    try:
        commit = ota_patch.git(repo, "rev-parse", tag + "^{commit}").decode().strip()
    except ota_patch.GitError as exc:
        print("FAIL  %s" % exc)
        return 1
    version = ota_patch.version_at(repo, commit)
    if tag[1:] != version:
        fails.append("tag %s but publish-control/client/VERSION is %s" % (tag, version))
    on_main = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                              commit, a.main]).returncode == 0
    if not on_main:
        fails.append("%s (%s) is not on %s: releases must be cut from main, never "
                     "from a side branch" % (tag, commit[:12], a.main))
    if a.manifest or a.zip:
        if not (a.manifest and a.zip):
            fails.append("--manifest and --zip go together")
        else:
            report = ota_patch.check(repo, commit, Path(a.manifest), Path(a.zip),
                                     simulate=True, require_signature=True)
            ota_patch._print(report)
            fails += ["OTA: " + f for f in report["fails"]]
    for f in fails:
        print("FAIL  " + f)
    print("RELEASE GUARD: %s (%s -> %s)" % ("PASS" if not fails else "FAIL", tag, commit[:12]))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
