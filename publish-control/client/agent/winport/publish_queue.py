"""Persistent, opt-in publisher queue. A running job is never retried after crash.

Each job has its own plan/preview/receipt. Only this queue's individually bound
Feishu card authorizes publishing; cadence batch reminders are NOT authorization.
"""
from datetime import datetime, timezone
from pathlib import Path
import contextlib
import io
import json
import re
from types import SimpleNamespace

from .errors import GateRed
from .jsonio import read_json, write_json
from .lock import FileLock


def enqueue(layout, plan, preview, receipt):
    from .approval import require_receipt
    from .license import require_receipt_public_key
    from .feishu_approval import approval_id_for
    from .content_binding import validate_local_content
    from .hashing import sha256_bytes
    require_receipt(receipt, plan, require_receipt_public_key(), operation_mode='approved_publish')
    validate_local_content(plan)
    if not preview.get('ok'):
        raise GateRed('dry-run failed')
    job_id = sha256_bytes((approval_id_for(preview) + '|' + receipt['receipt_id']).encode())[:24]
    path = layout.run / 'publish-queue' / (job_id + '.json')
    with FileLock(layout.run / 'publish-queue.lock'):
        if path.exists():
            raise GateRed('job already exists; refusing to overwrite')
        write_json(path, {'schema': 1, 'job_id': job_id, 'status': 'queued',
                         'plan': plan, 'preview': preview, 'receipt': receipt})
    return path


def _time(value):
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise GateRed('queue schedule must include timezone')
    return dt


def run_once(layout, settings, *, now=None, publisher=None):
    if not (settings.get('publish_queue') or {}).get('enabled'):
        return {'enabled': False, 'jobs': []}
    now = now or datetime.now(timezone.utc)
    lock = FileLock(layout.run / 'publish-queue.lock')
    if not lock.acquire():
        return {'enabled': True, 'busy': True, 'jobs': []}
    results = []
    try:
        for path in sorted((layout.run / 'publish-queue').glob('*.json')):
            job = None
            try:
                job = read_json(path)
                if not isinstance(job, dict) or not re.fullmatch(r'[0-9a-f]{24}', job.get('job_id', '')):
                    raise GateRed('invalid queue job')
                if job['status'] == 'running':
                    job.update(status='needs_reconcile', reason='上次进程在执行中退出；禁止自动重试')
                    write_json(path, job)
                if job['status'] not in ('queued', 'pending'):
                    continue
                plan, preview, receipt = job['plan'], job['preview'], job['receipt']
                due = _time(plan['schedule_at'])
                seconds = (due - now).total_seconds()
                if seconds > 600:
                    continue
                if seconds < -600:
                    # Catch-up: the machine was asleep/off (or the daemon was
                    # not running) past the 10-minute grace.  Never publish a
                    # stale point inside a wrong window -- move the job to the
                    # next legal window, rebuild its preview and let the normal
                    # approval flow ask the owner again.
                    auto = (settings.get('publish_queue') or {}).get(
                        'auto_reschedule', True)
                    if auto:
                        from .schedule import next_slot
                        from .dryrun import build_preview
                        old_at = plan.get('schedule_at')
                        new_at = next_slot(now, settings=settings)
                        plan['schedule_at'] = new_at.isoformat()
                        preview = build_preview(plan, settings=settings)
                        job.update(plan=plan, preview=preview, approval=None,
                                   status='queued', rescheduled_from=old_at,
                                   rescheduled_at=now.isoformat())
                        write_json(path, job)
                        results.append({'job': job.get('job_id'),
                                        'status': 'rescheduled',
                                        'from': old_at,
                                        'to': plan['schedule_at'],
                                        'problems': preview.get('problems')})
                        continue
                    raise GateRed('计划已逾期超过 10 分钟，须重新排期和确认')
                from .feishu_approval import submit_pending, refresh, gate
                record = job.get('approval')
                if not record:
                    record = submit_pending(layout, plan, preview, settings, now=now)
                record = refresh(layout, record, settings, now=now)
                job.update(approval=record, status='pending')
                write_json(path, job)
                verdict = gate(record, preview, now=now)
                if record.get('status') == 'pending' or (verdict['ok'] and seconds > 0):
                    continue
                if not verdict['ok']:
                    raise GateRed(verdict['reason'])
                # Persist the full immutable inputs before entering the driver.
                work = layout.run / 'publish-jobs' / job['job_id']
                for name, value in (('plan', plan), ('preview', preview), ('receipt', receipt)):
                    write_json(work / (name + '.json'), value)
                args = SimpleNamespace(data=str(layout.data), program=str(layout.program),
                    plan=str(work/'plan.json'), preview=str(work/'preview.json'),
                    receipt=str(work/'receipt.json'), mode='approved_publish',
                    approval_id=record['approval_id'], confirm_token=preview['confirm_token'],
                    canary_armed=True, allow_submit=True, license=None)
                job.update(status='running', started_at=now.isoformat())
                write_json(path, job)
                if publisher is None:
                    from .cli import cmd_publish
                    publish = cmd_publish
                else:
                    publish = publisher
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    rc = publish(args)
                result_text = output.getvalue()
                (work/'result.txt').write_text(result_text, encoding='utf-8')
                if rc != 0:
                    raise GateRed(f'publish returned {rc}; inspect ledger before retry')
                published = {}
                try:
                    parsed = json.loads(result_text)
                    if isinstance(parsed, dict):
                        published = parsed
                except ValueError:
                    published = {}
                job.update(status='published',
                           finished_at=datetime.now(timezone.utc).isoformat(),
                           item_id=(published.get('platform_work_id')
                                    or published.get('item_id') or None),
                           published_at=(published.get('published_at')
                                         or None))
                write_json(path, job)
                results.append({'job_id': job['job_id'], 'status': job['status']})
            except Exception as exc:
                if isinstance(job, dict):
                    job.update(status='needs_reconcile' if job.get('status') == 'running' else 'blocked',
                               reason=f'{type(exc).__name__}: {exc}')
                    write_json(path, job)
                results.append({'file': path.name, 'status': 'blocked', 'reason': str(exc)})
    finally:
        lock.release()
    return {'enabled': True, 'jobs': results}
