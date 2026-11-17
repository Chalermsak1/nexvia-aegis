"""Development-only durable marker effects. NEVER a robot/production executor.

Intent/claim/begin precede an exclusive synthetic file effect. Crash uncertainty
is retained; effects are not retried. All expected pins remain external premises.
SQLite/process-exit tests cannot establish storage power-loss or physical exactly-once.
"""
from copy import deepcopy
import hashlib,json,os,platform,re,sqlite3,time
from pathlib import Path
from .durable_feedback_session import DurableFeedbackSession,RestartRefused,canonical,sha,_sync_dir


class EffectUncertain(OSError):pass


def identity():
    from . import durable_feedback_session
    return dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version,
                sources={str(Path(p).name):hashlib.sha256(Path(p).read_bytes()).hexdigest()
                         for p in (__file__,durable_feedback_session.__file__)})


def label(x):
    if type(x) is not str or not 0<len(x)<=128:raise ValueError('bounded explicit identity required')


def ns(x):
    if type(x) is not int or not 0<=x<2**63:raise ValueError('nonnegative int64 monotonic timestamp required')


def transition(state,event,header):
    s=deepcopy(state);kind=event['kind'];now=event['now'];ns(now)
    if kind=='RECOVER':
        if set(event)!={'kind','now','boot_id'}:raise ValueError('recovery fields')
        boot=event['boot_id'];label(boot)
        if boot!=s['boot']:
            if boot in s['boots']:raise ValueError('retired boot cannot be reused')
            s['boots'].append(boot);s['boot']=boot;s['last_ns']=now
        elif now<s['last_ns']:raise ValueError('clock regression; new boot/review required')
        for row in s['commands'].values():
            if row['status']=='CLAIMED':row['status']='EFFECT_UNCERTAIN'
            if row['status']=='RECORDED' and row['boot_id']!=boot:row['status']='EXPIRED'
        s['last_ns']=now;return s
    if now<s['last_ns']:raise ValueError('monotonic clock regressed')
    s['last_ns']=now;name=event['command_id'];label(name)
    if kind=='RECORD':
        if set(event)!={'kind','now','command_id','plan','expires'}:raise ValueError('record fields')
        if name in s['commands']:raise ValueError('command identity already consumed/recorded')
        ns(event['expires']);p=event['plan']
        if event['expires']<=now:raise ValueError('future command expiry required')
        if (not isinstance(p,dict) or p.get('status') not in ('CONDITIONAL_PHYSICAL_TIME_PLAN','CONDITIONAL_FAMILY_DEVELOPMENT_PLAN','DEVELOPMENT_BASELINE_ACTION')
                or p.get('dispatch') is not False or p.get('operational_authorization') is not False
                or p.get('hardware_validation') is not False or p.get('gate_b')!='GATE_B_NOT_AUTHORIZED'):
            raise ValueError('only explicit non-authorized development plans accepted')
        if len(s['commands'])>=64:raise ValueError('command resource limit; no eviction')
        s['commands'][name]=dict(status='RECORDED',boot_id=s['boot'],created=now,expires=event['expires'],plan_sha256=sha(p),token=None)
        return s
    row=s['commands'][name]
    if kind=='CLAIM':
        if set(event)!={'kind','now','command_id','token'}:raise ValueError('claim fields')
        if row['status']!='RECORDED' or row['boot_id']!=s['boot']:raise ValueError('one claim on current boot required')
        if now>=row['expires']:raise ValueError('claim expired')
        if type(event['token']) is not str or not re.fullmatch('[0-9a-f]{64}',event['token']):raise ValueError('claim identity required')
        row.update(status='CLAIMED',token=event['token'])
    elif kind=='EXPIRE':
        if set(event)!={'kind','now','command_id'} or row['status']!='RECORDED' or now<row['expires']:raise ValueError('expiry transition')
        row['status']='EXPIRED'
    elif kind=='BEGIN':
        if set(event)!={'kind','now','command_id','token'} or row['status']!='CLAIMED' or row['token']!=event['token'] or row['boot_id']!=s['boot'] or now>=row['expires']:raise ValueError('invalid begin/expired effect')
        row['status']='EFFECT_UNCERTAIN'  # commit before possible external effect
    elif kind=='OBSERVE':
        if (set(event)!={'kind','now','command_id','marker_sha256','timeliness_established'} or row['status']!='EFFECT_UNCERTAIN'
                or type(event['marker_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',event['marker_sha256'])):raise ValueError('observation transition')
        if type(event['timeliness_established']) is not bool:raise ValueError('explicit timing-evidence status required')
        if event['timeliness_established'] and (row['boot_id']!=s['boot'] or now>=row['expires']):raise ValueError('timeliness not established')
        row.update(status='SYNTHETIC_EFFECT_OBSERVED',marker_sha256=event['marker_sha256'],timeliness_established=event['timeliness_established'])
    else:raise ValueError('unsupported effect transition')
    return s


class DurableSimulationExecutor:
    MAX_EVENTS=512

    @classmethod
    def create(cls,directory,*,store_id,boot_id,clock=time.monotonic_ns):
        label(store_id);label(boot_id);now=clock();ns(now)
        d=Path(directory);d.mkdir(exist_ok=False,mode=0o700);(d/'effects').mkdir(mode=0o700)
        fd=os.open(d/'state.sqlite',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd);_sync_dir(d)
        c=DurableFeedbackSession._connect(d)
        header=dict(schema='nexvia-synthetic-effects/1',store_id=store_id,initial_boot=boot_id,initial_ns=now,runtime=identity(),nonce=os.urandom(32).hex(),effect_kind='EXCLUSIVE_SYNTHETIC_MARKER_ONLY')
        try:
            c.execute('BEGIN IMMEDIATE');c.execute('CREATE TABLE metadata (header TEXT NOT NULL)');c.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY,previous TEXT,payload TEXT,digest TEXT)')
            c.execute('INSERT INTO metadata VALUES (?)',(canonical(header).decode(),));c.execute('COMMIT')
        finally:c.close()
        _sync_dir(d);_sync_dir(d.parent)
        pin=dict(store_id=store_id,header_sha256=sha(header),seq=0,head_sha256=sha(header))
        return cls.open(d,expected_checkpoint=pin,boot_id=boot_id,clock=clock)

    @classmethod
    def open(cls,directory,*,expected_checkpoint,boot_id,clock=time.monotonic_ns):
        label(boot_id)
        if (not isinstance(expected_checkpoint,dict) or set(expected_checkpoint)!={'store_id','header_sha256','seq','head_sha256'}
                or type(expected_checkpoint['seq']) is not int or not 0<=expected_checkpoint['seq']<=cls.MAX_EVENTS
                or any(type(expected_checkpoint[k]) is not str or not re.fullmatch('[0-9a-f]{64}',expected_checkpoint[k]) for k in ('header_sha256','head_sha256'))):raise RestartRefused('exact external checkpoint required')
        o=object.__new__(cls);o.directory=Path(directory);o._clock=clock;o._poisoned=False
        if (o.directory/'effects').is_symlink() or not (o.directory/'effects').is_dir():raise RestartRefused('unsafe/missing marker directory')
        o._con=DurableFeedbackSession._connect(directory)
        try:
            o._con.execute('BEGIN IMMEDIATE')
            if o._con.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise RestartRefused('integrity check')
            rows=o._con.execute('SELECT header FROM metadata').fetchall()
            if len(rows)!=1:raise RestartRefused('one header required')
            header=json.loads(rows[0][0]);seed=sha(header)
            if header.get('schema')!='nexvia-synthetic-effects/1' or header['runtime']!=identity():raise RestartRefused('runtime/source mismatch')
            state=dict(boot=header['initial_boot'],boots=[header['initial_boot']],last_ns=header['initial_ns'],commands={});previous=seed
            rows=o._con.execute('SELECT seq,previous,payload,digest FROM events ORDER BY seq LIMIT ?', (cls.MAX_EVENTS+1,)).fetchall()
            if len(rows)>cls.MAX_EVENTS:raise RestartRefused('event resource limit')
            for n,(seq,prev,raw,h) in enumerate(rows,1):
                e=json.loads(raw)
                if seq!=n or prev!=previous or sha(dict(seq=seq,previous=prev,event=e))!=h:raise RestartRefused('effect chain mismatch')
                state=transition(state,e,header);previous=h
            pin=dict(store_id=header['store_id'],header_sha256=seed,seq=len(rows),head_sha256=previous)
            if pin!=expected_checkpoint:raise RestartRefused('checkpoint mismatch: rollback/unacknowledged commit')
            o._con.execute('COMMIT');o._header=header;o._state=state;o._checkpoint=pin
            o._append(dict(kind='RECOVER',now=clock(),boot_id=boot_id))
            return o
        except BaseException:o._con.close();raise

    @classmethod
    def audit_closed(cls,directory,*,expected_checkpoint):
        """Read-only sealed-store replay. WAL stores must be recovered separately."""
        d=Path(directory)
        if d.is_symlink() or (d/'state.sqlite').is_symlink() or (d/'effects').is_symlink():raise RestartRefused('unsafe sealed store')
        if any((d/n).exists() for n in ('state.sqlite-wal','state.sqlite-shm')):raise RestartRefused('unsealed WAL store; copy/reconcile explicitly')
        c=sqlite3.connect((d/'state.sqlite').resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            if c.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise RestartRefused('sealed integrity check')
            rows=c.execute('SELECT header FROM metadata').fetchall()
            if len(rows)!=1:raise RestartRefused('sealed header count')
            header=json.loads(rows[0][0]);seed=sha(header)
            if header.get('schema')!='nexvia-synthetic-effects/1' or header['runtime']!=identity():raise RestartRefused('sealed source/runtime mismatch')
            state=dict(boot=header['initial_boot'],boots=[header['initial_boot']],last_ns=header['initial_ns'],commands={});previous=seed
            rows=c.execute('SELECT seq,previous,payload,digest FROM events ORDER BY seq LIMIT ?', (cls.MAX_EVENTS+1,)).fetchall()
            if len(rows)>cls.MAX_EVENTS:raise RestartRefused('sealed event bound')
            for n,(seq,prev,raw,h) in enumerate(rows,1):
                e=json.loads(raw)
                if seq!=n or prev!=previous or sha(dict(seq=seq,previous=prev,event=e))!=h:raise RestartRefused('sealed event mismatch')
                state=transition(state,e,header);previous=h
            pin=dict(store_id=header['store_id'],header_sha256=seed,seq=len(rows),head_sha256=previous)
            if pin!=expected_checkpoint:raise RestartRefused('sealed checkpoint mismatch')
            for name,row in state['commands'].items():
                if row['status']=='SYNTHETIC_EFFECT_OBSERVED':
                    p=d/'effects'/(sha(name)+'.json')
                    if p.is_symlink():raise RestartRefused('sealed marker symlink')
                    raw=p.read_bytes();expected=canonical(dict(classification='SYNTHETIC_MARKER_NOT_ROBOT_EFFECT',store_id=header['store_id'],command_id=name,plan_sha256=row['plan_sha256'],claim_token=row['token']))+b'\n'
                    if raw!=expected or hashlib.sha256(raw).hexdigest()!=row['marker_sha256']:raise RestartRefused('sealed marker mismatch')
            return dict(state=state,checkpoint=pin,operational_authorization=False)
        finally:c.close()

    @property
    def checkpoint(self):return deepcopy(self._checkpoint)
    @property
    def state(self):return deepcopy(self._state)
    def _commit(self):self._con.execute('COMMIT')
    def _after_effect_sync(self):pass

    def _append(self,event):
        if self._poisoned:raise EffectUncertain('failed connection; explicit reconciliation required')
        if self._checkpoint['seq']>=self.MAX_EVENTS:raise RestartRefused('event limit')
        if len(canonical(event))>131072:raise ValueError('event resource limit')
        try:
            self._con.execute('BEGIN IMMEDIATE');tail=self._con.execute('SELECT seq,digest FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            actual=(0,self._checkpoint['header_sha256']) if tail is None else tail
            if actual!=(self._checkpoint['seq'],self._checkpoint['head_sha256']):raise RestartRefused('stale writer')
            state=transition(self._state,event,self._header);seq=self._checkpoint['seq']+1;prev=self._checkpoint['head_sha256'];h=sha(dict(seq=seq,previous=prev,event=event))
            self._con.execute('INSERT INTO events VALUES (?,?,?,?)',(seq,prev,canonical(event).decode(),h));self._commit()
            self._state=state;self._checkpoint=dict(self._checkpoint,seq=seq,head_sha256=h)
        except BaseException:
            self._poisoned=True
            try:self._con.execute('ROLLBACK')
            except sqlite3.Error:pass
            raise

    def record(self,command_id,plan,*,expires_ns):
        self._append(dict(kind='RECORD',now=self._clock(),command_id=command_id,plan=deepcopy(plan),expires=expires_ns));return self.checkpoint

    def claim(self,command_id):
        now=self._clock();row=self._state['commands'][command_id]
        if row['status']=='RECORDED' and now>=row['expires']:
            self._append(dict(kind='EXPIRE',now=now,command_id=command_id));return dict(status='EXPIRED',token=None,checkpoint=self.checkpoint)
        token=sha(dict(store=self._checkpoint['header_sha256'],seq=self._checkpoint['seq']+1,command_id=command_id))
        self._append(dict(kind='CLAIM',now=now,command_id=command_id,token=token))
        return dict(status='CLAIMED',token=token,checkpoint=self.checkpoint)

    def _marker(self,command_id):
        row=self._state['commands'][command_id]
        return dict(classification='SYNTHETIC_MARKER_NOT_ROBOT_EFFECT',store_id=self._header['store_id'],command_id=command_id,plan_sha256=row['plan_sha256'],claim_token=row['token'])

    def simulate_effect(self,command_id,*,token):
        self._append(dict(kind='BEGIN',now=self._clock(),command_id=command_id,token=token))
        path=self.directory/'effects'/(sha(command_id)+'.json');data=canonical(self._marker(command_id))+b'\n'
        try:
            if (self.directory/'effects').is_symlink():raise RestartRefused('symlinked marker root')
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            _sync_dir(path.parent);self._after_effect_sync();now=self._clock();row=self._state['commands'][command_id]
            if now<self._state['last_ns'] or now>=row['expires']:
                self._poisoned=True
                return dict(status='EFFECT_UNCERTAIN',reason='POST_EFFECT_DEADLINE_OR_CLOCK_FAILURE',checkpoint=self.checkpoint,operational_authorization=False)
            self._append(dict(kind='OBSERVE',now=now,command_id=command_id,marker_sha256=hashlib.sha256(data).hexdigest(),timeliness_established=True))
            return dict(status='SYNTHETIC_EFFECT_OBSERVED',checkpoint=self.checkpoint,operational_authorization=False)
        except BaseException:
            self._poisoned=True;raise

    def reconcile_marker(self,command_id,*,expected_marker_sha256):
        if self._poisoned:raise EffectUncertain('reopen before reconciliation')
        row=self._state['commands'][command_id]
        if row['status']!='EFFECT_UNCERTAIN':raise ValueError('only uncertain effects can be reconciled')
        path=self.directory/'effects'/(sha(command_id)+'.json')
        if (self.directory/'effects').is_symlink() or path.is_symlink():raise RestartRefused('unsafe marker')
        if not path.is_file():return dict(status='EFFECT_UNCERTAIN',reason='ABSENCE_IS_NOT_PROOF_OF_NON_EXECUTION',checkpoint=self.checkpoint)
        raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest()
        if raw!=canonical(self._marker(command_id))+b'\n' or h!=expected_marker_sha256:raise RestartRefused('synthetic effect evidence mismatch')
        self._append(dict(kind='OBSERVE',now=self._clock(),command_id=command_id,marker_sha256=h,timeliness_established=False))
        return dict(status='SYNTHETIC_EFFECT_OBSERVED',timeliness_established=False,checkpoint=self.checkpoint,operational_authorization=False)

    def close(self):self._poisoned=True;self._con.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
