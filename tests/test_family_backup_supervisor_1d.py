from copy import deepcopy
from fractions import Fraction as Q
from itertools import product
import json
import pytest
from aegis.development import family_backup_supervisor_1d as core
from aegis.development.passive_backup_supervisor_1d import model,energy_box,bridge as old_bridge
from aegis.development.recovery_envelope_1d import point,internal
from scripts.research import family_recovery_composition_study as study
from scripts.research.backup_parameter_uncertainty_study import family
from scripts.research import recovery_supervisor_study_1d as old


def test_singleton_integrates_existing_primary_and_readiness():
    r=study.run_case(dict(id='singleton_primary'))['result']
    assert r['development_action']=='CONTINUE_WITH_FAMILY_RESERVE'
    assert not r['dispatch'] and not r['operational_authorization'] and not r['intersample_containment']


def test_family_cannot_reuse_a_primary_that_only_covers_nominal_mass():
    r=study.run_case(dict(id='insufficient_primary_mass'))['result']
    assert r['development_action'] is None and r['reason']=='PRIMARY_FAMILY_PHYSICAL_COVERAGE_NOT_ESTABLISHED'


def test_smallest_mass_changes_future_reserve_before_current_handoff_is_lost():
    args=study.inputs();r=core.assess(**args);s=model(args['backup'])
    old=old_bridge(s,point(Q(0)),point(Q('.5')),6,Q(1),Q('.01'))
    assert old[-1]['in_backup_set']
    assert r['current_handoff_supported'] and not r['continued_operation_reserve_supported']
    assert r['development_action']=='HANDOFF_TO_FAMILY_BACKUP'
    # Independent scalar witness under admitted carried/queued force cap.
    p=Q(0);v=Q('.5')
    for _ in range(6):v+=Q('.02')*Q('1.01')/Q('.85');p+=Q('.02')*v
    assert energy_box(s,point(p),point(v))>s['level']


def test_bridge_encloses_switching_mass_force_and_disturbance_extremes():
    args=study.inputs();s=model(args['backup']);mass=internal(Q('.85'),Q('1.15'))
    p=internal(Q('-.01'),Q('.01'));v=internal(Q('.45'),Q('.55'))
    rows=core.bridge(s,mass,p,v,3,Q(1),Q('.01'))
    choices=list(product((mass.lo,mass.hi),(Q(-1),Q(1)),(Q('-.01'),Q('.01'))))
    for p0,v0 in product((p.lo,p.hi),(v.lo,v.hi)):
        for history in product(choices,repeat=3):
            px,vx=p0,v0
            for n,(m,f,w) in enumerate(history,1):
                vx+=s['dt']*(f+w)/m;px+=s['dt']*vx
                assert Q(rows[n]['position'][0])<=px<=Q(rows[n]['position'][1])
                assert Q(rows[n]['velocity'][0])<=vx<=Q(rows[n]['velocity'][1])
                assert energy_box(s,point(px),point(vx))<=Q(rows[n]['lyapunov_upper'])


def test_all_admissible_discrete_ages_are_transport_hulled():
    a=study.inputs();a['state']['epoch_tick_bounds']=[98,100];r=core.assess(**a)
    assert r['admissible_state_ages']==[0,1,2]
    assert list(map(Q,r['transported_velocity']))==[Q('.5')-2*Q('.02')*Q('1.01')/Q('.85'),Q('.5')+2*Q('.02')*Q('1.01')/Q('.85')]
    assert r['transport_hull_relaxes_time_state_correlation']


@pytest.mark.parametrize('key',core.PREMISES.split())
def test_each_physical_parameter_and_clock_premise_is_required(key):
    a=study.inputs();a['premises'][key]=False;r=core.assess(**a)
    assert r['development_action'] is None and not r['conditional_future_sampled_containment']


@pytest.mark.parametrize('name',['stale_epoch','future_epoch','clock_reset','boot_reset','wrong_frame','unsupported_model','family_not_certified','unknown_state','outside_region','long_handoff','uncertain_epoch_outside_budget','contradictory_primary','wide_state'])
def test_negative_integrated_designs_never_get_a_safe_plan(name):
    r=study.run_case(dict(id=name))['result']
    assert r['development_action'] is None and not r['conditional_future_sampled_containment']


