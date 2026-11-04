"""Build an offline 'bucket' fixture + a 13-column export fixture.

Used by the self-test and the offline demo so the whole fetch->bind->report
chain is provable without network or a real Windows machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

VIDEO_EXT = "mp4"

# The export column names are NOT enumerated in source/.  The fixture uses a
# clearly-marked placeholder header of the right width so the "13 columns"
# logic is exercised; the real header is captured to evidence/ on the real
# machine (see VERIFY.md, item "export columns").
EXPORT_HEADER = [f"col{i}" for i in range(1, 14)]


def _bytes_for(seed: str, size: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(f"{seed}:{counter}".encode()).digest()
        counter += 1
    return bytes(out[:size])


def write_media(folder: Path, file_name: str, *, size=4096, seed=None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / file_name
    data = _bytes_for(seed or file_name, size)
    path.write_bytes(data)
    return path


def hashes(path: Path) -> dict:
    data = path.read_bytes()
    return {"md5": hashlib.md5(data).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def build_bucket(bucket_root: Path, *, customer_id="newme-001",
                 batch_id="B20261015-01", nickname="示例账号", task_type="种草",
                 pieces=None, manifest_seq=20261015001, paused=False) -> dict:
    bucket_root = Path(bucket_root)
    pieces = pieces or [
        {"piece_no": 1, "name": "第12集-上", "title": "上集标题", "copy_body": "上集文案"},
        {"piece_no": 2, "name": "第12集-下", "title": "下集标题", "copy_body": "下集文案"},
    ]
    folder_key = f"{batch_id}_{nickname}_{task_type}"
    media_dir = bucket_root / "customers" / customer_id / "media"
    out_pieces = []
    for piece in pieces:
        file_name = f"{piece['piece_no']:02d}_{piece['name']}.{VIDEO_EXT}"
        local = bucket_root / "_staging" / batch_id / file_name
        write_media(local.parent, file_name, size=piece.get("size", 4096),
                    seed=f"{batch_id}-{file_name}")
        info = hashes(local)
        key = (f"customers/{customer_id}/media/{info['sha256'][:2]}/"
               f"{info['sha256']}/{file_name}")
        target = bucket_root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(local.read_bytes())
        out_pieces.append({
            "piece_id": f"{batch_id}-{piece['piece_no']:02d}",
            "piece_no": piece["piece_no"],
            "name": piece["name"],
            "title": piece.get("title", piece["name"]),
            "copy_body": piece.get("copy_body", ""),
            "topics": piece.get("topics", ["#示例话题"]),
            "duration_sec": piece.get("duration_sec", 43.2),
            "file_name": file_name,
            "media_key": key,
            "media_bytes": info["bytes"],
            "md5": info["md5"],
            "sha256": info["sha256"],
            "covers": {"vertical": None, "horizontal": None},
            "poi": None,
        })
    manifest = {
        "schema_version": "1.0",
        "manifest_seq": manifest_seq,
        "generated_at": "2026-10-15T09:00:00+08:00",
        "customer_id": customer_id,
        "batch": {
            "batch_id": batch_id,
            "batch_name": "示例项目 1015 第 1 批",
            "folder_key": folder_key,
            "account_id": "douyin-pilot-001",
            "account_nickname": nickname,
            "platform": "douyin",
            "task_type": task_type,
            "star_task_name": "示例任务-260916-APP种草-1-示例需求方 星广 按效果结算",
            "piece_count": len(out_pieces),
            "paused": paused,
            "expires_at": "2026-10-22T00:00:00+08:00",
        },
        "pieces": out_pieces,
    }
    manifests = bucket_root / "customers" / customer_id / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / f"batch-{batch_id}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (manifests / "latest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def write_export_xlsx(path: Path, rows=None, header=None) -> Path:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
    from winport.minimal_xlsx import write_xlsx
    header = header or EXPORT_HEADER
    rows = rows or [header,
                    ["作品1", "2026-10-15", "1000", "10", "5", "3", "0.5",
                     "1", "2", "3", "4", "5", "6"],
                    ["作品2", "2026-10-15", "2000", "20", "6", "4", "0.6",
                     "1", "2", "3", "4", "5", "6"]]
    write_xlsx(path, rows, sheet_name="作品列表")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="make_fixture")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--export")
    args = parser.parse_args(argv)
    manifest = build_bucket(Path(args.bucket))
    print(f"bucket fixture built: {manifest['batch']['batch_id']} "
          f"folder_key={manifest['batch']['folder_key']}")
    if args.export:
        write_export_xlsx(Path(args.export))
        print(f"export fixture built: {args.export}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
