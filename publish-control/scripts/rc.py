#!/usr/bin/env python3
"""控制面远程助手：rc.py ping|ls <path>|read <path>|exec <cmd...>"""
import json,sys,time,urllib.request,os
ROOT='/home/ubuntu/workflow/projects/publish_control'
def env(k):
    for line in open(os.path.join(ROOT,'.env'),encoding='utf-8'):
        if line.startswith(k+'='): return line.split('=',1)[1].strip()
TOK=env('CONTROL_ADMIN_TOKEN')
CUST=os.environ.get('PUBLISH_CUSTOMER_ID','')
def call(op,args,timeout=120):
    body=json.dumps({"customer_id":CUST,"op":op,"args":args}).encode()
    r=urllib.request.Request('http://127.0.0.1:18977/api/remote/exec',data=body,
        headers={'Content-Type':'application/json','Authorization':'Bearer '+TOK})
    oid=json.load(urllib.request.urlopen(r,timeout=15))['id']
    t0=time.time()
    while time.time()-t0<timeout:
        import sqlite3
        c=sqlite3.connect(os.path.join(ROOT,'control.db'))
        row=c.execute('select status,result from remote_ops where id=?',(oid,)).fetchone()
        if row and row[0] in ('done','failed'):
            try: res=json.loads(row[1] or '{}')
            except Exception: res={'raw':row[1]}
            return {'status':row[0],'id':oid,'result':res}
        time.sleep(1.5)
    return {'status':'timeout','id':oid}
if __name__=='__main__':
    op=sys.argv[1]
    if op=='ping': res=call('ping',{})
    elif op=='ls': res=call('ls',{'path':sys.argv[2]})
    elif op=='read': res=call('read',{'path':sys.argv[2]})
    elif op=='exec': res=call('exec',{'cmd':sys.argv[2:],'timeout':90})
    else: raise SystemExit('op?')
    print(json.dumps(res,ensure_ascii=False)[:3000])
