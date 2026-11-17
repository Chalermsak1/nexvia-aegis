from pathlib import Path
from fractions import Fraction as Q
import json,gzip,copy
import pytest
from scripts.research import recovery_envelope_study_1d as study
from scripts.research.development_ledger import DevelopmentLedger
from aegis.env.mujoco_power_brake import PowerBrakeEnvironment


@pytest.mark.parametrize('a',study.plan(),ids=lambda a:a['id'])
def test_declared_analysis_cases_and_native_readonly_corroboration(a,monkeypatch):
 r=study.run_case(a);s=study.summary(r)
 assert s['operational_authorization'] is False and s['future_position_containment']=='NOT_ESTABLISHED'
 if a['native']:
  monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit stepped physics')))
  assert study.run_case(a,r['native'],audit_mode=True)==r
 if a['id']=='point_fast_wall':assert s['finite_horizon_containment'] and not s['point_witness_crosses_position_bound']
 if a['id']=='point_delayed_wall':assert not s['finite_horizon_containment'] and s['point_witness_crosses_position_bound']
 if a['id']=='bounded_feedback_fixed_parameters':assert s['conclusion']=='SUPPORTED_FINITE_MODEL_STATEMENT_ONLY'
 if a['id']=='full_uncertainty_linked':assert not s['finite_horizon_containment']
 if a['id'].startswith('full_uncertainty_partition'):
  assert s['finite_horizon_containment'] and not s['terminal_sample_condition']
  assert s['conclusion']=='NOT_ESTABLISHED_BY_THIS_ENCLOSURE'
  assert 0<s['cells_with_terminal_condition']<s['partition_cells']
 if a['id']=='no_brake_power':assert not s['point_witness_terminal_samples_satisfied']
 if a['id']=='late_power_cut':
  assert s['point_witness_terminal_samples_satisfied'] and s['future_coast_counterexample']['outside_upper_bound']
  assert s['future_coast_counterexample']['additional_steps']>0
 if a['id']=='unknown_measurements':assert s['conclusion']=='UNKNOWN_EVIDENCE'
 if a['id']=='contradictory_measurements':assert s['conclusion']=='CONTRADICTORY_EVIDENCE'
 if a['id']=='unverified_power_premise':assert s['conclusion']=='UNKNOWN_PHYSICAL_PREMISES'
 if a['id'].startswith('unsupported_'):assert s['conclusion']=='UNKNOWN_INPUT'


@pytest.mark.parametrize('field',['missing_native','force','measurement','position','clearance','summary'])
def test_native_record_corruption_is_rejected_without_stepping(field,monkeypatch):
 a=study.plan()[0];result=study.run_case(a);native=copy.deepcopy(result['native'])
 monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit stepped physics')))
 if field=='missing_native':native=None
 if field=='force':native['frames'][0]['plant']['ctrl'][0]=99.
 if field=='measurement':native['frames'][0]['measurement']['velocity_m_s']=99.
 if field=='position':native['frames'][0]['physical']['position'][0]=99.
 if field=='clearance':native['frames'][0]['physical']['boundary_clearance']=99.
 if field=='summary':native['max_absolute_force_error_n']=99.
 with pytest.raises(ValueError):study.run_case(a,native,audit_mode=True)


