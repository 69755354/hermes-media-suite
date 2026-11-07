"""Attempt-scoped create_v2 receipts, using the 2026-10-18 supplied live schema.

Empty or ID-less HTTP 200 bodies remain pending, never success. Only an exact,
completed response belonging to this creation/video pair can provide the
primary ID. If the platform returns no ID, a caller-approved page fallback may
bind one only when it appeared after submit and matches this attempt's
material fingerprint. This observer never sends POSTs.
"""
from __future__ import annotations
import base64
import hashlib
import json
import re
import time
import uuid
from urllib.parse import urlsplit

ENDPOINT = re.compile(r'^/web/api/media/aweme/create_v2/$')

def is_upload_placeholder(value):
    """The upload endpoint may return no ID; our local fallback is not an ID."""
    return isinstance(value, str) and value.startswith('upload:')

def parse_work_id(body):
    if not isinstance(body, dict) or type(body.get('status_code')) is not int or body['status_code'] != 0:
        return None
    item_id = body.get('item_id')
    return item_id if isinstance(item_id, str) and re.fullmatch(r'[0-9]{19}', item_id) else None

def parse_submission(raw):
    payload = json.loads(raw)
    common = payload['item']['common']
    creation, video = common['creation_id'], common['video_id']
    if any(not isinstance(v, str) or not v or v != v.strip() for v in (creation, video)):
        raise ValueError('invalid item.common creation_id/video_id')
    return creation, video

