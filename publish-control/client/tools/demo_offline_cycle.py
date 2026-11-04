"""End-to-end offline demo: bucket -> downlink -> bind -> ledger -> report.

This is the proof that the pipeline really runs (no browser, no network).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tools"))

import make_fixture  # noqa: E402
from winport import report as report_mod  # noqa: E402
from winport.downlink import Downlink, FileSystemSource  # noqa: E402
from winport.paths import Layout  # noqa: E402
from winport.settings import load_settings  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="demo_offline_cycle")
    parser.add_argument("--workdir", help="keep artefacts here (default: temp)")
    args = parser.parse_args(argv)

    tmp = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="winport-demo-"))
    bucket = tmp / "bucket"
    data = tmp / "data"
    tmp.mkdir(parents=True, exist_ok=True)
    manifest = make_fixture.build_bucket(bucket, batch_id="B20261015-01")
    layout = Layout(program=ROOT, data=data).ensure()
    settings = load_settings(layout.settings_file)
    source = FileSystemSource(bucket)
    downlink = Downlink(layout, source, settings, machine_id="demo-machine",
                        free_bytes=lambda p: 10 ** 12,
                        customer_id="newme-001")

    print("[1] folder_key / 素材就绪，开始第一轮取件")
    first = downlink.run_once()
    print("    round1:", json.dumps(first, ensure_ascii=False))

    folder = layout.inbox / "B20261015-01" / manifest["batch"]["folder_key"]
    landed = sorted(p.name for p in folder.iterdir() if not p.name.startswith("."))
    print(f"    landed files: {landed}")
    print("    .folder.json:",
          json.dumps(json.loads((folder / ".folder.json").read_text(encoding="utf-8"))
                     if (folder / ".folder.json").exists() else None,
                     ensure_ascii=False))

    print("[2] 第二轮：seq 未变（幂等：整轮跳过，不重复下载）")
    second = downlink.run_once()
    print("    round2:", json.dumps(second, ensure_ascii=False))

    print("[3] 第三轮：家长 seq+1 但内容不变（只拉缺的 -> 应全部 SKIP）")
    make_fixture.build_bucket(bucket, manifest_seq=20261015002)
    third = downlink.run_once()
    print("    round3:", json.dumps({"downloaded": third["downloaded"],
                                     "skipped": third["skipped"],
                                     "failed": third["failed"]},
                                    ensure_ascii=False))

    print("[4] 第四轮：删掉一条成片 + seq+1（应只补拉 1 条）")
    victim = folder / manifest["pieces"][0]["file_name"]
    victim.unlink()
    make_fixture.build_bucket(bucket, manifest_seq=20261015003)
    fourth = downlink.run_once()
    print("    round4:", json.dumps({"downloaded": fourth["downloaded"],
                                     "skipped": fourth["skipped"],
                                     "failed": fourth["failed"],
                                     "status": fourth["folders"][0]["status"]},
                                    ensure_ascii=False))

    print("[5] 生成日报（xlsx + md）")
    export = tmp / "export.xlsx"
    make_fixture.write_export_xlsx(export)
    from winport.collect_douyin import collect_offline
    collection = collect_offline(layout, export)
    rep = report_mod.write_report(layout, collection={
        "row_count": collection["normalized"]["row_count"],
        "column_count": collection["normalized"]["column_count"],
        "header": collection["normalized"]["header"]})
    print("    report md  :", rep["md"])
    print("    report xlsx:", rep["xlsx"])

    import zipfile
    with zipfile.ZipFile(rep["xlsx"]) as zf:
        print("    xlsx parts :", len(zf.namelist()), "entries; valid:",
              zf.testzip() is None)
    print("    ledger     :", layout.downlink_ledger)
    print("DEMO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
