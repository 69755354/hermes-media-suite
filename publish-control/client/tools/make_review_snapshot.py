#!/usr/bin/env python3
"""Create a new immutable-by-convention source snapshot and bind an existing zip.

Never overwrite a previous snapshot. Snapshot manifests cover its exact files;
VERSION_MAP additionally records the package hash and source->package comparisons.
"""
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bundle


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--package', type=Path, required=True)
    args=ap.parse_args(argv)
    root=args.root.resolve(); out=args.out.resolve(); package=args.package.resolve()
    if out.exists() or out == root or root in out.parents or out in root.parents:
        raise SystemExit('refusing existing/overlapping snapshot destination')
    version=(root/'VERSION').read_text().strip()
    name='manju-publish-assistant-'+version+'-win64'
    mismatches=[]; compared=0
    with zipfile.ZipFile(package) as z:
        for path in build_bundle.iter_files(root):
            rel=path.relative_to(root).as_posix()
            if path.is_symlink(): raise SystemExit('symlink refused: '+rel)
            try: payload=z.read(name+'/'+rel)
            except KeyError: mismatches.append(rel); continue
            if hashlib.sha256(payload).hexdigest()!=build_bundle.sha256_of(path):
                mismatches.append(rel)
            compared+=1
    if mismatches: raise SystemExit('source/package mismatches: '+str(mismatches))
    shutil.copytree(root,out,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','.git'))
    binding={'version':version,'package':package.name,'package_sha256':build_bundle.sha256_of(package),
             'source_files_compared':compared,'source_package_mismatches':mismatches}
    (out/'PACKAGE_BINDING.json').write_text(json.dumps(binding,indent=2)+'\n')
    (out/'VERSION_MAP.md').write_text(
        '# VERSION_MAP\n\n'+f'Version: {version}\n\nPackage: {package.name}\n\n'
        +f'Package SHA256: {binding["package_sha256"]}\n\n'
        +f'{compared} source files were compared with the zip before this review binding was written; '
        +'PACKAGE_BINDING.json is intentionally replaced here, every other file stays byte-identical.\n\n'
        +'MANIFEST.json and SHA256SUMS.txt cover this snapshot, not real-account acceptance.\n')
    build_bundle.build(out,version=version)
    result=build_bundle.verify(out)
    print(json.dumps({'binding':binding,'snapshot':str(out),'verify':result},indent=2))
    return 0 if result['ok'] else 2
if __name__=='__main__': raise SystemExit(main())
