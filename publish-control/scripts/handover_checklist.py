#!/usr/bin/env python3
"""Offline checklist and byte/JSON verification only. No network, copy, token or ledger mutation."""
import argparse
import hashlib
import json
from pathlib import Path

REQUIRED = ('run/stage2-ledger.json', 'run/agentpoll-state.json', 'run/publish_holds.json')
STEPS = (
    'inventory_commands_remote_ops_batches', 'dispatch_paused', 'old_device_isolated',
    'no_inflight_verified', 'consistent_backup_taken', 'material_identity_mapping_checked',
    'new_device_integrity_identity_license_checked', 'new_device_dry_run_only',
    'drafts_rebuilt_and_reconfirmed', 'new_epoch_and_new_credentials_only',
    'old_credentials_revoked', 'human_cutover_approval',
)

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def safe(root, relative):
    rel=Path(relative)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError('unsafe manifest path')
    p=root / rel
    if any(q.is_symlink() for q in [p, *p.parents] if q != root.parent):
        raise ValueError('symlink not allowed')
    if not p.resolve().is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('missing regular file: '+relative)
    return p

def compare(source, target, manifest):
    files=manifest.get('files', [])
    if not isinstance(files,list) or len(files)!=len(set(files)) or not set(REQUIRED)<=set(files):
        raise ValueError('manifest must include ledgers and holds exactly once')
    result=[]
    for name in files:
        a,b=safe(source,name),safe(target,name)
        sha_a,sha_b=digest(a),digest(b)
        if sha_a != sha_b: raise ValueError('byte mismatch: '+name)
        if name.endswith('.json') and json.loads(a.read_text()) != json.loads(b.read_text()):
            raise ValueError('semantic mismatch: '+name)
        result.append({'path':name,'bytes':a.stat().st_size,'sha256':sha_a,'unchanged':True})
    return result

def check_inventory(inventory, customer_id):
    for kind in ('commands','remote_ops','batches'):
        section=inventory.get(kind, {})
        if section.get('complete') is not True or not isinstance(section.get('rows'),list):
            raise ValueError('complete inventory required: '+kind)
        for row in section['rows']:
            if row.get('customer_id') != customer_id:
                raise ValueError('foreign customer in '+kind)
            rows=row.get('items',[]) if kind=='batches' else [row]
            for entry in rows:
                if entry.get('status') not in ('done','failed','cancelled','completed','published','skipped'):
                    raise ValueError('unresolved task requires manual reconciliation: '+kind)
    # No inference from an empty excerpt; explicit complete inventory and human evidence are both required.

def verify(source,target,record):
    cid=record.get('customer_id')
    if not isinstance(cid,str) or not cid: raise ValueError('customer_id required')
    check_inventory(record.get('inventory',{}),cid)
    steps=record.get('steps',{})
    for step in STEPS:
        value=steps.get(step,{})
        if value.get('checked') is not True or not value.get('evidence') or not value.get('operator'):
            raise ValueError('missing external evidence: '+step)
    if (not record.get('old_device_id') or not record.get('new_device_id') or
            record['old_device_id']==record['new_device_id'] or
            type(record.get('old_epoch')) is not int or type(record.get('new_epoch')) is not int or
            record['new_epoch'] <= record['old_epoch']):
        raise ValueError('device/epoch transition invalid')
    return {'customer_id':cid,'files':compare(source,target,record),
            'verification':'offline evidence consistency only; not approval or execution'}

if __name__=='__main__':
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='mode',required=True)
    sub.add_parser('template')
    v=sub.add_parser('verify'); v.add_argument('--source',type=Path,required=True);v.add_argument('--target',type=Path,required=True);v.add_argument('--record',type=Path,required=True)
    a=ap.parse_args()
    if a.mode=='template':
        result={'customer_id':'','old_device_id':'','new_device_id':'','old_epoch':0,'new_epoch':1,
                'files':list(REQUIRED),'inventory':{k:{'complete':False,'rows':[]} for k in ('commands','remote_ops','batches')},
                'steps':{s:{'checked':False,'operator':'','evidence':''} for s in STEPS}}
    else:
        try: result=verify(a.source,a.target,json.loads(a.record.read_text()))
        except (ValueError,OSError,KeyError) as e: ap.exit(3,'MANUAL_REVIEW_REQUIRED: HANDOVER:'+str(e)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
