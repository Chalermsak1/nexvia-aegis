"""Streaming reader for the existing DEVELOPMENT ledger schemas.

Only an exhausted iterator validates the complete visible file. A yielded prefix
is not an accepted ledger. No resume/repair/write or independent authentication.
Memory retains assignment states and one line, not the entire raw/event log.
"""
import json
from pathlib import Path
from scripts.research.development_ledger import SCHEMA,EVENT_SCHEMA,ZERO_HASH,LedgerError,_unique_object,_assignment_ids,_entry,_encode


class LedgerStream:
    def __init__(self,path):
        self.path=Path(path);self.fd=None;self.started=False;self.exhausted=False;self.failed=False
        self.states=None;self.event_counts={};self.schema=None;self.finalized=False;self.previous=ZERO_HASH
        self.lines=0;self.peak_line_bytes=0

    def __enter__(self):
        if self.fd is not None or self.started:raise LedgerError('stream already used')
        self.fd=self.path.open('rb');return self

    def __exit__(self,*args):
        if self.fd is not None:self.fd.close();self.fd=None

    def __iter__(self):
        if self.fd is None or self.started:raise LedgerError('stream must be opened once')
        self.started=True
        try:
            for index,raw in enumerate(self.fd):
                self.peak_line_bytes=max(self.peak_line_bytes,len(raw))
                if not raw.endswith(b'\n'):raise LedgerError('truncated ledger record')
                line=raw[:-1]
                try:
                    obj=json.loads(line,object_pairs_hook=_unique_object,parse_constant=lambda _:(_ for _ in ()).throw(LedgerError('nonfinite value')))
                except (ValueError,UnicodeDecodeError) as exc:raise LedgerError('invalid JSON record') from exc
                if not isinstance(obj,dict) or set(obj)!={'index','previous_sha256','payload','sha256'}:raise LedgerError('invalid record envelope')
                if type(obj['index']) is not int or obj['index']!=index or obj['previous_sha256']!=self.previous:raise LedgerError('invalid record ordering or chain')
                p=obj['payload']
                if not isinstance(p,dict) or obj!=_entry(index,self.previous,p) or line!=_encode(obj):raise LedgerError('invalid hash or noncanonical encoding')
                if self.finalized:raise LedgerError('record after finalization')
                self.previous=obj['sha256'];kind=p.get('kind')
                if index==0:
                    if (set(p)!={'kind','schema','classification','study','assignments'} or kind!='HEADER' or
                        p['schema'] not in (SCHEMA,EVENT_SCHEMA) or p['classification']!='EXPLORATORY_SIMULATION' or
                        not isinstance(p['study'],str) or not p['study'].strip()):raise LedgerError('invalid header')
                    self.states={k:'ASSIGNED' for k in _assignment_ids(p['assignments'])};self.event_counts={k:0 for k in self.states};self.schema=p['schema']
                elif self.states is None:raise LedgerError('missing header')
                elif kind=='START':
                    if set(p)!={'kind','id'} or not isinstance(p['id'],str) or self.states.get(p['id'])!='ASSIGNED':raise LedgerError('invalid or duplicate start')
                    self.states[p['id']]='STARTED'
                elif kind=='EVENT':
                    if (self.schema!=EVENT_SCHEMA or set(p)!={'kind','id','event_index','details'} or not isinstance(p['id'],str) or
                        self.states.get(p['id'])!='STARTED' or type(p['event_index']) is not int or
                        p['event_index']!=self.event_counts[p['id']] or not isinstance(p['details'],dict)):raise LedgerError('invalid event')
                    self.event_counts[p['id']]+=1
                elif kind=='TERMINAL':
                    if (set(p)!={'kind','id','status','details'} or not isinstance(p['id'],str) or self.states.get(p['id'])!='STARTED' or
                        p['status'] not in ('COMPLETED','ERROR') or not isinstance(p['details'],dict)):raise LedgerError('invalid terminal')
                    self.states[p['id']]=p['status']
                elif kind=='FINAL':
                    errors=sum(s=='ERROR' for s in self.states.values())
                    if (set(p)!={'kind','assignments','errors'} or type(p['assignments']) is not int or type(p['errors']) is not int or
                        p['assignments']!=len(self.states) or p['errors']!=errors or any(s in ('ASSIGNED','STARTED') for s in self.states.values())):raise LedgerError('invalid finalization')
                    self.finalized=True
                else:raise LedgerError('unknown record type')
                self.lines=index+1
                yield p
            if self.states is None:raise LedgerError('empty/missing header')
            self.exhausted=True
        except BaseException:
            self.failed=True
            raise

    def summary(self):
        if not self.exhausted or self.failed:raise LedgerError('complete stream has not been validated')
        counts={s:sum(v==s for v in self.states.values()) for s in ('ASSIGNED','STARTED','COMPLETED','ERROR')}
        return {'integrity':'VALID_SELF_REPORTED_CHAIN','finalized':self.finalized,
          'state':'INCOMPLETE' if not self.finalized else 'FINALIZED_WITH_ERRORS' if counts['ERROR'] else 'FINALIZED',
          'counts':counts,'assignments':dict(self.states),'event_counts':dict(self.event_counts),'schema':self.schema,'last_sha256':self.previous}


def inspect_stream(path):
    with LedgerStream(path) as reader:
        for _ in reader:pass
        return reader.summary()
