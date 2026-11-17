"""One-shot atomic frame transactions for LIVE01. No candidate before persist.

Reuses the pinned EA01 transition and evaluation semantics. Records are private
until the whole bounded bundle is fsynced/committed. Not an actuator transaction.
"""
from copy import deepcopy
import json
from . import recovery_evidence as core
from .durable_feedback_session import sha,canonical


class FrameTransaction:
    def __init__(self,*,policy,boot_id,clock_domain,now):
        core.policy_check(policy);core.label(boot_id);core.label(clock_domain);core.tick(now)
        self.header=dict(schema='NEXVIA_EVIDENCE_1',scope=core.SCOPE,policy=deepcopy(policy),boot_id=boot_id,clock_domain=clock_domain,now=now)
        self.state=core.initial(self.header);self.records=[];self.closed=False;self.persisted=False;self._append(self.header,header=True)
    @property
    def checkpoint(self):return dict(seq=len(self.records)-1,head_sha256=self.records[-1]['sha256'],header_sha256=self.records[0]['sha256'])
    def _append(self,event,*,header=False):
        if self.closed or len(self.records)>=32:raise ValueError('closed or exhausted one-shot frame')
        state=self.state if header else core.reduce(self.state,event,self.header)
        body=dict(seq=len(self.records),previous=core.ZERO if not self.records else self.records[-1]['sha256'],payload=deepcopy(event));self.records.append(dict(body,sha256=sha(body)));self.state=state
    def submit(self,artifact,*,now):
        core.tick(now)
        try:core.artifact_check(artifact,self.header['policy'])
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            try:digest=sha(artifact)
            except (ValueError,TypeError):digest=core.ZERO
            self._append(dict(kind='REJECT',now=now,reason=str(exc),artifact_sha256=digest));return dict(status='REJECTED',reason=str(exc),checkpoint=self.checkpoint)
        old=self.state['seen'].get(artifact['id']);self._append(dict(kind='ARTIFACT',now=now,artifact=deepcopy(artifact)))
        return dict(status='REPLAY_IGNORED' if old==sha(artifact) else 'RECORDED',checkpoint=self.checkpoint)
    def evaluate(self,statement,*,now):
        core.tick(now);s=deepcopy(self.state)
        if now<s['now']:s['fault']='CLOCK_REGRESSION'
        result=core.vector(s,statement,self.header['policy'],now);self._append(dict(kind='EVALUATE',now=now,statement=deepcopy(statement),vector=result))
        return core.evaluation_result(result,statement,self.checkpoint)
    def record_fault(self,reason,*,now):self._append(dict(kind='FAULT',now=now,reason=reason))
    def persist(self,path):
        from .live_recovery_contract import save
        if self.persisted or self.closed:raise ValueError('frame cannot be republished')
        bundle=dict(schema='LIVE01_ATOMIC_EVIDENCE_BUNDLE_1',records=self.records,checkpoint=self.checkpoint,operational_authorization=False)
        if len(canonical(bundle))>131072:raise ValueError('bounded frame bundle required')
        try:save(path,bundle)
        except BaseException:self.closed=True;raise
        self.persisted=True;self.closed=True
    def close(self):self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class BundleReplay(core.EvidenceReplay):
    def __init__(self,path):
        if path.is_symlink() or path.stat().st_size>131072:raise ValueError('unsafe evidence bundle')
        raw=path.read_bytes();bundle=json.loads(raw)
        if set(bundle)!={'schema','records','checkpoint','operational_authorization'} or bundle['schema']!='LIVE01_ATOMIC_EVIDENCE_BUNDLE_1' or bundle['operational_authorization'] is not False or canonical(bundle)+b'\n'!=raw:raise ValueError('bundle identity mismatch')
        self.records=bundle['records']
        if not 1<=len(self.records)<=32:raise ValueError('bundle record bound')
        previous=core.ZERO;state=None
        for index,r in enumerate(self.records):
            body={k:r[k] for k in ('seq','previous','payload')}
            if set(r)!={'seq','previous','payload','sha256'} or r['seq']!=index or r['previous']!=previous or sha(body)!=r['sha256']:raise ValueError('bundle chain mismatch')
            if index==0:
                self.header=r['payload'];core.policy_check(self.header['policy'])
                if set(self.header)!={'schema','scope','policy','boot_id','clock_domain','now'} or self.header['schema']!='NEXVIA_EVIDENCE_1' or self.header['scope']!=core.SCOPE:raise ValueError('bundle header scope')
                core.label(self.header['boot_id']);core.label(self.header['clock_domain']);core.tick(self.header['now'])
                state=core.initial(self.header)
            else:state=core.reduce(state,r['payload'],self.header)
            previous=r['sha256']
        if bundle['checkpoint']!=dict(seq=len(self.records)-1,head_sha256=previous,header_sha256=self.records[0]['sha256']):raise ValueError('bundle checkpoint mismatch')
        self.state=core.initial(self.header);self.index=1
        while self.index<len(self.records) and self.records[self.index]['payload']['kind']!='EVALUATE':self.state=core.reduce(self.state,self.records[self.index]['payload'],self.header);self.index+=1
