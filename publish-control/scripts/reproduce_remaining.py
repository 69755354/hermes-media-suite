#!/usr/bin/env python3
"""Reproduce isolated patches/tests. Does not apply patches to production paths."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

project=Path(__file__).resolve().parents[1]
ev=project/'fix_evidence_remaining'
manifest=json.loads((ev/'manifest.json').read_text())
tmp=Path('/tmp/publish-remaining')
for label,src in [('bot',project.parent/'feishu_publish_bot/bot.py'),('control',project/'server.py')]:
    expected=manifest['baseline_sha256'][str(src)]
    if hashlib.sha256(src.read_bytes()).hexdigest()!=expected:
        raise SystemExit('baseline changed; independent rebase/review required: '+str(src))
    dest=tmp/label;dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dest/src.name)
    subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(project/f'remaining_{label}.patch')],cwd=dest,check=True)
    actual=hashlib.sha256((dest/src.name).read_bytes()).hexdigest()
    if actual != manifest['candidate_sha256'][f'{label}/{src.name}']:
        raise SystemExit('candidate mismatch')
shutil.copy2(project.parent/'feishu_publish_bot/receipt_issue.py',tmp/'bot/receipt_issue.py')
for folder in ('scripts','migrations'):
    (tmp/folder).mkdir(exist_ok=True)
for name in ('verify_device_binding.py','handover_checklist.py'):
    shutil.copy2(project/'scripts'/name,tmp/'scripts'/name)
shutil.copy2(project/'migrations/20261028_device_binding.sql',tmp/'migrations/20261028_device_binding.sql')
shutil.copytree(ev/'tests',tmp/'tests',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copy2(ev/'client_scan_reference.py',tmp/'client_scan_reference.py')
env=dict(os.environ,PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
result=subprocess.run([sys.executable,'-m','pytest','-q','tests'],cwd=tmp,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
print(result.stdout,end='')
(tmp/'pytest-reproduced.txt').write_text(result.stdout)
raise SystemExit(result.returncode)
