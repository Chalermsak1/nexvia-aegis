from copy import deepcopy
import pytest
from scripts.research import physical_reference_study as study
from scripts.research.development_ledger import DevelopmentLedger, LedgerWriteError, inspect


@pytest.fixture(scope='module')
def complete(tmp_path_factory):
 path=tmp_path_factory.mktemp('physical_reference')/'all.jsonl'
 return path,study.run(path)


def rows(complete,case,arm):return [a['summary'] for a in complete[1]['assignments'] if a['id'].endswith(':'+case+':'+arm)]


def test_plan_horizon_and_matched_noise(complete):
 r=complete[1];assert len(study.plan())==126 and r['counts']['COMPLETED']==126 and r['ledger_state']=='FINALIZED'
 assert len(r['matched_triples'])==42 and all(t['status']=='MATCHED_RESET_RUNTIME_NOISE_ONLY' for t in r['matched_triples'])
 assert all(t['summary']['physics_steps']==60 for t in r['assignments'])


def test_nominal_references_and_feedback_have_no_inconsistency(complete):
 for arm in study.ARMS:
  for r in rows(complete,'nominal',arm):
   assert r['first_state_failure_tick'] is None and r['first_feedback_failure_tick'] is None
   assert r['reference_velocity_ball_violations']==0 and r['reference_evaluable_intervals']==60
   assert r['contact_samples']==0


def test_sudden_shared_reversal_detected_by_reference_before_wrong_command(complete):
 assert all(r['positive_command_power_ticks']>0 for r in rows(complete,'shared_reverse','WITNESS_BASELINE'))
 for arm in ('REFERENCE_GUARD','REFERENCE_FEEDBACK'):
  assert all(r['first_fallback_request_tick']==6 and r['positive_command_power_ticks']==0 for r in rows(complete,'shared_reverse',arm))


def test_initial_frame_error_needs_force_acceleration_relation(complete):
 base=rows(complete,'initial_frame_flip','REFERENCE_GUARD');full=rows(complete,'initial_frame_flip','REFERENCE_FEEDBACK')
 assert all(r['positive_command_power_ticks']>1 for r in base)
 assert all(r['first_feedback_failure_tick']==1 and r['first_fallback_request_tick']==1 for r in full)
 assert all(r['positive_command_power_ticks']==1 for r in full)  # Cannot retroactively prevent first interval.


def test_coherent_model_frame_and_ghost_spoofing_remain_counterexamples(complete):
 joint=rows(complete,'joint_frame_model_spoof','REFERENCE_FEEDBACK')
 assert all(r['first_state_failure_tick'] is None and r['first_feedback_failure_tick'] is None for r in joint)
 assert all(r['first_fallback_request_tick'] is None and r['positive_command_power_ticks']>0 and r['reference_velocity_ball_violations']>0 for r in joint)
 ghost=rows(complete,'all_feedback_ghost','REFERENCE_FEEDBACK')
 assert all(r['first_state_failure_tick'] is None and r['first_feedback_failure_tick'] is None for r in ghost)
 assert all(r['force_sensor_bound_violations']>0 for r in ghost)
 # All three short-horizon ghost trajectories remain inside a wide velocity ball.
 # The violated force-sensor assumption still makes actuator consistency misleading.
 assert all(r['reference_velocity_ball_violations']==0 for r in ghost)
 assert all(r['reference_evaluable_intervals']==60 for r in ghost)


def test_failed_brake_and_forged_feedback_are_detected(complete):
 loss=rows(complete,'brake_loss','REFERENCE_FEEDBACK')
 assert any(r['brake_force_inconsistent_intervals']>0 for r in loss)
 assert any(r['first_feedback_failure_tick'] is None and r['uninformative_brake_intervals']>0 for r in loss)
 assert all(r['force_acceleration_inconsistent_intervals']>0 for r in rows(complete,'force_feedback_spoof','REFERENCE_FEEDBACK'))
 assert all(r['first_feedback_failure_tick'] is not None for r in rows(complete,'force_feedback_spoof','REFERENCE_FEEDBACK'))


def test_partial_spoof_and_reference_bias_raise_continuing_diagnostics(complete):
 partial=rows(complete,'imu_force_spoof','REFERENCE_FEEDBACK')
 assert any(r['first_state_failure_tick'] is not None for r in partial)
 assert any(r['first_state_failure_tick'] is None and r['first_feedback_failure_tick'] is None for r in partial)
 assert all(r['first_feedback_failure_tick'] is not None and r['first_feedback_failure_tick']>=7 for r in rows(complete,'reference_bias','REFERENCE_FEEDBACK'))


def test_missing_reference_is_not_a_favorable_coverage_result(complete):
 for arm in study.ARMS:
  for r in rows(complete,'reference_dropout',arm):
   assert r['reference_evaluable_intervals']==6 and r['reference_unevaluable_intervals']==54
   assert r['acceleration_sensor_missing_intervals']==54 and r['unsupported_feedback_intervals']>=54
 for r in rows(complete,'reference_dropout','REFERENCE_FEEDBACK'):
  assert r['first_fallback_request_tick']<=7


def test_contact_is_not_reclassified_as_success(complete):
 assert all(r['contact_samples']>0 and r['free_motion_evaluation']=='UNEVALUABLE_CONTACT' for r in rows(complete,'mass_gravity_offset','REFERENCE_FEEDBACK'))


