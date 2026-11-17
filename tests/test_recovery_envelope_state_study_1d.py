from pathlib import Path
import copy,gzip,json
import pytest
from scripts.research import recovery_envelope_state_study_1d as study
from scripts.research.development_ledger import DevelopmentLedger,LedgerWriteError
from aegis.env.mujoco_power_brake import PowerBrakeEnvironment


@pytest.mark.parametrize('a',study.plan(),ids=lambda a:a['id'])
def test_stateful_designs_and_native_readonly_reconstruction(a,monkeypatch):
 r=study.run_case(a);s=study.summary(r)
 assert s['operational_authorization'] is False and s['future_position_containment']=='NOT_ESTABLISHED'
 if a['native']:
  monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit integrated physics')))
  assert study.run_case(a,r['native'],audit_mode=True)==r
 if a['id'] in ('pending_acceleration','mixed_pending_order'):
  assert s['reset_reference_containment'] and s['reset_reference_terminal_samples']
  assert s['finite_horizon_containment'] is False and s['point_witness_crosses_bound']
 if a['id']=='pending_braking':assert s['finite_horizon_containment'] and s['terminal_sample_condition']
 if a['id'].startswith('stale_') or a['id']=='missing_pending_records':
  assert s['conclusion']=='UNKNOWN_INPUT' and s['stateful_analysis_branches']==0
 if a['id']=='unasserted_actuator_state':assert s['conclusion']=='UNKNOWN_PHYSICAL_PREMISES'
 if a['id']=='unknown_measurement_evidence':assert s['conclusion']=='UNKNOWN_EVIDENCE'
 if a['id']=='expired_absolute_power_window':
  assert s['finite_horizon_containment'] is False and s['point_witness_crosses_bound']
  assert s['misused_absolute_budget_containment'] and s['misused_absolute_budget_terminal']


@pytest.mark.parametrize('field',['seed','plant','physical','measurement','missing'])
def test_invalid_native_evidence_is_rejected_without_native_steps(field,monkeypatch):
 a=study.plan()[1];r=study.run_case(a);native=copy.deepcopy(r['native'])
 monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit integrated physics')))
 if field=='seed':native['state_seed']['force']=['0','0']
 if field=='plant':native['frames'][0]['plant']['ctrl'][0]=99.
 if field=='physical':native['frames'][0]['physical']['position'][0]=99.
 if field=='measurement':native['frames'][0]['measurement']['velocity_m_s']=99.
 if field=='missing':native=None
 with pytest.raises(ValueError):study.run_case(a,native,audit_mode=True)


def test_analysis_error_retains_all_remaining_assignments(tmp_path,monkeypatch):
 monkeypatch.setattr(study,'run_case',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('intentional analysis failure')))
 p=tmp_path/'failed'
 with pytest.raises(RuntimeError):study.run(p)
 r=study.audit(p);assert r['counts']=={'ASSIGNED':12,'STARTED':0,'COMPLETED':0,'ERROR':1}
 assert all(a['summary'] is None for a in r['assignments'])
 with pytest.raises(FileExistsError):study.run(p)


def test_post_native_step_write_failure_keeps_outcome_unknown(tmp_path,monkeypatch):
 original=DevelopmentLedger.event;advance=PowerBrakeEnvironment.advance_prepared;calls=[]
 def event(self,assignment_id,*,details):
  if details['phase']=='NATIVE_PHYSICS':raise LedgerWriteError('intentional post-physics write failure')
  return original(self,assignment_id,details=details)
 def step(self):calls.append(1);return advance(self)
 monkeypatch.setattr(DevelopmentLedger,'event',event);monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',step)
 p=tmp_path/'post_step'
 with pytest.raises(LedgerWriteError):study.run(p)
 assert len(calls)==1
 r=study.audit(p);assert r['counts']=={'ASSIGNED':12,'STARTED':1,'COMPLETED':0,'ERROR':0}
 assert all(a['summary'] is None for a in r['assignments'])
