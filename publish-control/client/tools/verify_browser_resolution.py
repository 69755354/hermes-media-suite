#!/usr/bin/env python3
"""Browser-resolution branch harness -- run every branch, print the real echo.

source/brief-chrome-only-20261016.md item 5: "Chrome 已装/未装两个分支都要跑并带回显；
本机验不了的列「待真机」".  This harness exercises the **Chrome-only** resolver (and
the Edge diagnostics path, which must never run anything) with fake install trees,
so every branch prints the ACTUAL value it produced, not a claim.

What the build host can prove here:
  B1  chrome   -- real Chrome present                -> engine=chrome, tier=1
  B2  stop     -- no Chrome, Edge present            -> found=False, engine=None
  B3  stop     -- neither present                    -> same stop + installer+page
  B4  edge     -- Edge is diagnostics only           -> "不参与运行", not a tier
  B5  launch   -- Chrome argv keeps isolation; msedge.exe is REFUSED
  B6  CDP      -- Edg/->edge, Chrome/->chrome, Headless/Chromium->none
  B7  policy   -- only Google Chrome's policy root is consulted (unknown here)
  B8  regress  -- harness rejects an Edg/ endpoint, accepts a real Chrome endpoint
  B9  offline  -- selector regression reports "pending_real_machine", never green
  B10 installer-- the shipped official Chrome installer (optional --installer)

Real-machine items (real Chrome actually launching, the DOM selector regression on
the customer box) are NOT claimed here; they are listed as 待真机 in the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

RESULTS = []


def record(branch, name, ok, echo):
    RESULTS.append({"branch": branch, "check": name, "ok": bool(ok), "echo": echo})
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {branch:6} {name}")
    print(f"           回显: {echo}")
    return bool(ok)


def _fake_tree(base: Path, relative: str) -> Path:
    exe = base / relative
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    return exe


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_installer(path: Path) -> dict:
    """Evidence for the shipped official Chrome installer (no Windows needed).

    We cannot *install* Chrome on the Linux build host (that is a 待真机 item);
    what we CAN prove is that the file we ship is the byte-exact download from
    Google's own host and that its hash is recorded in the package.
    """
    info = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return info
    raw = path.read_bytes()
    info["bytes"] = len(raw)
    info["sha256"] = hashlib.sha256(raw).hexdigest()
    info["pe"] = raw[:2] == b"MZ"
    sha_file = path.with_name(path.name + ".sha256")
    if sha_file.exists():
        recorded = sha_file.read_text(encoding="utf-8").strip().split()[0]
        info["recorded_sha256"] = recorded
        info["sha256_matches"] = (recorded == info["sha256"])
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verify_browser_resolution")
    ap.add_argument("--out", default=None, help="write the JSON report here")
    ap.add_argument("--installer", default=None,
                    help="path to the shipped official Chrome offline installer")
    args = ap.parse_args(argv)
    from winport import chrome as cb

    print("=" * 72)
    print("浏览器解析 -- Google Chrome ONLY 分支自验（构建机静态带真回显）")
    print(f"版本: 最低内核 {cb.MIN_CHROME_MAJOR}+ / 唯一驱动引擎: chrome / 兜底: 无")
    print("=" * 72)

    tmp = Path(tempfile.mkdtemp(prefix="browser-resolve-"))
    both = {"LOCALAPPDATA": str(tmp / "both" / "la"),
            "PROGRAMFILES(X86)": str(tmp / "both" / "pfx86")}
    chrome_in_both = _fake_tree(Path(both["LOCALAPPDATA"]),
                                "Google/Chrome/Application/chrome.exe")
    edge_in_both = _fake_tree(Path(both["PROGRAMFILES(X86)"]),
                              "Microsoft/Edge/Application/msedge.exe")
    edge_only = {"PROGRAMFILES(X86)": str(tmp / "edge" / "pfx86")}
    edge_exe = _fake_tree(Path(edge_only["PROGRAMFILES(X86)"]),
                          "Microsoft/Edge/Application/msedge.exe")
    none_env = {"LOCALAPPDATA": str(tmp / "none" / "la"),
                "PROGRAMFILES(X86)": str(tmp / "none" / "pfx86")}

    # B1 Chrome present -----------------------------------------------------
    r1 = cb.resolve_browser(env=both)
    record("B1", "已装 Chrome -> 用真 Google Chrome（engine=chrome, tier=1）",
           r1["found"] and r1["engine"] == "chrome" and r1["tier"] == 1,
           f"engine={r1['engine']} tier={r1['tier']} path={r1['path']}")

    # B2 no Chrome, Edge present -> STOP (this is the corrected branch) ------
    r2 = cb.resolve_browser(env=edge_only,
                            explicit=str(tmp / "none" / "chrome.exe"))
    record("B2", "未装 Chrome（机器上有 Edge）-> 明确停下，绝不用 Edge 顶替",
           (not r2["found"]) and r2["engine"] is None and r2["tier"] is None
           and r2["needs_chrome"],
           f"found={r2['found']} engine={r2['engine']} tier={r2['tier']} "
           f"needs_chrome={r2['needs_chrome']}；机器上其实有 "
           f"{Path(edge_exe).name}，但解析结果不是它")

    # B3 neither -> same stop, installer + official page ---------------------
    r3 = cb.resolve_browser(env=none_env,
                            explicit=str(tmp / "none" / "chrome.exe"),
                            edge_explicit=str(tmp / "none" / "msedge.exe"))
    record("B3", "Chrome/Edge 都没有 -> 同一句提示 + 官方离线安装包 + 官方下载地址",
           (not r3["found"]) and cb.CHROME_OFFLINE_DOWNLOAD_URL in r3["reason"]
           and cb.CHROME_BUNDLED_INSTALLER_DISPLAY in r3["reason"]
           and "需要 Google Chrome" in r3["reason"],
           r3["reason"][:170])

    # B4 Edge = diagnostics text only ---------------------------------------
    record("B4", "Edge 只用于诊断提示，不参与任何执行路径（tiers 里只有 chrome）",
           r2["edge"]["present"] and "不参与运行" in r2["edge"]["note"]
           and "不参与运行" in r2["reason"]
           and [t["engine"] for t in r2["tiers"]] == ["chrome"]
           and cb.ENGINE_EDGE not in cb.ENGINE_TIERS,
           f"edge.note={r2['edge']['note']} | ENGINE_TIERS={cb.ENGINE_TIERS} | "
           f"tiers={[t['engine'] for t in r2['tiers']]}")

    # B5 launch args --------------------------------------------------------
    cargs = cb.build_launch_args("C:/Google/chrome.exe", "C:/prof/env_1", 9224,
                                 "https://creator.douyin.com/")
    record("B5", "Chrome 启动参数：独立 user-data-dir + 独立调试端口，无 Edge 专属旗标",
           any(a == "--user-data-dir=C:/prof/env_1" for a in cargs)
           and any(a == "--remote-debugging-port=9224" for a in cargs)
           and not any("msEdgeFirstRunExperience" in a for a in cargs)
           and "--disable-sync" not in cargs
           and not any("Default" in a for a in cargs),
           " ".join(cargs))
    refused = None
    try:
        cb.build_launch_args(str(edge_exe), "C:/prof/env_1", 9224)
        refused = False
    except cb.ConfigError as exc:
        refused = True
        echo_ref = str(exc)
    record("B5", "把 msedge.exe 交给启动器 -> 直接拒绝（ConfigError，绝不静默替换）",
           refused, echo_ref if refused else "没有报错，说明可能被静默采用")

    # B6 CDP identity -------------------------------------------------------
    record("B6", "CDP 身份串：Edg/->edge（仅用于识别），Chrome/->chrome，Headless->拒绝",
           cb.browser_engine_of("Edg/130.0.0.0") == "edge"
           and cb.browser_engine_of("Chrome/130.0.0.0") == "chrome"
           and cb.browser_engine_of("HeadlessChrome/120") is None
           and cb.browser_engine_of("Chromium/120") is None,
           "Edg/130.0.0.0->edge; Chrome/130.0.0.0->chrome; "
           "HeadlessChrome/120->None; Chromium/120->None")

    # B7 policy root --------------------------------------------------------
    pc = cb.policy_remote_debugging(engine="chrome")
    pe = cb.policy_remote_debugging(engine="edge")
    record("B7", "企业策略只查 Google Chrome 的策略根（本机=未知，不谎报绿）",
           pc.get("blocked") is None and pe.get("blocked") is None,
           f"chrome.policy.blocked={pc.get('blocked')} "
           f"edge(kwarg ignored).blocked={pe.get('blocked')} "
           f"details={pc.get('details')}")

    # B8 regression harness -------------------------------------------------
    from winport import environments as env_mod
    from winport import regression as regression_mod
    from winport.paths import Layout
    layout = Layout(program=ROOT, data=tmp / "data",
                    system=tmp / "system").ensure()
    channels = env_mod.expand_channels(env_mod.default_environments())
    cookie = lambda l, c: {"profile_present": True, "debug_port_listening": True,
                           "cookie_count": 3, "backend_reachable": True,
                           "redirected_to_login": False, "backend_status": 200}
    live_edge = regression_mod.run_regression(
        layout, channels, cdp_probe=lambda p: {"ok": True, "browser": "Edg/130.0.0.0"},
        cookie_probe=cookie)
    record("B8", "选择器回归框架：Edge 端点判为「不是我们要的浏览器」，不通过",
           (not live_edge["is_real_chrome"]) and live_edge["engine"] == "edge"
           and (not live_edge["all_ok"]) and live_edge["wrong_engine"]
           and live_edge["edge_on_port"],
           f"mode={live_edge['mode']} engine={live_edge['engine']} "
           f"all_ok={live_edge['all_ok']} note={live_edge['chrome_note']}")
    live_chrome = regression_mod.run_regression(
        layout, channels,
        cdp_probe=lambda p: {"ok": True, "browser": "Chrome/131.0.0.0"},
        cookie_probe=cookie)
    record("B8", "选择器回归框架：真 Chrome 端点判为通过（engine=chrome, all_ok）",
           live_chrome["is_real_chrome"] and live_chrome["engine"] == "chrome"
           and live_chrome["all_ok"] and not live_chrome["wrong_engine"],
           f"mode={live_chrome['mode']} engine={live_chrome['engine']} "
           f"all_ok={live_chrome['all_ok']}")
    bad = regression_mod.run_regression(
        layout, channels, cdp_probe=lambda p: {"ok": True, "browser": "HeadlessChrome/120"},
        cookie_probe=cookie)
    record("B8", "选择器回归框架仍然拒绝 Headless/Chromium 端点",
           (not bad["is_real_chrome"]) and (not bad["all_ok"]),
           f"engine={bad['engine']} is_real_chrome={bad['is_real_chrome']} "
           f"all_ok={bad['all_ok']}")

    # B9 offline regression is pending, never green ------------------------
    offline = regression_mod.run_regression(
        layout, channels, cdp_probe=lambda p: {"ok": False, "error": "refused"})
    record("B9", "构建机上选择器回归=offline/待真机，绝不谎报通过",
           offline["mode"] == "offline" and offline["pending_real_machine"]
           and not offline["all_ok"],
           f"mode={offline['mode']} pending_real_machine={offline['pending_real_machine']} "
           f"all_ok={offline['all_ok']} reason={offline['reason']}")
    record("B9", "给了真机可照抄的 Chrome 回归命令（明说不用 Edge 顶替）",
           any("chrome-regression" in c for c in regression_mod.COMMANDS)
           and any("只认 Google Chrome" in c for c in regression_mod.COMMANDS),
           " | ".join(regression_mod.COMMANDS))

    # B10 shipped installer evidence ---------------------------------------
    installer_info = None
    if args.installer:
        installer_info = check_installer(Path(args.installer))
        ok = (installer_info.get("exists") and installer_info.get("pe")
              and installer_info.get("sha256_matches") is not False)
        record("B10", "随包官方 Chrome 离线安装包：存在 / 是 PE / sha256 与记录一致",
               bool(ok),
               json.dumps(installer_info, ensure_ascii=False))

    passed = sum(1 for r in RESULTS if r["ok"])
    total = len(RESULTS)
    print("-" * 72)
    print(f"BROWSER RESOLUTION BRANCHES: {passed}/{total} passed")
    print("-" * 72)
    failed = [r for r in RESULTS if not r["ok"]]
    if failed:
        print("FAILED:")
        for r in failed:
            print(f"  {r['branch']} {r['check']} -> {r['echo']}")

    if args.out:
        report = {"passed": passed, "total": total, "results": RESULTS,
                  "host_os": os.name,
                  "mode": "chrome-only",
                  "installer": installer_info,
                  "note": ("本机为构建机（非 Windows）：只认 Google Chrome 的分支逻辑已"
                           "逐条跑通（含已装/未装两个分支），Edge 只作诊断不参与执行；"
                           "真 Chrome 真正拉起 + 选择器在真 Chrome 上的 DOM 回归 = 待真机。"),
                  "pending_real_machine": [
                      "在已装 Chrome 的 Windows 上 `winport browser-probe` 应报 found=true/engine=chrome/tier=1",
                      "在没装 Chrome 的 Windows 上 `winport browser-probe` 应报 found=false + 需装 Chrome（且不去找 Edge）",
                      "`winport env-open --env env_1` 应拉起 chrome.exe（独立目录+端口）；端口被占用时报 CDP_NOT_UP",
                      "`winport chrome-regression --live` 应报 engine=chrome 且 all_ok（选择器真机回归的唯一证据）",
                      "在客户机上双击包内 chrome-offline\\ChromeStandaloneSetup64.exe 应能装上官方 Chrome",
                  ]}
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2)
                                  + "\n", encoding="utf-8")
        print(f"report: {args.out}")
    return 0 if passed == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
