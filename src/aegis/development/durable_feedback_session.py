"""DEVELOPMENT persistent temporal operations; not a production trust anchor.

Committed SQLite WAL/FULL operations are replayed before restart use. An external
checkpoint must match exactly. A checkpoint restored together with the database
cannot detect rollback. Source authentication and checkpoint custody are outside
this prototype. No hardware action is executed or authorized.
"""
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3

from .temporal_feedback_1d import TemporalFeedbackSession


class RestartRefused(ValueError):
    pass


class DurabilityUncertain(OSError):
    pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def runtime_identity():
    modules=('aegis.development.durable_feedback_session','aegis.development.temporal_feedback_1d',
             'aegis.development.recovery_feedback_state_1d','aegis.development.recovery_envelope_state_1d',
             'aegis.development.recovery_envelope_1d','aegis.development.independent_clock_mapping',
             'aegis.development.runtime_readiness')
    return dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version,
        sources={name:hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest() for name in modules})


def _dispatch(session,op):
    if not isinstance(op,dict) or 'type' not in op:raise ValueError('operation required')
    kind=op['type'];args={k:v for k,v in op.items() if k!='type'}
    if kind=='INGEST':return session.ingest(**args)
    if kind=='ASSESS':return session.assess_at(**args)
    if kind=='BEGIN_SESSION':return session.begin_session(**args)
    raise ValueError('unsupported persistent operation')


def _sync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