@pytest.mark.parametrize('field,value',[('assessment_tick',True),('monitor_ticks',0),('monitor_ticks',17),('max_state_age_ticks',True),('handoff_delay_ticks',[0,17]),('handoff_delay_ticks',[3,1]),('active_force_cap','-1'),('environment_force','.02'),('state',None),('parameter_bounds',None)])
def test_malformed_contracts_do_not_create_actions(field,value):
    a=study.inputs();a[field]=value;r=core.assess(**a)
    assert r['development_action'] is None and not r['conditional_future_sampled_containment']


def test_post_backup_step_can_detect_missing_mechanism_and_missing_evidence():
    a=study.inputs();before=dict(position=['0','0'],velocity=['.5','.5'])
    compatible=dict(position=['.0094','.0094'],velocity=['.47','.47'])
    absent=dict(position=['.01','.01'],velocity=['.5','.5'])
    assert core.check_step(a['backup'],a['parameter_bounds'],before,compatible,dynamics_id=core.DYNAMICS_ID)['status']=='COMPATIBLE_UNDER_ASSERTED_FAMILY'
    assert core.check_step(a['backup'],a['parameter_bounds'],before,absent,dynamics_id=core.DYNAMICS_ID)['status']=='FAMILY_MODEL_OR_EVIDENCE_CONTRADICTION'
    assert core.check_step(a['backup'],a['parameter_bounds'],before,None,dynamics_id=core.DYNAMICS_ID)['status']=='UNKNOWN_FAMILY_OBSERVATION'


@pytest.mark.parametrize('mass,stiffness,damping',[('.85','3.4','2.55'),('1','4','3'),('1.15','4.6','3.45')])
def test_native_family_steps_with_explicit_supported_stage_force(mass,stiffness,damping,tmp_path):
    import numpy as np
    from aegis.env.mujoco_power_brake import PowerBrakeEnvironment
    m,k,c=map(float,(mass,stiffness,damping));env=PowerBrakeEnvironment(actual_mass_kg=m,brake_cap_per_axis_n=1.);env.reset_development(.5)
    pos=0.;vel=.5;rows=[];a=study.inputs()
    for tick in range(50):
        before=old.observation(pos,vel);force=float(max(-4.,min(4.,-k*pos-c*vel)))
        # Explicit simulated support mg, not a flying total-power-loss model.
        intent=env.prepare_powered_force([0.,0.,0.],brake_powered=False,gravity_powered=True,disturbance=[force+.01,0.,9.81*(m-1.)])
        observed=env.advance_prepared();vn=vel+.02*(force+.01)/m;pn=pos+.02*vn
        assert abs(observed['position'][0]+2.-pn)<1e-10 and abs(observed['velocity'][0]-vn)<1e-10
        assert abs(observed['position'][2]-1.3)<1e-10
        assert not observed['contact_floor'] and not observed['contact_obstacle']
        after=old.observation(observed['position'][0]+2.,observed['velocity'][0])
        checked=core.check_step(a['backup'],a['parameter_bounds'],before,after,dynamics_id=core.DYNAMICS_ID)
        rows.append(dict(tick=tick,intent=intent,physical=observed,check=checked))
        assert checked['status']=='COMPATIBLE_UNDER_ASSERTED_FAMILY'
        pos,vel=observed['position'][0]+2.,observed['velocity'][0]
    (tmp_path/'native_family_frames.json').write_text(json.dumps(dict(runtime=env.runtime_record(),support='EXPLICIT_IDEAL_MG_NOT_HARDWARE',frames=rows)))


def test_all_inputs_remain_unchanged():
    a=study.inputs();saved=deepcopy(a);core.assess(**a);assert a==saved


@pytest.mark.parametrize('name,action',[('family_primary','CONTINUE_WITH_FAMILY_RESERVE'),('family_primary_long_monitor','HANDOFF_TO_FAMILY_BACKUP'),('family_deadline_withheld','HANDOFF_TO_FAMILY_BACKUP')])
def test_genuine_interval_mass_primary_integration(name,action):
    r=study.run_case(dict(id=name))['result']
    assert r['development_action']==action
    if name!='family_deadline_withheld':assert r['primary_decision']['status']=='DEVELOPMENT_RECOVERY_CANDIDATE_ONLY'
    else:assert r['primary_decision']['reason']=='DEADLINE_OR_RESULT_BINDING_FAILED'
