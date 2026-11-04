"""Inventory every first-party text/code file and compile Python in memory.

Delay inventory includes variable expressions and embedded JavaScript; this is
an audit aid, not a claim of semantic completeness or zero fixed waits.
"""
import ast
import hashlib
import json
import re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
files=[]; waits=[]; failures=[]
for p in sorted(root.rglob('*')):
    if not p.is_file() or any(x in p.parts for x in ('__pycache__','.git')):continue
    rel=p.relative_to(root).as_posix()
    if rel.startswith('evidence/') or p.name in ('MANIFEST.json','SHA256SUMS.txt'):continue
    raw=p.read_bytes(); files.append({'file':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    if p.suffix=='.py':
        try:
            source=raw.decode('utf-8-sig'); tree=ast.parse(source,filename=rel)
            compile(tree,rel,'exec')
            for n in ast.walk(tree):
                if isinstance(n,ast.Call):
                    call=ast.unparse(n.func)
                    if call.endswith(('sleep','wait_for_timeout')):
                        waits.append({'file':rel,'line':n.lineno,'call':ast.unparse(n)})
            for m in re.finditer(r'(setTimeout|setInterval)\s*\([^\n]+',source):
                waits.append({'file':rel,'line':source.count('\n',0,m.start())+1,'call':m.group(0)})
        except (SyntaxError,UnicodeError) as exc:failures.append({'file':rel,'error':str(exc)})
print(json.dumps({'files':files,'delay_inventory':waits,'compile_failures':failures,
                  'scope':'first-party source; no Windows or platform execution'},ensure_ascii=False,indent=2))
raise SystemExit(bool(failures))
