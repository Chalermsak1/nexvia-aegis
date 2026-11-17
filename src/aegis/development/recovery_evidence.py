"""Durable DEVELOPMENT_SIMULATION evidence predicates; never a trust anchor.

Source allowlists, statements and external checkpoint pins are caller premises.
Finite predicate support does not authenticate sensors or establish hardware facts.
"""
from copy import deepcopy
from fractions import Fraction as Q
from pathlib import Path
import fcntl,hashlib,json,os,re
from .durable_feedback_session import canonical,sha
from .independent_clock_mapping import tick
from .physical_time_recovery import PREMISES

SCOPE='DEVELOPMENT_SIMULATION'
PREMISE_NAMES=tuple(PREMISES.split())
KINDS={'ENCLOSES','IDENTITY','DISTINCT'}
ZERO='0'*64
MAX_EVENTS=4096


def label(value):
    if type(value) is not str or not 0<len(value)<=128:raise ValueError('bounded explicit label required')
    return value


def hexhash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:raise ValueError('SHA-256 identity required')
    return value


def bounded(value):
    if len(canonical(value))>16384:raise ValueError('bounded evidence object required')


def rational(value):
    if type(value) not in (str,int) or len(str(value))>256:raise ValueError('bounded exact rational required')
    return Q(value)


def policy_check(policy):
    if type(policy) is not dict or set(policy)!=set(PREMISE_NAMES):raise ValueError('all nine registered premise policies required')
    for value in policy.values():
        if type(value) is not dict or set(value)!={'source_id','predicate','max_age_ticks'} or value['predicate'] not in KINDS:raise ValueError('exact source/predicate/age policy required')
        label(value['source_id']);tick(value['max_age_ticks'])
    bounded(policy)


def statement_check(statement,policy):
    if type(statement) is not dict or set(statement)!={'scope','input_sha256','requirements'} or statement['scope']!=SCOPE:raise ValueError('development statement required')
    hexhash(statement['input_sha256']);requirements=statement['requirements']
    if type(requirements) is not dict or set(requirements)!=set(policy):raise ValueError('complete statement required')
    for key,value in requirements.items():
        if type(value) is not dict or set(value)!={'predicate','expected'} or value['predicate']!=policy[key]['predicate']:raise ValueError('statement/predicate mismatch')
        expected=value['expected']
        if value['predicate']=='ENCLOSES':
            if type(expected) is not list or not 1<=len(expected)<=16:raise ValueError('bounded interval vector required')
            for interval in expected:
                if type(interval) is not list or len(interval)!=2 or rational(interval[0])>rational(interval[1]):raise ValueError('ordered rational interval required')
        if value['predicate']=='DISTINCT':
            if type(expected) is not list or not 2<=len(expected)<=16 or len(set(expected))!=len(expected):raise ValueError('distinct role labels required')
            for role in expected:label(role)
    bounded(statement)


def predicate_check(requirement,observations):
    kind=requirement['predicate'];expected=requirement['expected']
    if kind=='IDENTITY':return canonical(observations)==canonical(expected)
    if kind=='DISTINCT':
        if type(observations) is not dict or set(observations)!=set(expected):raise ValueError('exact role observations required')
        for value in observations.values():label(value)
        return len(set(observations.values()))==len(expected)
    if type(observations) is not list or len(observations)!=len(expected):raise ValueError('observation vector mismatch')
    return all(rational(lo)<=rational(value)<=rational(hi) for value,(lo,hi) in zip(observations,expected))


def artifact_check(a,policy):
    fields={'id','premise','source_id','scope','statement_sha256','boot_id','clock_domain','observed_tick','expires_tick','kind','observations'}
    if type(a) is not dict or set(a)!=fields or a['scope']!=SCOPE:raise ValueError('exact simulation artifact required')
    for key in ('id','source_id','boot_id','clock_domain'):label(a[key])
    if a['premise'] not in policy or a['source_id']!=policy[a['premise']]['source_id']:raise ValueError('unregistered premise/source')
    hexhash(a['statement_sha256']);tick(a['observed_tick']);tick(a['expires_tick'])
    if a['expires_tick']<=a['observed_tick'] or a['kind'] not in ('OBSERVATION','ASSERTED','UNKNOWN'):raise ValueError('positive validity and explicit evidence kind required')
    if a['kind']!='OBSERVATION' and a['observations'] is not None:raise ValueError('assumptions/unknowns cannot carry observations')
    bounded(a)


