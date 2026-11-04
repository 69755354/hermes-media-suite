#!/usr/bin/env python3
"""Smoke test for the unified gate chain.

Every adapter in workflow_gate.LEGACY_MAP must exist in this checkout and must
run far enough to return a business verdict (ALLOWED / BLOCKED / WARN) instead
of dying on a missing import or a hardcoded /home/ubuntu path.

Usage: python3 scripts/test_gate_chain.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# Fixture file names are Chinese by contract; escaped so this file stays ASCII.
N3_PLAYBOOK = "\u8282\u70b93_\u6253\u6cd5\u65b9\u6848.md"
N4_COPY = "\u8282\u70b94_\u6587\u6848v{}.md"
N4_REVIEW = "\u8282\u70b94_\u8bc4\u5ba1\u62a5\u544a.md"
N10_PROMPT = "\u8282\u70b910_\u63d0\u793a\u8bcd.md"
N11_QC = "\u8282\u70b911_\u8d28\u68c0\u62a5\u544a.md"
PRELOAD = "_\u9884\u8bfb_{}.md"

failures = []


def check(name, condition, detail=""):
    if condition:
        print("PASS %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        failures.append(name)


def run(*args, env=None):
    return subprocess.run([PY] + list(args), capture_output=True, text=True,
                          cwd=HERE, env=env)


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def fixture(proj):
    # 平台组合 / 内容配比 / 阶段节奏 / 投流策略 / 变现方式
    write(os.path.join(proj, N3_PLAYBOOK),
          "\u5e73\u53f0\u7ec4\u5408 \u5185\u5bb9\u914d\u6bd4 \u9636\u6bb5\u8282\u594f "
          "\u6295\u6d41\u7b56\u7565 \u53d8\u73b0\u65b9\u5f0f\n")
    for index in (1, 2, 3):
        write(os.path.join(proj, N4_COPY.format(index)), "v%d\n" % index)
    write(os.path.join(proj, N4_REVIEW), "PASS\n")
    write(os.path.join(proj, N10_PROMPT), "x\n")
    write(os.path.join(proj, N11_QC), "ok\n")
    baseline = [
        "/home/ubuntu/.hermes/skills/newmedia-operations/content-data-review/SKILL.md",
        "/home/ubuntu/.hermes/skills/newmedia-operations/content-review-gate/SKILL.md",
        "/home/ubuntu/.hermes/skills/newmedia-operations/video-production/SKILL.md",
        "/home/ubuntu/.hermes/skills/newmedia-operations/content-redlines/SKILL.md",
        "/home/ubuntu/.hermes/skills/newmedia-operations/huolong-replica-template/references/current-rulings-20261001.md",
    ]
    for node in ("5", "10", "11"):
        write(os.path.join(proj, PRELOAD.format(node)),
              "- \u8981\u70b9: ok\n" + "\n".join("- " + item for item in baseline) + "\n")


def main():
    sys.path.insert(0, HERE)
    import workflow_gate
    import workflow_ticket
    import codex_preload_manifest

    # 1. every legacy adapter named by the gate must be in this checkout
    missing = []
    for pairs in workflow_gate.LEGACY_MAP.values():
        for script, _gate in pairs or []:
            if not os.path.isfile(os.path.join(workflow_gate.SCRIPTS, script)):
                missing.append(script)
    check("legacy adapters present", not missing, ",".join(sorted(set(missing))))
    check("registry present", os.path.isfile(workflow_gate.REGISTRY), workflow_gate.REGISTRY)
    check("creative route present", os.path.isfile(workflow_gate.CREATIVE_ROUTE_TABLE),
          workflow_gate.CREATIVE_ROUTE_TABLE)
    check("node map present", os.path.isfile(workflow_ticket.NODE_MAP), workflow_ticket.NODE_MAP)

    # 2. env roots drive path resolution (no silent fallback to /home/ubuntu)
    with tempfile.TemporaryDirectory() as fake_wf, tempfile.TemporaryDirectory() as fake_hm:
        env = dict(os.environ, WORKFLOW_HOME=fake_wf, HERMES_HOME=fake_hm)
        code = ("import sys; sys.path.insert(0, %r); import codex_preload_manifest as m; "
                "print(m.WORKFLOW_HOME); print(m.HERMES_HOME); print(m.NEW_RULINGS)" % HERE)
        out = subprocess.run([PY, "-c", code], capture_output=True, text=True, env=env)
        lines = out.stdout.splitlines()
        check("preload roots follow env",
              out.returncode == 0 and lines[:2] == [fake_wf, fake_hm],
              out.stdout + out.stderr)
        check("preload file paths follow env",
              len(lines) > 2 and lines[2].startswith(fake_hm + "/"),
              out.stdout + out.stderr)

    with tempfile.TemporaryDirectory() as proj:
        fixture(proj)

        result = run("review_gate.py", "check", proj, "node3_strategy")
        check("review_gate node3_strategy runs", result.returncode == 0,
              result.stdout + result.stderr)

        result = run("review_gate.py", "check", proj, "node4_review")
        check("review_gate node4_review runs (preload import)", result.returncode == 0,
              result.stdout + result.stderr)

        result = run("review_gate.py", "check", proj, "node12_pre")
        check("review_gate node12_pre reaches preload stage",
              "preload_10_11" in (result.stdout + result.stderr) or result.returncode == 0,
              result.stdout + result.stderr)

        result = run("data_source_gate.py", "check", proj, "node4_body")
        check("data_source_gate runs", any(
            marker in (result.stdout + result.stderr) for marker in ("node4_body", "ALLOWED")),
            result.stdout + result.stderr)

        result = run("codex_preload_manifest.py", "check", proj, "4")
        check("preload manifest runs", result.returncode == 2 and "preload_4" in result.stdout,
              result.stdout + result.stderr)

        result = run("director_review_scorer.py", "--help")
        check("director_review_scorer runs", result.returncode == 0,
              result.stdout + result.stderr)

        result = run("workflow_ticket.py", "classify", "process job 123")
        ok = result.returncode == 0
        try:
            json.loads(result.stdout)
        except ValueError:
            ok = False
        check("workflow_ticket classify runs", ok, result.stdout + result.stderr)

        result = run("workflow_ticket.py", "status")
        check("workflow_ticket status runs", result.returncode == 0,
              result.stdout + result.stderr)

        result = run("workflow_gate.py", "status", proj)
        check("workflow_gate status runs", result.returncode == 0,
              result.stdout + result.stderr)

    if failures:
        print("\n%d check(s) failed: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("\nall gate chain checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