def make_partial(path):
 path.mkdir();sources=study.hashes();meta={'sources':sources,'versions':{'python':study.platform.python_version(),'numpy':study.np.__version__,'mujoco':study.mujoco.__version__},'classification':'SYNTHETIC_PARTIAL_FIXTURE'}
 assignments=[dict(a,metadata=meta) for a in study.plan()];a=assignments[0];r=study.run_case(a);file=path/(a['id']+'.json.gz');raw=study.write_output(file,r)
 with DevelopmentLedger.create(path/'assignments.jsonl',study=study.STUDY,assignments=assignments,record_events=True) as w:
  w.start(a['id']);w.event(a['id'],details={'phase':'ANALYSIS_INTENT','criteria_origin':'EXPLICIT_SYNTHETIC_DEVELOPMENT_NOT_APPROVED_OPERATIONAL_CRITERIA'})
  pos=[-2.,-2.,1.3];vel=[float(Q(a['model']['velocity'][0])),0.,0.]
  for frame in r['native']['frames']:
   w.event(a['id'],details={'phase':'NATIVE_TICK_INTENT','tick':frame['tick'],'position_before':pos,'velocity_before':vel,'measurement':frame['measurement'],'plant':frame['plant']})
   w.event(a['id'],details={'phase':'NATIVE_PHYSICS','tick':frame['tick'],'physical':frame['physical']})
   pos=frame['physical']['position'];vel=frame['physical']['velocity']
  w.complete(a['id'],status='COMPLETED',details={'output_file':file.name,'compressed_sha256':study.hashlib.sha256(file.read_bytes()).hexdigest(),'canonical_raw_sha256':raw,'summary':study.summary(r),'sources_after':sources})
 return path


def test_partial_output_audit_does_not_execute_native_steps(tmp_path,monkeypatch):
 p=make_partial(tmp_path/'partial')
 monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit stepped physics')))
 r=study.audit(p);assert r['ledger_state']=='INCOMPLETE' and r['counts']['ASSIGNED']==14
 assert all(a['summary'] is None for a in r['assignments'][1:])


def test_altered_output_file_rejected_even_with_valid_ledger(tmp_path):
 p=make_partial(tmp_path/'altered');f=p/(study.plan()[0]['id']+'.json.gz')
 raw=f.read_bytes();f.write_bytes(raw[:-3]+b'bad')
 with pytest.raises(ValueError):study.audit(p)


def test_analysis_failure_is_retained_as_error_not_favorable_missingness(tmp_path,monkeypatch):
 p=tmp_path/'failed'
 monkeypatch.setattr(study,'run_case',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('intentional analysis interruption')))
 with pytest.raises(RuntimeError,match='intentional analysis interruption'):study.run(p)
 r=study.audit(p);assert r['ledger_state']=='INCOMPLETE' and r['counts']=={'ASSIGNED':14,'STARTED':0,'COMPLETED':0,'ERROR':1}
 assert all(a['summary'] is None for a in r['assignments'])
 with pytest.raises(FileExistsError):study.run(p)


def test_native_failure_preserves_intent_and_error_without_inventing_completion(tmp_path,monkeypatch):
 p=tmp_path/'native_failed'
 monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(RuntimeError('intentional native interruption')))
 with pytest.raises(RuntimeError,match='intentional native interruption'):study.run(p)
 r=study.audit(p);assert r['ledger_state']=='INCOMPLETE' and r['counts']['ERROR']==1
 assert r['assignments'][0]['summary'] is None
 from scripts.research.streaming_ledger import LedgerStream
 with LedgerStream(p/'assignments.jsonl') as reader:
  events=[record['details']['phase'] for record in reader if record['kind']=='EVENT']
 assert events==['ANALYSIS_INTENT','NATIVE_TICK_INTENT']


def test_post_physics_sink_failure_remains_started_with_unknown_outcome(tmp_path,monkeypatch):
 from scripts.research.development_ledger import LedgerWriteError
 original=DevelopmentLedger.event;advance=PowerBrakeEnvironment.advance_prepared;calls=[]
 def event(self,assignment_id,*,details):
  if details['phase']=='NATIVE_PHYSICS':raise LedgerWriteError('intentional post-physics sink failure')
  return original(self,assignment_id,details=details)
 def step(self):calls.append(1);return advance(self)
 monkeypatch.setattr(DevelopmentLedger,'event',event);monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',step)
 p=tmp_path/'sink_failed'
 with pytest.raises(LedgerWriteError,match='post-physics sink failure'):study.run(p)
 assert len(calls)==1
 r=study.audit(p);assert r['counts']=={'ASSIGNED':14,'STARTED':1,'COMPLETED':0,'ERROR':0}
 assert r['assignments'][0]['summary'] is None