def vector(state,statement,policy,now):
    statement_check(statement,policy);binding=sha(statement);answer={}
    for key in PREMISE_NAMES:
        candidates=[a for a in state['artifacts'].values() if a['premise']==key and a['statement_sha256']==binding and a['boot_id']==state['boot_id'] and a['clock_domain']==state['clock_domain']]
        a=max(enumerate(candidates),key=lambda x:(x[1]['observed_tick'],x[0]))[1] if candidates else None;status='UNKNOWN'
        negative_ids=set(state['contradiction_evidence'].get(key,[]));invalid_ids=[]
        for item in candidates:
            if item['kind']=='OBSERVATION':
                try:
                    if not predicate_check(statement['requirements'][key],item['observations']):negative_ids.add(item['id'])
                except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError):invalid_ids.append(item['id'])
        if state['fault'] is not None:status='LEDGER_FAULT'
        elif key in state['contradictions']:status='CONTRADICTED'
        elif invalid_ids:status='INVALID_EVIDENCE'
        elif negative_ids:status='CONTRADICTED'
        elif a is not None and a['statement_sha256']==binding and a['boot_id']==state['boot_id'] and a['clock_domain']==state['clock_domain']:
            if now<a['observed_tick']:status='FUTURE'
            elif now>=a['expires_tick'] or now-a['observed_tick']>policy[key]['max_age_ticks']:status='EXPIRED'
            elif a['kind']!='OBSERVATION':status=a['kind']
            else:status='SUPPORTED_SIMULATION_PREDICATE' if predicate_check(statement['requirements'][key],a['observations']) else 'CONTRADICTED'
        answer[key]=dict(status=status,artifact_id=None if a is None else a['id'],source_id=policy[key]['source_id'],contradiction_artifact_ids=sorted(negative_ids),invalid_artifact_ids=sorted(invalid_ids),evaluated_artifact_ids=[x['id'] for x in candidates],ledger_fault=state['fault'])
    return answer


def reduce(state,event,header):
    s=deepcopy(state);kind=event['kind'];now=event['now'];tick(now)
    if kind=='BOOT':
        if set(event)!={'kind','now','boot_id','clock_domain'}:raise ValueError('boot fields')
        boot=label(event['boot_id']);domain=label(event['clock_domain'])
        if boot in s['boots']:raise ValueError('retired/current boot cannot be reused')
        s.update(boot_id=boot,clock_domain=domain,now=now);s['boots'].append(boot);return s
    if now<s['now']:s['fault']='CLOCK_REGRESSION'
    s['now']=max(s['now'],now)
    if kind=='REJECT':
        if set(event)!={'kind','now','reason','artifact_sha256'}:raise ValueError('reject fields')
        s['fault']='MALFORMED_OR_FOREIGN_EVIDENCE';return s
    if kind=='FAULT':
        if set(event)!={'kind','now','reason'}:raise ValueError('fault fields')
        s['fault']=label(event['reason']);return s
    if kind=='ARTIFACT':
        if set(event)!={'kind','now','artifact'}:raise ValueError('artifact event fields')
        a=event['artifact'];artifact_check(a,header['policy']);name=a['id'];digest=sha(a)
        if name in s['seen']:
            if s['seen'][name]!=digest:s['fault']='EVIDENCE_ID_CONFLICT'
            return s
        s['seen'][name]=digest
        if a['boot_id']!=s['boot_id'] or a['clock_domain']!=s['clock_domain']:
            s['fault']='EVIDENCE_BOOT_OR_CLOCK_MISMATCH';return s
        if a['observed_tick']>now:s['fault']='FUTURE_EVIDENCE';return s
        s['artifacts'][name]=a
        previous=s['latest'].get(a['premise'])
        # Late arrivals never displace a newer observation or renew support.
        if previous is None or a['boot_id']!=previous['boot_id'] or a['observed_tick']>=previous['observed_tick']:s['latest'][a['premise']]=a
        return s
    if kind=='EVALUATE':
        if set(event)!={'kind','now','statement','vector'}:raise ValueError('evaluation event fields')
        expected=vector(s,event['statement'],header['policy'],now)
        if event['vector']!=expected:raise ValueError('recorded evidence vector mismatch')
        s['contradictions']=sorted(set(s['contradictions'])|{k for k,v in expected.items() if v['status']=='CONTRADICTED'})
        for key,value in expected.items():
            if value['contradiction_artifact_ids']:s['contradiction_evidence'][key]=value['contradiction_artifact_ids']
        if any(v['status']=='INVALID_EVIDENCE' for v in expected.values()):s['fault']='INVALID_EVIDENCE'
        return s
    raise ValueError('unknown evidence transition')


