from copy import deepcopy
import json
from pathlib import Path
import pytest
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,inspect,_entry,_encode,ZERO_HASH
from scripts.research.streaming_ledger import LedgerStream,inspect_stream
from scripts.research import physical_reference_study as reference,audit_reference_stream as streaming


def make(path,final=True,error=False,interleaved=False):
 with DevelopmentLedger.create(path,study='synthetic',assignments=[{'id':'a'},{'id':'b'}],record_events=True) as w:
  w.start('a')
  if interleaved:w.start('b')
  for i in range(10):w.event('a',details={'value':i})
  w.complete('a',status='ERROR' if error else 'COMPLETED',details={})
  if not interleaved:w.start('b')
  if final:w.complete('b',status='COMPLETED',details={});w.finalize()


@pytest.mark.parametrize('final,error,interleaved',[(True,False,False),(True,True,False),(False,False,False),(True,False,True)])
def test_stream_summary_matches_existing_reader(tmp_path,final,error,interleaved):
 p=tmp_path/'a.jsonl';make(p,final,error,interleaved);old=inspect(p)
 assert inspect_stream(p)=={k:v for k,v in old.items() if k!='records'}


def test_prefix_or_abandoned_iterator_cannot_claim_acceptance(tmp_path):
 p=tmp_path/'a.jsonl';make(p)
 with LedgerStream(p) as r:
  iterator=iter(r);assert next(iterator)['kind']=='HEADER'
  with pytest.raises(LedgerError):r.summary()
 with pytest.raises(LedgerError):r.summary()


@pytest.mark.parametrize('defect',['truncated','tampered','after_final','empty','duplicate_key','noncanonical','wrong_index_type'])
def test_bad_bytes_rejected_by_both_readers(tmp_path,defect):
 p=tmp_path/'a.jsonl';make(p);raw=p.read_bytes()
 if defect=='truncated':raw=raw[:-1]
 elif defect=='tampered':raw=raw.replace(b'"value":0',b'"value":9',1)
 elif defect=='after_final':raw+=raw.splitlines(keepends=True)[-1]
 elif defect=='empty':raw=b''
 elif defect=='duplicate_key':raw=raw.replace(b'"index":0',b'"index":0,"index":0',1)
 elif defect=='noncanonical':raw=raw.replace(b'"index":0',b'"index": 0',1)
 else:raw=raw.replace(b'"index":0',b'"index":false',1)
 p.write_bytes(raw)
 for reader in (inspect,inspect_stream):
  with pytest.raises(LedgerError):reader(p)


def test_trailing_record_is_not_hidden_by_a_final_marker(tmp_path):
 p=tmp_path/'a.jsonl';make(p)
 with p.open('ab') as f:f.write(b'incomplete')
 with LedgerStream(p) as reader:
  with pytest.raises(LedgerError):list(reader)
  with pytest.raises(LedgerError):reader.summary()


@pytest.fixture
def physical_partial(tmp_path):
 p=tmp_path/'physical.jsonl';meta={'sources':reference.hashes(),'classification':'SYNTHETIC_FIXTURE'}
 assignments=[dict(a,metadata=meta) for a in reference.plan()];a=assignments[0]
 with DevelopmentLedger.create(p,study=reference.STUDY,assignments=assignments,record_events=True) as w:
  w.start(a['id']);result=reference.run_episode(a,lambda e:w.event(a['id'],details=e))
  w.complete(a['id'],status='COMPLETED',details={'summary':result,'sources_after':meta['sources']})
 return p


def test_streaming_study_reconstruction_matches_existing_partial_audit(physical_partial):
 old=reference.audit(physical_partial);new=streaming.audit(physical_partial)
 assert streaming.normalized(new)==streaming.normalized(old)
 assert new['ledger_state']=='INCOMPLETE' and new['counts']['ASSIGNED']==125
 assert new['peak_buffered_episode_events']==181
 assert all(r['summary'] is None for r in new['assignments'][1:])


def test_streaming_study_reader_does_not_advance_physics(physical_partial,monkeypatch):
 def fail(*args,**kw):raise AssertionError('reader advanced physics')
 monkeypatch.setattr(reference.ForceLimitedBrakeEnvironment,'advance_prepared',fail)
 assert streaming.audit(physical_partial)['counts']['COMPLETED']==1


def test_rehashed_false_episode_rejected_by_both_study_readers(physical_partial,tmp_path):
 records=deepcopy(inspect(physical_partial)['records']);event=next(r for r in records if r['kind']=='EVENT' and r['details']['type']=='SENSORS')
 event['details']['monitor']['feedback']['force_acceleration']['status']='FALSE_COMPATIBLE'
 out=tmp_path/'false.jsonl';previous=ZERO_HASH
 with out.open('wb') as f:
  for i,r in enumerate(records):
   e=_entry(i,previous,r);f.write(_encode(e)+b'\n');previous=e['sha256']
 for reader in (reference.audit,streaming.audit):
  with pytest.raises(ValueError):reader(out)
