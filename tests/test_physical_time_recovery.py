from fractions import Fraction as Q
from itertools import product
import pytest
from aegis.development import physical_time_recovery as core
from scripts.research.fair_physical_execution_study import clock_map
from scripts.research.recovery_supervisor_study_1d import backup_model
from scripts.research.backup_parameter_uncertainty_study import family
from aegis.development.passive_backup_supervisor_1d import model,energy_box
from aegis.development.recovery_envelope_1d import point,internal


def inputs():
    return dict(backup=backup_model(),parameter_bounds=family('.1'),packet=dict(remote_time=1100,local_epoch='local-A',remote_epoch='sensor-A',frame='WORLD_X_SI',position=['0','0'],velocity=['.3','.3'],source_id='fixture'),clock_map=clock_map(),now_local=100,units_per_second='1000',max_state_age_seconds='.05',local_epoch='local-A',boot_id='boot-A',active_force_cap='1',handoff_delay_seconds=['0','.06'],monitor_seconds='.06',premises={k:True for k in core.PREMISES.split()},primary_healthy=True,dynamics_id=core.DYNAMICS_ID)


def test_fractional_mapped_age_composes_with_ideal_physical_certificate():
    r=core.assess(**inputs())
    assert r['status']=='CONDITIONAL_PHYSICAL_TIME_PLAN' and r['development_action']=='CONTINUE'
    assert list(map(Q,r['age_seconds']))==[Q(0),Q('.002')]
    assert r['conditional_continuous_containment'] and not r['hardware_validation'] and not r['dispatch']


def test_common_metric_matches_zoh_scalar_physics_with_switching_parameters_and_disturbance():
    b=backup_model();f=family('.1');r=core.certificate(b,f);s=model(b)
    assert r['conditional_continuous_containment']
    p=Q(0);v=Q('.5');h=Q('.02')
    for n in range(90):
        m=Q('.9') if n%2 else Q('1.1');k=Q('3.6') if n%3 else Q('4.4');c=Q('2.7') if n%5 else Q('3.3');w=Q('.01') if n%2 else Q('-.01')
        force=-k*p-c*v;assert abs(force)<=4;acc=(force+w)/m
        for i in range(11):
            t=h*i/10;px=p+t*v+t*t*acc/2;assert Q('-.5')<=px<=Q('.32')
        p,v=p+h*v+h*h*acc/2,v+h*acc
        assert energy_box(s,point(p),point(v))<=s['level']


def test_fractional_time_transport_contains_independent_polynomials():
    p=internal(Q('-.1'),Q('.1'));v=internal(Q('-.3'),Q('.4'));A=Q('1.2');lo=Q('1/300');hi=Q('1/17');pn,vn=core.transport(p,v,A,lo,hi)
    for px,vx,a in product((p.lo,p.hi),(v.lo,v.hi),(-A,A)):
        for j in range(31):
            t=lo+(hi-lo)*j/30;assert pn.contains(px+t*vx+t*t*a/2) and vn.contains(vx+t*a)


@pytest.mark.parametrize('x',[Q(0),Q(2),Q('1/3'),Q('999999/13')])
def test_square_root_bound_is_exactly_outward(x):
    r=core.sqrt_upper(x);assert r*r>=x and (r-Q(1,10**12))**2<x if r else x==0


@pytest.mark.parametrize('key',core.PREMISES.split())
def test_each_clock_physical_and_trigger_assertion_is_required(key):
    a=inputs();a['premises'][key]=False;assert not core.assess(**a)['conditional_continuous_containment']


@pytest.mark.parametrize('field,value',[('now_local',99),('units_per_second','0'),('dynamics_id','SEMI_IMPLICIT_WORLD_X_SI_V1'),('local_epoch','reset'),('primary_healthy',1)])
def test_future_wrong_epoch_model_and_invalid_inputs_withhold(field,value):
    a=inputs();a[field]=value;r=core.assess(**a);assert r['development_action'] is None


def test_wrong_remote_epoch_and_old_clock_map_are_not_bridged():
    a=inputs();a['packet']['remote_epoch']='new';assert core.assess(**a)['development_action'] is None
    a=inputs();a['now_local']=200;assert core.assess(**a)['development_action'] is None


def test_primary_unavailable_or_long_monitor_uses_supported_backup_only():
    a=inputs();a['primary_healthy']=False;assert core.assess(**a)['development_action']=='HANDOFF'
    a=inputs();a['monitor_seconds']='.4';assert core.assess(**a)['development_action']=='HANDOFF'
    a=inputs();a['packet']['velocity']=['1.5','1.5'];assert core.assess(**a)['development_action'] is None


def test_sample_invariance_does_not_bypass_physical_segment_projection():
    b=backup_model();b['safe_position']=['-.3','.3'];r=core.certificate(b,family('.1'))
    assert not r['conditional_continuous_containment'] and not r['checks']['all_segment_position_projection']


@pytest.mark.parametrize('mass,stiffness,damping',[('.9','3.6','2.7'),('1','4','3'),('1.1','4.4','3.3')])
def test_native_rk4_held_force_matches_physical_zoh_endpoints(mass,stiffness,damping,tmp_path):
    import json,mujoco
    from aegis.env.mujoco_power_brake import PowerBrakeEnvironment
    m,k,c=map(float,(mass,stiffness,damping));env=PowerBrakeEnvironment(actual_mass_kg=m,brake_cap_per_axis_n=1.)
    env.reset_development(.5);env.model.opt.integrator=mujoco.mjtIntegrator.mjINT_RK4
    p=0.;v=.5;frames=[]
    for tick in range(50):
        force=float(max(-4.,min(4.,-k*p-c*v)));acc=(force+.01)/m
        intent=env.prepare_powered_force([0.,0.,0.],brake_powered=False,gravity_powered=True,disturbance=[force+.01,0.,9.81*(m-1.)])
        actual=env.advance_prepared();pn=p+.02*v+.0002*acc;vn=v+.02*acc
        assert abs(actual['position'][0]+2.-pn)<1e-10 and abs(actual['velocity'][0]-vn)<1e-10
        assert abs(actual['position'][2]-1.3)<1e-10 and not actual['contact_floor'] and not actual['contact_obstacle']
        frames.append(dict(tick=tick,position_before=p,velocity_before=v,held_force=force,intent=intent,actual=actual,analytic_position=pn,analytic_velocity=vn))
        p,v=actual['position'][0]+2.,actual['velocity'][0]
    (tmp_path/'rk4_physical_frames.json').write_text(json.dumps(dict(runtime=env.runtime_record(),integrator_override='EXPLICIT_RK4_AFTER_MODEL_BUILD',ideal_gravity_support=True,frames=frames)))