def initial(header):
    return dict(boot_id=header['boot_id'],clock_domain=header['clock_domain'],boots=[header['boot_id']],now=header['now'],seen={},artifacts={},latest={},contradictions=[],contradiction_evidence={},fault=None)


def evaluation_result(result,statement,checkpoint):
    supported=all(x['status']=='SUPPORTED_SIMULATION_PREDICATE' for x in result.values())
    return dict(status='SIMULATION_PREDICATES_SUPPORTED' if supported else 'EVIDENCE_INSUFFICIENT',premises=result,statement_sha256=sha(statement),checkpoint=checkpoint,operational_authorization=False,hardware_validation=False,independent_attestation=False,scope=SCOPE)


def inspect(directory):
    d=Path(directory);previous=ZERO;rows=[];state=None;header=None
    if d.is_symlink():raise ValueError('journal directory symlink')
    for path in d.iterdir():
        if path.is_symlink() or not path.is_file() or not (path.name=='writer.lock' or re.fullmatch(r'(pending_)?[0-9]{8}\.json',path.name)):raise ValueError('unexpected journal entry')
    paths=sorted(d.glob('[0-9]'*8+'.json'))
    if not paths:raise ValueError('missing committed header')
    for index,path in enumerate(paths):
        if path.is_symlink():raise ValueError('journal symlink')
        if path.stat().st_size>65536:raise ValueError('oversize journal record')
        raw=path.read_bytes();r=json.loads(raw);body={k:r[k] for k in ('seq','previous','payload')}
        if set(r)!={'seq','previous','payload','sha256'} or r['seq']!=index or path.name!='%08d.json'%index or r['previous']!=previous or sha(body)!=r['sha256'] or canonical(r)+b'\n'!=raw:raise ValueError('journal chain mismatch')
        if index==0:
            header=r['payload']
            if set(header)!={'schema','scope','policy','boot_id','clock_domain','now'} or header['schema']!='NEXVIA_EVIDENCE_1' or header['scope']!=SCOPE:raise ValueError('header identity mismatch')
            policy_check(header['policy']);label(header['boot_id']);label(header['clock_domain']);tick(header['now']);state=initial(header)
        else:state=reduce(state,r['payload'],header)
        previous=r['sha256'];rows.append(r)
    if len(rows)>MAX_EVENTS+1:raise ValueError('journal capacity exceeded')
    pending=[dict(name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size_bytes=p.stat().st_size) for p in sorted(d.glob('pending_*'))]
    return dict(header=header,state=state,records=rows,pending=pending,checkpoint=dict(seq=len(rows)-1,head_sha256=previous,header_sha256=rows[0]['sha256']))