class PublishReceipt:
    def __init__(self,page,origin,attempt_id,account_id,fingerprint,resource_ids=(),bind_submission=None,
                 page_work_probe=None,baseline_work_ids=()):
        self.page=page; self.origin=urlsplit(origin)
        self.attempt_id=attempt_id; self.account_id=account_id; self.fingerprint=fingerprint
        # ``upload:<request id>`` only proves that this process sent the upload;
        # it is not the platform video ID.  Comparing it with create_v2's real
        # item.common.video_id made every successful upload fail when the upload
        # response body was empty.
        self.resource_ids=[str(v) for v in resource_ids
                           if isinstance(v,str) and v and not is_upload_placeholder(v)]
        self.bind_submission=bind_submission; self.page_work_probe=page_work_probe
        self.baseline_work_ids={str(v) for v in baseline_work_ids if v}
        self.creation_id=None; self.video_id=None
        self.requests={}; self.responses=[]; self.pending=[]; self.fault=None; self.started_at=time.time()
        self.active=True; self.handlers=[]; self.finished=set()
        self.page_failures=[]
        self.page_proof=None; self.page_fallback_attempted=0.0; self.page_fallback_error=None
        self._allow_page_fallback=bool(page_work_probe)
        self._listen(page,'request',self.on_request)
        self._listen(page,'response',self.on_response)
        self._listen(page,'requestfailed',self.on_failed)
        self._listen(page,'requestfinished',lambda request: self.finished.add(request))
        self._listen(page,'close',lambda *_: self.fail('PAGE_CLOSED'))
        self._listen(page,'crash',lambda *_: self.fail('PAGE_CRASHED'))
        browser=page.context.browser
        if browser: self._listen(browser,'disconnected',lambda *_: self.fail('BROWSER_DISCONNECTED'))
        self.cdp=None; self.network={}; self.network_finished=set()
        try:
            self.cdp=page.context.new_cdp_session(page)
            self.cdp.send('Page.enable')
            self.frame_id=self.cdp.send('Page.getFrameTree')['frameTree']['frame']['id']
            self._listen(self.cdp,'Network.requestWillBeSent',self.on_network_request)
            self._listen(self.cdp,'Network.responseReceived',self.on_network_response)
            self._listen(self.cdp,'Network.loadingFinished',lambda e:self.network_finished.add(e['requestId']))
            self._listen(self.cdp,'Network.loadingFailed',lambda e:self.fail('SUBMIT_BODY_FAILED') if e['requestId'] in self.network else None)
            self.cdp.send('Network.enable',{'maxTotalBufferSize':8*1024*1024,
                'maxResourceBufferSize':2*1024*1024,'enableDurableMessages':True})
        except Exception as exc: self.fail('RESPONSE_CAPTURE_UNAVAILABLE:'+str(exc))
    def matches_url(self,url):
        parsed=urlsplit(url)
        return (parsed.scheme==self.origin.scheme and parsed.netloc==self.origin.netloc and
                not parsed.username and bool(ENDPOINT.fullmatch(parsed.path)))
    def on_network_request(self,event):
        request=event['request']
        if not self.active or request.get('method')!='POST' or not self.matches_url(request.get('url','')): return
        try:
            if event.get('frameId')!=self.frame_id or event.get('redirectResponse') or event['requestId'] in self.network:
                raise ValueError('redirect/frame/request ID mismatch')
            raw=request.get('postData')
            if raw is None:
                raw=self.cdp.send('Network.getRequestPostData',{'requestId':event['requestId']})['postData']
            creation,video=parse_submission(raw)
            self.network[event['requestId']]={'url':request['url'],'method':request['method'],
                'body_sha256':hashlib.sha256(raw.encode()).hexdigest(), 'creation_id':creation,'video_id':video}
        except Exception as exc: self.fail('SUBMIT_NETWORK_BINDING_FAILED:'+str(exc))
    def on_network_response(self,event):
        entry=self.network.get(event['requestId'])
        if entry is not None:
            response=event['response']
            entry.update(status=response['status'],response_url=response['url'])
    def _listen(self,emitter,event,callback):
        emitter.on(event,callback); self.handlers.append((emitter,event,callback))
    def observe_page_failure(self, reason):
        # DOM diagnostics cannot poison a completed OR a still-pending receipt.
        if self.active and reason not in self.page_failures:
            self.page_failures.append(str(reason))
    def fail(self,reason):
        if str(reason).startswith('VERIFICATION_FAILURE:'):
            self.observe_page_failure(reason)
            return
        if self.active and self.fault is None: self.fault=str(reason)
    def matches(self,request):
        return request.method=='POST' and self.matches_url(request.url) and request.frame==self.page.main_frame
    def on_request(self,request):
        if not self.active: return
        try:
            if self.matches(request):
                raw=request.post_data
                creation,video=parse_submission(raw)
                # A real upload-response resource ID is authoritative.  When
                # the upload body carried no ID, the create request is the only
                # authoritative source for this attempt's video_id.
                if self.resource_ids and self.resource_ids != [video]:
                    raise ValueError('video_id differs from this upload')
                if self.creation_id is None:
                    if not callable(self.bind_submission): raise ValueError('durable submission binding unavailable')
                    self.bind_submission(creation,video)
                    self.creation_id,self.video_id=creation,video
                elif (creation,video)!=(self.creation_id,self.video_id):
                    raise ValueError('foreign creation_id/video_id')
                self.requests[request]={'url':request.url,'method':request.method,
                    'started_at':time.time(),'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                    'creation_id':creation,'video_id':video,'sequence':len(self.requests),
                    'binding_source':'upload_response' if self.resource_ids else 'create_request'}
        except Exception as exc: self.fail('REQUEST_BINDING_FAILED:'+str(exc))
    def on_failed(self,request):
        if request in self.requests: self.fail('SUBMIT_REQUEST_FAILED')
    def on_response(self,response):
        if not self.active or response.request not in self.requests: return
        try:
            if any(r is response.request for _,_,r in self.pending): raise ValueError('duplicate response object')
            entry=dict(self.requests[response.request],status=response.status,
                       received_at=time.time(),attempt_id=self.attempt_id,
                       account_id=self.account_id,fingerprint=self.fingerprint,
                       resource_ids=self.resource_ids)
            self.responses.append(entry)
            if response.status!=200:
                self.fail('SUBMIT_HTTP_'+str(response.status)); return
            self.pending.append((response,entry,response.request))
        except Exception as exc: self.fail('RESPONSE_QUERY_FAILED:'+str(exc))
    def proof(self, allow_page_fallback=None):
        if allow_page_fallback is None:
            allow_page_fallback=bool(getattr(self,'_allow_page_fallback',False))
        if self.fault: return None
        try:
            # Both event streams are ordered by request start. Bind each ordinal
            # by its full POST hash, creation/video pair, URL, method and status.
            # Body bytes come ONLY from that CDP requestId, including after navigation.
            network_items=list(self.network.items())
            for response,entry,request in list(self.pending):
                seq=entry['sequence']
                if request not in self.finished or seq>=len(network_items): continue
                request_id,network=network_items[seq]
                if request_id not in self.network_finished: continue
                if (any(network.get(k)!=entry[k] for k in ('url','method','status','body_sha256','creation_id','video_id')) or
                    network.get('response_url')!=entry['url']):
                    raise ValueError('body response binding mismatch')
                body=self.cdp.send('Network.getResponseBody',{'requestId':request_id})
                raw=base64.b64decode(body['body'],validate=True) if body.get('base64Encoded') else body['body'].encode('utf-8')
                entry.update(network_request_id=request_id,body_transport='cdp_durable_response_body',
                             response_sha256=hashlib.sha256(raw).hexdigest())
                if raw==b'':
                    entry['result']='PENDING_EMPTY_BODY'
                else:
                    payload=json.loads(raw); work_id=parse_work_id(payload)
                    if work_id:
                        if work_id in self.baseline_work_ids:
                            raise ValueError('response reused a pre-submit work ID')
                        entry.update(work_id=work_id,item_id=work_id,status_code=0,result='SUCCESS')
                    elif (isinstance(payload,dict) and type(payload.get('status_code')) is int
                          and payload.get('status_code')==0):
                        entry['result']='PENDING_MISSING_ID'
                    else:
                        raise ValueError('requires status_code=0 and top-level ASCII item_id of length 19')
                self.pending.remove((response,entry,request))
        except Exception as exc:
            self.fail('RESPONSE_QUERY_FAILED:'+str(exc)); return None
        if (self.fault or self.pending or len(self.requests)!=len(self.responses) or
                len(self.requests)!=len(self.network) or not set(self.requests).issubset(self.finished)):
            return None
        successes=[r for r in self.responses if r.get('result')=='SUCCESS']
        if len(successes)>1:
            self.fail('MULTIPLE_SUCCESS_RECEIPTS'); return None
        if successes:
            return dict(successes[0],source='playwright_response',ok=True)
        if self.page_proof is not None:
            return self.page_proof
        idless=[r for r in self.responses if r.get('result') in
                ('PENDING_EMPTY_BODY','PENDING_MISSING_ID')]
        if idless and allow_page_fallback:
            return self._page_work_proof(idless)
        return None
    def success_without_id(self):
        """A completed, bound create_v2 HTTP 200 with business status 0.

        The platform sometimes returns no ``item_id`` even though the submit
        succeeded.  That is a publish success signal, but it is deliberately
        not a ledger receipt: no work ID means no CONSUMED row and no replay.
        """
        if self.fault:
            return None
        # ``proof`` drains the response bodies and normalises response results.
        if self.proof():
            return None
        if (self.pending or len(self.responses) != 1 or
                len(self.requests) != len(self.responses) or
                not set(self.requests).issubset(self.finished)):
            return None
        entry=self.responses[0]
        if entry.get('result') != 'PENDING_MISSING_ID':
            return None
        if entry.get('status') != 200:
            return None
        return dict(entry,source='playwright_response',result='SUCCESS_NO_ID',
                    ok=True,work_id=None,item_id=None,status_code=0)
    def _page_work_proof(self,idless):
        """Return a page receipt only when it is new and material-bound.

        This is not a list-based success guess: the callback must prove that a
        work appeared after submit and that its material fingerprint equals
        this attempt's fingerprint.  No callback, no unique match, or any
        mismatch leaves the result UNKNOWN.
        """
        if not callable(self.page_work_probe):
            return None
        if self.creation_id is None or self.video_id is None or not idless:
            return None
        now_mono=time.monotonic()
        if self.page_fallback_attempted and now_mono-self.page_fallback_attempted<1.0:
            return None
        self.page_fallback_attempted=now_mono
        context={'attempt_id':self.attempt_id,'account_id':self.account_id,
                 'fingerprint':self.fingerprint,'creation_id':self.creation_id,
                 'video_id':self.video_id,'submitted_at':self.started_at,
                 'baseline_work_ids':sorted(self.baseline_work_ids)}
        try:
            candidate=self.page_work_probe(context)
        except Exception as exc:
            self.page_fallback_error=str(exc)[:300]
            return None
        if not isinstance(candidate,dict) or candidate.get('new_after_submit') is not True:
            return None
        if candidate.get('fingerprint')!=self.fingerprint:
            return None
        work_id=parse_work_id({'status_code':0,'item_id':candidate.get('work_id')})
        if not work_id or work_id in self.baseline_work_ids:
            return None
        if candidate.get('creation_id') not in (None,self.creation_id) or \
                candidate.get('video_id') not in (None,self.video_id):
            return None
        observed_at=candidate.get('observed_at',time.time())
        try:
            observed_at=float(observed_at)
        except (TypeError,ValueError):
            return None
        if observed_at<self.started_at:
            return None
        base=dict(idless[-1]); base.pop('result',None)
        self.page_proof=dict(base,source='platform_page',result='SUCCESS',ok=True,
            item_id=work_id,work_id=work_id,status_code=0,fingerprint=self.fingerprint,
            new_after_submit=True,observed_at=observed_at,
            page_url=str(candidate.get('page_url') or '')[:2000])
        return self.page_proof
    def close(self):
        self.active=False
        for emitter,event,callback in self.handlers:
            try: emitter.remove_listener(event,callback)
            except Exception: pass
        self.handlers=[]
        if getattr(self,'observer_name',None):
            # inject-ok: 触发脚本里的闭包清理，不依赖任何 window 全局属性。
            try: self.page.evaluate("name => document.dispatchEvent(new Event(name))",
                                    self.observer_name+'Stop')
            except Exception: pass
        if self.cdp is not None:
            if getattr(self,'observer_script_id',None):
                try: self.cdp.send('Page.removeScriptToEvaluateOnNewDocument',{'identifier':self.observer_script_id})
                except Exception: pass
            try: self.cdp.detach()
            except Exception: pass

