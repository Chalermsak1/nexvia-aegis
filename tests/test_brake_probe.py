from copy import deepcopy
import pytest
from aegis.development.physical_reference import KinematicReference
from aegis.development.probe_window import brake_probe_window
from scripts.research import brake_probe_study as study
from scripts.research.development_ledger import DevelopmentLedger,LedgerWriteError,inspect


def setup():
 env,rng,ref,design=study.setup(study.plan()[0]);return ref.snapshot(),env.runtime_record()


def test_design_bound_and_explicit_non_authorization():
 ref,geometry=setup();d=brake_probe_window(ref,geometry)
 assert d['design_status']=='WITHIN_ASSERTED_SAMPLED_WINDOW' and d['window_ticks']==6
 assert 0<d['sampled_path_upper_m']<d['clearance_lower_m']
 assert d['operational_authorization'] is False and d['post_window_recoverability_established'] is False


def test_uncertainty_and_clearance_conservatism():
 ref,geometry=setup();ref['position']=[-2.79,-2.,1.3]
 assert brake_probe_window(ref,geometry)['design_status']=='DECLINED_CLEARANCE_BOUND'
 ref['position_error_m']=1.
 assert brake_probe_window(ref,geometry)['design_status']=='DECLINED_CLEARANCE_BOUND'
 ref['status']='UNSUPPORTED'
 assert brake_probe_window(ref,geometry)['design_status']=='UNSUPPORTED'


@pytest.mark.parametrize('kw',[dict(delay_ticks=True),dict(pulse_ticks=0),dict(feedback_ticks=-1),dict(cap_per_axis_n=0.),dict(mass_lower_kg=0.)])
def test_invalid_probe_contract_never_grants_design(kw):
 ref,geometry=setup();assert brake_probe_window(ref,geometry,**kw)['design_status']=='UNSUPPORTED'


@pytest.fixture(scope='module')
def complete(tmp_path_factory):
 p=tmp_path_factory.mktemp('brake_probe')/'all.jsonl';return p,study.run(p)


def rows(complete,case):return [a['summary'] for a in complete[1]['assignments'] if a['id'].endswith(':'+case)]


def test_probe_horizon_and_declined_designs(complete):
 r=complete[1];assert r['counts']['COMPLETED']==21 and r['ledger_state']=='FINALIZED'
 assert sum(a['summary']['physics_steps'] for a in r['assignments'])==108
 assert all(a['physics_steps']==0 and a['classification']=='NO_PROBE_WINDOW_DECLINED' for a in rows(complete,'near_wall_design'))


def test_probe_resolves_missing_force_when_excitation_is_informative(complete):
 assert all(r['brake_inconsistent_pulse_samples']==2 for r in rows(complete,'brake_absent'))
 assert all(r['cross_inconsistent_samples']>=2 for r in rows(complete,'force_feedback_spoof'))
 assert all(r['brake_inconsistent_pulse_samples']==0 and r['cross_inconsistent_samples']==0 for r in rows(complete,'nominal'))


def test_coherent_spoof_remains_a_counterexample_and_motion_is_not_rest(complete):
 for r in rows(complete,'coherent_spoof'):
  assert r['brake_inconsistent_pulse_samples']==0 and r['cross_inconsistent_samples']==0
  assert r['force_sensor_bound_violations']>0 and r['residual_speed_m_s']>0
  assert r['operational_authorization'] is False


def test_wrong_sign_and_force_budget_violation_are_retained(complete):
 assert all(r['brake_inconsistent_pulse_samples']==2 for r in rows(complete,'wrong_sign'))
 assert all(r['force_budget_violated'] and r['window_bound_evaluation']=='UNEVALUABLE_FORCE_BUDGET' and r['path_exceeds_design_bound'] is None for r in rows(complete,'force_over_budget'))


def test_readonly_audit_never_advances_physics(complete,monkeypatch):
 def fail(*args,**kwargs):raise AssertionError('reader advanced physics')
 monkeypatch.setattr(study.ForceLimitedBrakeEnvironment,'advance_prepared',fail)
 assert study.audit(complete[0])==complete[1]


def test_new_output_only(complete):
 before=complete[0].read_bytes()
 with pytest.raises(FileExistsError):study.run(complete[0])
 assert complete[0].read_bytes()==before


def test_rehashed_false_force_observation_rejected(complete,tmp_path):
 log=inspect(complete[0]);records=deepcopy(log['records']);assignments=records[0]['assignments']
 target=next(r for r in records if r['kind']=='EVENT' and r['details']['type']=='OBSERVATION')
 target['details']['force']['value'][0]+=1
 path=tmp_path/'false_force.jsonl'
 with DevelopmentLedger.create(path,study=study.STUDY,assignments=assignments,record_events=True) as w:
  for r in records[1:]:
   if r['kind']=='START':w.start(r['id'])
   elif r['kind']=='EVENT':w.event(r['id'],details=r['details'])
   elif r['kind']=='TERMINAL':w.complete(r['id'],status=r['status'],details=r['details'])
   else:w.finalize()
 with pytest.raises(ValueError):study.audit(path)


def test_probe_sink_failure_retains_partial_assignment(tmp_path,monkeypatch):
 original=DevelopmentLedger.event;p=tmp_path/'sink.jsonl'
 def fail(self,identifier,*,details):
  if details['type']=='TICK':raise LedgerWriteError('synthetic')
  return original(self,identifier,details=details)
 monkeypatch.setattr(DevelopmentLedger,'event',fail)
 with pytest.raises(LedgerWriteError):study.run(p)
 r=study.audit(p);assert r['counts']=={'ASSIGNED':20,'STARTED':1,'COMPLETED':0,'ERROR':0}