class EvidenceJournal:
    """One writer; crash-safe file commits under OS/filesystem assumptions."""
    @classmethod
    def create(cls,directory,*,policy,boot_id,clock_domain,now=0):
        policy_check(policy);label(boot_id);label(clock_domain);tick(now)
        d=Path(directory);d.mkdir(exist_ok=False,mode=0o700)
        with (d/'writer.lock').open('xb') as f:f.flush();os.fsync(f.fileno())
        self=cls();self.directory=d;self._lock=(d/'writer.lock').open('r+b');fcntl.flock(self._lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self._closed=False;self._seq=0;self._previous=ZERO
        self.header=dict(schema='NEXVIA_EVIDENCE_1',scope=SCOPE,policy=deepcopy(policy),boot_id=boot_id,clock_domain=clock_domain,now=now);self.state=initial(self.header)
        try:self._commit(self.header,header=True)
        except BaseException:self.close();raise
        return self

    @classmethod
    def reopen(cls,directory,*,expected_checkpoint):
        self=cls();self.directory=Path(directory);lock=self.directory/'writer.lock'
        if lock.is_symlink():raise ValueError('writer lock symlink')
        self._lock=lock.open('r+b');self._closed=False
        try:
            fcntl.flock(self._lock,fcntl.LOCK_EX|fcntl.LOCK_NB);r=inspect(self.directory)
            if r['pending'] or r['checkpoint']!=expected_checkpoint:raise ValueError('pending evidence or checkpoint mismatch; review required')
            self.header=r['header'];self.state=r['state'];self._seq=r['checkpoint']['seq']+1;self._previous=r['checkpoint']['head_sha256'];self._header_hash=r['checkpoint']['header_sha256']
            return self
        except BaseException:self.close();raise

    @property
    def checkpoint(self):return dict(seq=self._seq-1,head_sha256=self._previous,header_sha256=self._header_hash)

    def _commit(self,event,*,header=False):
        if self._closed:raise ValueError('closed or poisoned journal')
        if self._seq>MAX_EVENTS:raise ValueError('journal capacity exhausted; no eviction')
        state=self.state if header else reduce(self.state,event,self.header)
        body=dict(seq=self._seq,previous=self._previous,payload=event);record=dict(body,sha256=sha(body));raw=canonical(record)+b'\n'
        pending=self.directory/('pending_%08d.json'%self._seq);final=self.directory/('%08d.json'%self._seq)
        try:
            with pending.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            os.link(pending,final);fd=os.open(self.directory,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            pending.unlink()
        except BaseException:self.close();raise
        self.state=state;self._previous=record['sha256'];self._seq+=1
        if header:self._header_hash=record['sha256']

    def submit(self,artifact,*,now):
        tick(now)
        try:artifact_check(artifact,self.header['policy'])
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            try:digest=sha(artifact)
            except (ValueError,TypeError):digest=ZERO
            self._commit(dict(kind='REJECT',now=now,reason=str(exc),artifact_sha256=digest));return dict(status='REJECTED',reason=str(exc),checkpoint=self.checkpoint)
        old=self.state['seen'].get(artifact['id']);self._commit(dict(kind='ARTIFACT',now=now,artifact=deepcopy(artifact)))
        return dict(status='REPLAY_IGNORED' if old==sha(artifact) else 'RECORDED',checkpoint=self.checkpoint)

    def evaluate(self,statement,*,now):
        tick(now);statement_check(statement,self.header['policy'])
        s=deepcopy(self.state)
        if now<s['now']:s['fault']='CLOCK_REGRESSION'
        result=vector(s,statement,self.header['policy'],now)
        self._commit(dict(kind='EVALUATE',now=now,statement=deepcopy(statement),vector=result))
        return evaluation_result(result,statement,self.checkpoint)

    def begin_boot(self,boot_id,clock_domain,*,now):self._commit(dict(kind='BOOT',boot_id=boot_id,clock_domain=clock_domain,now=now))
    def record_fault(self,reason,*,now):self._commit(dict(kind='FAULT',now=now,reason=reason))
    def close(self):
        if not getattr(self,'_closed',True):self._closed=True;self._lock.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class EvidenceReplay:
    """Consume existing evaluation events, without opening a writer or effects."""
    def __init__(self,directory):
        r=inspect(directory);self.header=r['header'];self.records=r['records'];self.state=initial(self.header);self.index=1
        while self.index<len(self.records) and self.records[self.index]['payload']['kind']!='EVALUATE':
            self.state=reduce(self.state,self.records[self.index]['payload'],self.header);self.index+=1

    @property
    def checkpoint(self):return dict(seq=self.index-1,head_sha256=self.records[self.index-1]['sha256'],header_sha256=self.records[0]['sha256'])

    def evaluate(self,statement,*,now):
        if self.index>=len(self.records):raise ValueError('no recorded evaluation remains')
        s=deepcopy(self.state)
        if now<s['now']:s['fault']='CLOCK_REGRESSION'
        result=vector(s,statement,self.header['policy'],now);expected=dict(kind='EVALUATE',now=now,statement=deepcopy(statement),vector=result)
        if expected!=self.records[self.index]['payload']:raise ValueError('replayed evaluation input differs')
        self.state=reduce(self.state,expected,self.header);self.index+=1
        return evaluation_result(result,statement,self.checkpoint)
