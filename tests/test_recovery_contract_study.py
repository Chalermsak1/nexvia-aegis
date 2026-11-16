import copy
from pathlib import Path
import pytest
from scripts.research import recovery_contract_study as study
from scripts.research.development_ledger import DevelopmentLedger,_entry,_encode,ZERO_HASH
from aegis.env.mujoco_lease_brake import ForceLimitedBrakeEnvironment


@pytest.mark.parametrize('a',study.plan(),ids=lambda a:a['id'])
def test_native_design_and_full_fixed_horizon_reconstruct(a,monkeypatch):
 events=[];summary=study.execute(a,events.append)
 sources=study.hashes();terminal={'summary':summary,'sources_after':sources};meta={'sources':sources}
 monkeypatch.setattr(ForceLimitedBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit stepped physics')))
 assert study.audit_episode(a,events,terminal,meta)==summary
 if 'declined' in a['case']:
  assert summary['physics_steps']==0 and summary['terminal_speed_band_and_dwell_observed'] is None
 else:
  assert summary['physics_steps']==events[0]['design']['required_total_steps']
  assert summary['terminal_dwell_samples']==26
  if a['case'] in ('over_budget_probe','brake_loss','late_brake_loss'):
   assert summary['model_evaluation']=='UNEVALUABLE_PREMISE_VIOLATION'
   assert summary['path_exceeds_design_bound'] is None
  else:
   assert summary['model_evaluation']=='CONDITIONAL_SAMPLED_COMPARISON'
   assert summary['path_exceeds_design_bound'] is False and summary['energy_exceeds_design_bound'] is False
  if a['case']=='brake_loss':assert summary['terminal_speed_band_and_dwell_observed'] is False
  elif a['case']!='over_budget_probe':assert summary['terminal_speed_band_and_dwell_observed'] is True
  if a['case']=='late_brake_loss':
   assert summary['terminal_speed_band_and_dwell_observed'] is True
   assert summary['brake_availability_violated'] is True
   assert summary['empirical_post_horizon_containment']=='NOT_ESTABLISHED_BY_FINITE_TRAJECTORY'
 assert summary['operational_authorization'] is False


def partial(path):
 meta={'sources':study.hashes(),'classification':'SYNTHETIC_FIXTURE'}
 assignments=[dict(a,metadata=meta) for a in study.plan()]
 with DevelopmentLedger.create(path,study=study.STUDY,assignments=assignments,record_events=True) as w:
  a=assignments[0];w.start(a['id']);summary=study.execute(a,lambda e:w.event(a['id'],details=e))
  w.complete(a['id'],status='COMPLETED',details={'summary':summary,'sources_after':meta['sources']})
 return study.audit(path)


def test_partial_retains_all_unexecuted_and_never_grants(tmp_path):
 result=partial(tmp_path/'partial.jsonl')
 assert result['ledger_state']=='INCOMPLETE' and result['counts']['ASSIGNED']==38
 assert all(a['summary'] is None for a in result['assignments'][1:])
 assert result['assignments'][0]['summary']['operational_authorization'] is False


@pytest.mark.parametrize('change',['terminal','tick','physics','runtime','sources','missing_event'])
def test_rehashed_or_missing_semantic_evidence_is_rejected(change):
 a=study.plan()[0];events=[];summary=study.execute(a,events.append);sources=study.hashes()
 terminal={'summary':summary,'sources_after':sources};meta={'sources':sources}
 if change=='terminal':terminal['summary']['terminal_speed_band_and_dwell_observed']=False
 if change=='tick':events[1]['actual_gain']=999.
 if change=='physics':events[2]['velocity'][0]+=1.
 if change=='runtime':events[0]['runtime']['mass_kg']=2.
 if change=='sources':terminal['sources_after']={}
 if change=='missing_event':events.pop()
 with pytest.raises(ValueError):study.audit_episode(a,events,terminal,meta)


def test_failure_preserves_error_and_unstarted_assignments(tmp_path,monkeypatch):
 def fail(self):raise RuntimeError('synthetic physics interruption')
 monkeypatch.setattr(ForceLimitedBrakeEnvironment,'advance_prepared',fail)
 p=tmp_path/'failed.jsonl'
 with pytest.raises(RuntimeError,match='synthetic physics interruption'):study.run(p)
 r=study.audit(p)
 assert r['ledger_state']=='INCOMPLETE' and r['counts']['ERROR']==1 and r['counts']['ASSIGNED']==38
 assert all(a['summary'] is None for a in r['assignments'])
 with pytest.raises(FileExistsError):study.run(p)
