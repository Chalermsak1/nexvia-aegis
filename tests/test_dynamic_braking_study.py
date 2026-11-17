from pathlib import Path
from dataclasses import replace
import copy
import pytest
from scripts.research import dynamic_braking_study as s
from scripts.research.development_ledger import DevelopmentLedger
from aegis.env.mujoco_power_brake import PowerBrakeEnvironment


@pytest.mark.parametrize('a',s.plan(),ids=lambda a:a['id'])
def test_fixed_horizon_measurements_and_readonly_reconstruction(a,monkeypatch):
 ev=[];r=s.execute(a,ev.append)
 monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit advanced physics')))
 assert s.audit_episode(a,ev,{'summary':r,'sources_after':s.hashes()},{'sources':s.hashes()})==r
 assert r['physics_steps']==160 and r['operational_authorization'] is False
 assert r['future_position_containment']=='NOT_ESTABLISHED'
 if a['case']=='nominal':
  assert r['first_any_inconsistency_tick'] is None
  assert r['final_truth_speed_clearance_dwell'] and r['final_measured_dwell_under_asserted_channels']
  assert not any(r['truth_channel_bound_violations'].values())
 if a['case']=='total_actuation_loss':
  assert r['contact_or_geometry_violation'] and r['contact_dynamics_steps_not_reconstructed']>0
  assert not r['final_truth_speed_clearance_dwell'] and not r['final_measured_dwell_under_asserted_channels']
 if a['case'] in ('sensor_loss','force_dropout','stale_state'):
  assert r['unknown_evidence_samples']>0 and not r['final_measured_dwell_under_asserted_channels']
 if a['case'] in ('force_spoof','force_acc_spoof'):
  assert r['first_any_inconsistency_tick'] is not None
 if a['case']=='all_feedback_ghost':
  assert r['false_measured_dwell_for_scoring']
  assert r['first_any_inconsistency_tick'] is None
  assert r['truth_channel_bound_violations']['state_velocity']>0
 if a['case']=='late_bus_loss':
  assert r['final_truth_speed_clearance_dwell']
  assert r['future_position_containment']=='NOT_ESTABLISHED'
 if a['case'] in ('delay_mismatch','ramp_mismatch') and a['arm']=='DELAYED_RAMPED':
  assert r['first_force_inconsistency_tick'] is not None


@pytest.mark.parametrize('field',['force','power','physics','packet','monitor','summary','source','missing'])
def test_semantic_mutation_cannot_survive_readonly_audit(field):
 a=s.plan()[0];ev=[];r=s.execute(a,ev.append);terminal={'summary':r,'sources_after':s.hashes()};meta={'sources':s.hashes()}
 if field=='force':ev[1]['plant']['actuator_force_pre_n'][0]+=1.
 if field=='power':ev[1]['plant']['gravity_powered']=False
 if field=='physics':ev[2]['velocity'][0]+=1.
 if field=='packet':ev[1]['state_packet']['source']='FABRICATED'
 if field=='monitor':ev[3]['monitor']['assessment']='APPROVED'
 if field=='summary':terminal['summary']['false_measured_dwell_for_scoring']=True
 if field=='source':terminal['sources_after']={}
 if field=='missing':ev.pop()
 with pytest.raises(ValueError):s.audit_episode(a,ev,terminal,meta)


def test_partial_and_error_assignments_remain_unevaluable(tmp_path,monkeypatch):
 def fail(self):raise RuntimeError('intentional dynamics interruption')
 monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',fail);p=tmp_path/'failed.jsonl'
 with pytest.raises(RuntimeError,match='intentional dynamics interruption'):s.run(p)
 r=s.audit(p)
 assert r['ledger_state']=='INCOMPLETE' and r['counts']=={'ASSIGNED':51,'STARTED':0,'COMPLETED':0,'ERROR':1}
 assert all(row['summary'] is None for row in r['assignments'])
 with pytest.raises(FileExistsError):s.run(p)


def test_sensor_interface_converts_numpy_to_strict_python_numeric_packets():
 a=s.plan()[0];env,sensor,monitor,actuator,current,first=s.setup(a)
 assert all(type(x) is float for x in current.position+current.velocity)
 assert monitor.command(current,tick=0)['status']=='MEASURED_BRAKE_REQUEST'