def test_actual_reanalysis_and_new_output_only(complete):
 path,result=complete;assert study.audit(path)==result
 before=path.read_bytes()
 with pytest.raises(FileExistsError):study.run(path)
 assert path.read_bytes()==before


@pytest.fixture(scope='module')
def episode(complete):
 log=inspect(complete[0]);a=next(v for v in log['records'][0]['assignments'] if v['id']=='v0:brake_loss:REFERENCE_FEEDBACK')
 ev=[r['details'] for r in log['records'] if r['kind']=='EVENT' and r['id']==a['id']]
 t=next(r['details'] for r in log['records'] if r['kind']=='TERMINAL' and r['id']==a['id'])
 return a,ev,t


@pytest.mark.parametrize('defect',['anchor','reference','force_reading','accel_reading','interval','feedback_result','brake_gain','geometry','impulse','source','summary','missing_sensor','command_port'])
def test_reader_rejects_edited_reference_evidence(episode,defect):
 a,original,terminal=episode;ev,t=deepcopy(original),deepcopy(terminal)
 tick,p,s=ev[1:4]
 if defect=='anchor':ev[0]['reference_anchor']['velocity'][0]+=.1
 elif defect=='reference':tick['reference_at_interval_start']['velocity_error_m_s']+=1
 elif defect=='force_reading':s['measurements']['force']['value'][0]+=.1
 elif defect=='accel_reading':s['measurements']['acceleration']['value'][0]+=.1
 elif defect=='interval':s['measurements']['acceleration']['start_tick']+=1
 elif defect=='feedback_result':s['monitor']['feedback']['force_acceleration']['status']='VERIFIED'
 elif defect=='brake_gain':tick['plant']['native_gain'][0]+=1
 elif defect=='geometry':p['boundary_clearance']+=1
 elif defect=='impulse':p['velocity'][0]+=.1
 elif defect=='source':t['sources_after']={}
 elif defect=='summary':t['summary']['reference_evaluable_intervals']+=1
 elif defect=='missing_sensor':ev.pop(3)
 else:s['measurements']['reported_command_for_monitor'][0]+=.1
 with pytest.raises(ValueError):study.audit_episode(a,ev,t,a['metadata'])


def test_valid_rehashed_false_feedback_verdict_is_rejected(episode,tmp_path):
 a,ev,t=episode;ev=deepcopy(ev)
 bad=next(v for v in ev if v['type']=='SENSORS' and v['monitor']['feedback']['brake_force']['status']=='INCONSISTENT')
 bad['monitor']['feedback']['brake_force']['status']='MODEL_CONSISTENT_FORCE'
 path=tmp_path/'false_feedback.jsonl'
 with DevelopmentLedger.create(path,study=study.STUDY,assignments=[dict(p,metadata=a['metadata']) for p in study.plan()],record_events=True) as w:
  w.start(a['id'])
  for e in ev:w.event(a['id'],details=e)
  w.complete(a['id'],status='COMPLETED',details=t)
 with pytest.raises(ValueError):study.audit(path)


def test_sink_failure_preserves_unstarted_and_no_integrated_tick(tmp_path,monkeypatch):
 path=tmp_path/'sink_failure.jsonl';original=DevelopmentLedger.event
 def fail(self,identifier,*,details):
  if details['type']=='TICK':raise LedgerWriteError('synthetic')
  return original(self,identifier,details=details)
 monkeypatch.setattr(DevelopmentLedger,'event',fail)
 with pytest.raises(LedgerWriteError):study.run(path)
 r=study.audit(path);assert r['counts']=={'ASSIGNED':125,'STARTED':1,'COMPLETED':0,'ERROR':0}
 assert [v['details']['type'] for v in inspect(path)['records'] if v['kind']=='EVENT']==['RESET']


def test_runtime_failure_preserves_error_and_all_remaining_work(tmp_path,monkeypatch):
 path=tmp_path/'sim_failure.jsonl'
 def fail(a,emit):raise RuntimeError('synthetic')
 monkeypatch.setattr(study,'run_episode',fail)
 with pytest.raises(RuntimeError):study.run(path)
 r=study.audit(path);assert r['counts']=={'ASSIGNED':125,'STARTED':0,'COMPLETED':0,'ERROR':1}
 assert all(t['status']=='UNEVALUABLE_INCOMPLETE' for t in r['matched_triples'])


def test_sensor_sink_failure_retains_already_integrated_physics(tmp_path,monkeypatch):
 path=tmp_path/'sensor_sink_failure.jsonl';original=DevelopmentLedger.event
 def fail(self,identifier,*,details):
  if details['type']=='SENSORS':raise LedgerWriteError('synthetic post-physics sensor sink failure')
  return original(self,identifier,details=details)
 monkeypatch.setattr(DevelopmentLedger,'event',fail)
 with pytest.raises(LedgerWriteError):study.run(path)
 r=study.audit(path)
 assert r['counts']=={'ASSIGNED':125,'STARTED':1,'COMPLETED':0,'ERROR':0}
 assert r['assignments'][0]['summary'] is None
 assert [v['details']['type'] for v in inspect(path)['records'] if v['kind']=='EVENT']==['RESET','TICK','PHYSICS']