class DurableFeedbackSession:
    MAX_EVENTS=512

    @classmethod
    def create(cls,directory,config,*,store_id):
        if type(store_id) is not str or not 0<len(store_id)<=128:raise ValueError('explicit store identity required')
        # Validate config before creating files; no physical reset is inferred.
        TemporalFeedbackSession(**deepcopy(config))
        directory=Path(directory);directory.mkdir(mode=0o700,exist_ok=False)
        path=directory/'state.sqlite'
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd);_sync_dir(directory)
        con=cls._connect(directory)
        try:
            header=dict(schema='nexvia-durable-feedback/1',config=deepcopy(config),runtime=runtime_identity(),
                        store_id=store_id,nonce=os.urandom(32).hex())
            raw=canonical(header).decode()
            con.execute('BEGIN IMMEDIATE')
            con.execute('CREATE TABLE metadata (header TEXT NOT NULL)')
            con.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY, previous TEXT NOT NULL, operation TEXT NOT NULL, result TEXT NOT NULL, digest TEXT NOT NULL)')
            con.execute('INSERT INTO metadata VALUES (?)',(raw,));con.execute('COMMIT')
            token=dict(store_id=store_id,header_sha256=sha(header),seq=0,head_sha256=sha(header))
        finally:con.close()
        _sync_dir(directory);_sync_dir(directory.parent)
        return cls.open(directory,expected_checkpoint=token)

    @staticmethod
    def _connect(directory):
        directory=Path(directory)
        if directory.is_symlink():raise RestartRefused('symlinked store')
        for name in ('state.sqlite','state.sqlite-wal','state.sqlite-shm'):
            if (directory/name).is_symlink():raise RestartRefused('symlinked database component')
        if not (directory/'state.sqlite').is_file():raise RestartRefused('missing store; never create on restart')
        con=sqlite3.connect((directory/'state.sqlite').resolve().as_uri()+'?mode=rw',uri=True,isolation_level=None,timeout=0)
        try:
            con.execute('PRAGMA trusted_schema=OFF')
            if con.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower()!='wal':raise RestartRefused('WAL unavailable')
            con.execute('PRAGMA synchronous=FULL');con.execute('PRAGMA fullfsync=ON');con.execute('PRAGMA checkpoint_fullfsync=ON')
            if con.execute('PRAGMA synchronous').fetchone()[0]!=2:raise RestartRefused('FULL synchronization unavailable')
            return con
        except BaseException:con.close();raise

    @classmethod
    def open(cls,directory,*,expected_checkpoint):
        if (not isinstance(expected_checkpoint,dict) or set(expected_checkpoint)!={'store_id','header_sha256','seq','head_sha256'}
                or type(expected_checkpoint['seq']) is not int or not 0<=expected_checkpoint['seq']<=cls.MAX_EVENTS
                or type(expected_checkpoint['store_id']) is not str or not 0<len(expected_checkpoint['store_id'])<=128
                or any(type(expected_checkpoint[k]) is not str or not re.fullmatch('[0-9a-f]{64}',expected_checkpoint[k]) for k in ('header_sha256','head_sha256'))):
            raise RestartRefused('explicit well-formed independent checkpoint required')
        obj=object.__new__(cls);obj.directory=Path(directory);obj._con=cls._connect(directory);obj._poisoned=False
        try:
            obj._con.execute('BEGIN IMMEDIATE')
            if obj._con.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise RestartRefused('SQLite integrity check failed')
            rows=obj._con.execute('SELECT header FROM metadata').fetchall()
            if len(rows)!=1:raise RestartRefused('one immutable header required')
            header=json.loads(rows[0][0]);seed=sha(header)
            if header.get('schema')!='nexvia-durable-feedback/1' or header['runtime']!=runtime_identity():raise RestartRefused('runtime/source pin mismatch')
            session=TemporalFeedbackSession(**deepcopy(header['config']))
            events=obj._con.execute('SELECT seq,previous,operation,result,digest FROM events ORDER BY seq LIMIT ?', (cls.MAX_EVENTS+1,)).fetchall()
            if len(events)>cls.MAX_EVENTS:raise RestartRefused('event resource bound exceeded')
            previous=seed
            for expected,row in enumerate(events,1):
                seq,prior,op_raw,result_sha,digest=row
                op=json.loads(op_raw)
                if seq!=expected or prior!=previous or sha(dict(seq=seq,previous=prior,operation=op,result=result_sha))!=digest:
                    raise RestartRefused('persistent operation chain mismatch')
                if sha(_dispatch(session,op))!=result_sha:raise RestartRefused('persistent operation reconstruction mismatch')
                previous=digest
            token=dict(store_id=header['store_id'],header_sha256=seed,seq=len(events),head_sha256=previous)
            if expected_checkpoint!=token:raise RestartRefused('external checkpoint mismatch; rollback or unacknowledged commit requires review')
            obj._con.execute('COMMIT')
            obj._session=session;obj._checkpoint=token
            return obj
        except BaseException:
            obj._con.close();raise

    @property
    def checkpoint(self):return deepcopy(self._checkpoint)

    def _commit(self):self._con.execute('COMMIT')

    def apply(self,operation):
        if self._poisoned:raise DurabilityUncertain('store connection previously failed; explicit reopen/reconciliation required')
        raw=canonical(operation)
        if len(raw)>65536:raise ValueError('operation resource limit')
        if self._checkpoint['seq']>=self.MAX_EVENTS:raise RestartRefused('persistent session resource bound; no silent compaction')
        try:
            self._con.execute('BEGIN IMMEDIATE')
            tail=self._con.execute('SELECT seq,digest FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            actual=(0,self._checkpoint['header_sha256']) if tail is None else tail
            if actual!=(self._checkpoint['seq'],self._checkpoint['head_sha256']):raise RestartRefused('concurrent writer or changed database head')
            trial=deepcopy(self._session);result=_dispatch(trial,json.loads(raw))
            seq=self._checkpoint['seq']+1;result_sha=sha(result)
            digest=sha(dict(seq=seq,previous=self._checkpoint['head_sha256'],operation=json.loads(raw),result=result_sha))
            self._con.execute('INSERT INTO events VALUES (?,?,?,?,?)',(seq,self._checkpoint['head_sha256'],raw.decode(),result_sha,digest))
            self._commit()
            # Commit before exposing ACCEPTED. No hardware side effect precedes it.
            self._session=trial;self._checkpoint=dict(self._checkpoint,seq=seq,head_sha256=digest)
            return dict(result=result,checkpoint=self.checkpoint,operational_authorization=False)
        except BaseException:
            self._poisoned=True
            try:self._con.execute('ROLLBACK')
            except sqlite3.Error:pass
            raise

    def close(self):
        self._poisoned=True;self._con.close()

    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