# Shared by the Playwright read and the read-only MutationObserver. A text
# node is eligible only when it and every ancestor have visible rendered boxes.
VISIBLE_TEXT_SCRIPT = r'''root => {
 const visible=n=>{
   const el=n.nodeType===3?n.parentElement:n;
   if(!el||!el.isConnected||el.closest('script,style,template,noscript'))return false;
   for(let p=el;p;p=p.parentElement){
     const s=getComputedStyle(p), box=p.getBoundingClientRect();
     if(p.getAttribute('aria-hidden')?.toLowerCase()==='true'||
        s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||
        Number(s.opacity)===0||box.width<=0||box.height<=0)return false;
   }
   return true;
 };
 const read=n=>{
   if(!n||(n.nodeType!==1&&n.nodeType!==3)||!visible(n))return '';
   if(n.nodeType===3)return n.textContent||'';
   if(n.nodeType!==1)return '';
   return Array.from(n.childNodes).map(read).join('');
 };
 return read(root);
}'''

# Only reads DOM and reports diagnostics; never writes platform evidence.
# The only window property here is Playwright's own expose_binding channel.
# Install idempotency and stop are handled without window-scoped state: the
# caller installs once per page, and teardown is a DOM event the closure owns.
# inject-ok: read-only DOM observer, reports diagnostics, never writes evidence.
MONITOR_SCRIPT = r'''(() => {
 const name=__BINDING__, failures=__FAILURES__;
 const report=s=>{ if(typeof window[name]==='function') window[name](s); };
 const failed=text=>failures.find(s=>(text||'').includes(s));
 const renderedText=(__VISIBLE_TEXT__);
 const inspect=()=>{
   if(!document.body)return;
   const f=failed(renderedText(document.body)); if(f)report('VERIFICATION_FAILURE:'+f);
 };
 const observer=new MutationObserver(records=>{
   for(const record of records){
     // Detached/hidden nodes fail visible() before any text is matched.
     for(const n of record.addedNodes){const f=failed(renderedText(n));if(f)report('VERIFICATION_FAILURE:'+f);}
     if(record.type==='characterData'){const f=failed(renderedText(record.target));if(f)report('VERIFICATION_FAILURE:'+f);}
   }
   inspect();
 });
 observer.observe(document,{subtree:true,childList:true,characterData:true,attributes:true});
 inspect();const timer=setInterval(inspect,100);
 document.addEventListener(name+'Stop',()=>{observer.disconnect();clearInterval(timer);},{once:true});
})();'''

def install_monitor(page,receipt,failure_markers):
    # 每个 page 只装一次：脚本内不再用 window 标记做幂等，重复调用会挂两个
    # observer 和两个 100ms 定时器，所以幂等由这里保证。
    if getattr(receipt,'observer_script_id',None):
        return
    name='_publishMonitor_'+uuid.uuid4().hex
    page.expose_binding(name,lambda source,reason: receipt.observe_page_failure(reason)
                        if source.get('frame')==page.main_frame else None)
    script=MONITOR_SCRIPT.replace('__BINDING__',json.dumps(name)).replace('__FAILURES__',json.dumps(list(failure_markers))).replace('__VISIBLE_TEXT__',VISIBLE_TEXT_SCRIPT)
    receipt.observer_name=name
    receipt.observer_script_id=receipt.cdp.send('Page.addScriptToEvaluateOnNewDocument',{'source':script})['identifier']
    # inject-ok: 同一个只读观察脚本补装到当前文档（新文档由 CDP 自动注入）。
    page.evaluate(script)
