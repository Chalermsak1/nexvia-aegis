"""Counterexamples and independent bounded-trajectory checks; no Holdout."""
import copy
from fractions import Fraction as Q
from itertools import product
import pytest

from aegis.development.recovery_feedback_state_1d import prepare_feedback, assess_feedback


def model():
    return dict(dt='.02', position=['0','0'], velocity=['.5','.5'],
                mass=['1','1'], gain=['2','2'], cap=['1','1'], slew=['4','4'],
                disturbance='0', measurement_error='0', delay_ticks=[3,3],
                power_cut_ticks=[160,160], horizon=140, safe_position=['-.5','.32'],
                terminal_velocity=['-.05','.05'], terminal_samples=25)


def flags():
    return dict(evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS',
                measurement_bounds_asserted=True, actuator_model_asserted=True,
                power_bounds_asserted=True, command_records_asserted=True,
                clock_bounds_asserted=True)


def packet(tick=100, **values):
    return dict(sample_tick=tick, received_tick=100, clock_id='synthetic-clock',
                frame='WORLD_X_SI', source_id='synthetic-sensor', **values)


def command(tick, value='0'):
    return dict(enqueue_tick=tick, received_tick=100, clock_id='synthetic-clock',
                frame='WORLD_X_SI', source_id='synthetic-ack', effective_target=[value,value])


def evidence():
    return dict(assessment_tick=100, clock_id='synthetic-clock', max_state_age_ticks=8,
                state_observations=[packet(position=['0','0'],velocity=['.5','.5'])],
                force_observations=[packet(force=['0','0'])],
                commands=[command(t) for t in (97,98,99)],
                power=dict(absolute_cut_ticks=[260,260], received_tick=100,
                           clock_id='synthetic-clock', source_id='synthetic-power'))


def prepare(e=None,m=None,**kw):
    f=flags();f.update(kw)
    return prepare_feedback(model() if m is None else m, evidence() if e is None else e, **f)


def test_fresh_complete_feedback_reproduces_state_model_without_truth_inputs():
    from aegis.development.recovery_envelope_state_1d import assess_state
    e=evidence();before=copy.deepcopy(e);m=model();result=assess_feedback(m,e,**flags())
    prepared=result['preparation']
    assert prepared['status']=='READY_CONDITIONAL_INPUTS'
    assert prepared['model']['power_cut_ticks']==[140,140]  # same finite dynamics
    expected=assess_state(prepared['model'],prepared['snapshot'],
                         **{k:v for k,v in flags().items() if k not in ('clock_bounds_asserted','command_records_asserted')},
                         actuator_state_bounds_asserted=True)
    assert result['assessment']==expected
    assert result['assessment']['finite_horizon_containment'] is True
    assert e==before and m==model()
    assert result['action'] is None and not result['operational_authorization']


def test_acknowledged_acceleration_is_not_replaced_by_reset_queue():
    e=evidence();e['commands']=[command(t,'.8') for t in (97,98,99)]
    e['force_observations']=[packet(force=['.8','.8'])]
    result=assess_feedback(model(),e,**flags())
    assert result['assessment']['finite_horizon_containment'] is False
    final=result['assessment']['branches'][0]['history'][-1]['position']
    assert Q(final[0])==Q(final[1]) and Q(final[0])>Q('.49')


def test_missing_acknowledgement_preserves_accelerating_witness():
    e=evidence();e['commands']=[];e['force_observations']=[]
    result=assess_feedback(model(),e,**flags());p=result['preparation']
    assert p['snapshot']['force']==['-1','1']
    assert p['snapshot']['pending_by_delay']['3']==[['-1','1']]*3
    assert p['diagnostics']['unknown_queue_ticks_by_delay']=={'3':[97,98,99]}
    assert result['assessment']['finite_horizon_containment'] is False
    # Independently integrate a valid accelerating prehistory, then measured-P.
    pos,vel,force=Q(0),Q('.5'),Q('.8');queue=[Q('.8')]*3
    for row in result['assessment']['branches'][0]['history'][1:]:
        queue.append(max(Q(-1),min(Q(1),-2*vel)));target=queue.pop(0)
        force+=max(Q('-.08'),min(Q('.08'),target-force))
        vel+=Q('.02')*force;pos+=Q('.02')*vel
        for key,value in (('position',pos),('velocity',vel),('force',force)):
            lo,hi=map(Q,row[key]);assert lo<=value<=hi


def test_stale_transport_encloses_all_extreme_time_varying_accelerations():
    e=evidence();m=model();m.update(mass=['1','2'],cap=['1','2'],disturbance='.5')
    e['state_observations']=[packet(96,position=['-.1','.1'],velocity=['.4','.6'])]
    p=prepare(e,m);assert p['status']=='READY_CONDITIONAL_INPUTS'
    expected=Q('2.5');assert p['diagnostics']['acceleration_transport_bound_m_s2']==[str(-expected),str(expected)]
    for initialp,initialv,accels in product((Q('-.1'),Q('.1')),(Q('.4'),Q('.6')),product((-expected,expected),repeat=4)):
        pos,vel=initialp,initialv
        for accel in accels:vel+=Q('.02')*accel;pos+=Q('.02')*vel
        for key,value in (('position',pos),('velocity',vel)):
            lo,hi=map(Q,p['model'][key]);assert lo<=value<=hi
    # Aging must widen, never just relabel the old intervals as current.
    assert list(map(Q,p['model']['velocity']))==[Q('.2'),Q('.8')]
    assert p['snapshot']['state_bounds_tick']==100


def test_position_uses_semi_implicit_not_continuous_time_coefficient():
    e=evidence();e['state_observations']=[packet(99,position=['0','0'],velocity=['0','0'])]
    p=prepare(e);assert list(map(Q,p['model']['position']))==[Q('-.0004'),Q('.0004')]


def test_intersecting_new_packet_tightens_transported_old_bounds():
    e=evidence();e['state_observations']=[packet(98,position=['-.02','.02'],velocity=['.4','.6']),
                                        packet(position=['.01','.02'],velocity=['.48','.52'])]
    p=prepare(e)
    assert p['model']['position']==['1/100','1/50']
    assert p['model']['velocity']==['12/25','13/25']


@pytest.mark.parametrize('kind',['position','velocity','current_force','old_force','ack','cap'])
def test_contradictions_do_not_trigger_unknown_full_cap_fallback(kind):
    e=evidence()
    if kind in ('position','velocity'):
        row=packet(position=['0','0'],velocity=['.5','.5']);row[kind]=['9','9'];e['state_observations'].append(row)
    if kind=='current_force':e['force_observations'].append(packet(force=['1','1']))
    if kind=='old_force':e['force_observations']=[packet(99,force=['0','0']),packet(99,force=['1','1'])]
    if kind=='ack':e['commands'].append(command(98,'1'))
    if kind=='cap':e['force_observations']=[packet(force=['2','2'])]
    result=assess_feedback(model(),e,**flags())
    assert result['conclusion']=='CONTRADICTORY_EVIDENCE'
    assert result['assessment'] is None and result['preparation']['snapshot'] is None


def test_consistent_duplicate_ack_constraints_are_intersected():
    e=evidence();e['commands'][0]['effective_target']=['-.5','.5']
    e['commands'].append(command(97,'.2'))
    assert prepare(e)['snapshot']['pending_by_delay']['3'][0]==['1/5','1/5']


def test_stale_force_is_not_relabelled_as_current_or_assumed_zero():
    e=evidence();e['force_observations']=[packet(99,force=['-.8','-.8'])]
    p=prepare(e)
    assert p['snapshot']['force']==['-1','1']
    assert p['diagnostics']['stale_force_observations_unused'][0]['sample_tick']==99


def test_every_delay_has_ordered_fifo_and_explicit_missing_slots():
    e=evidence();m=model();m['delay_ticks']=[0,3];e['commands']=[command(99,'-.4'),command(97,'.8')]
    p=prepare(e,m);q=p['snapshot']['pending_by_delay']
    assert q=={'0':[], '1':[['-2/5','-2/5']], '2':[['-1','1'],['-2/5','-2/5']],
               '3':[['4/5','4/5'],['-1','1'],['-2/5','-2/5']]}


def test_unobserved_pre_epoch_zero_queue_is_not_invented():
    e=evidence();e['assessment_tick']=0;e['commands']=[]
    e['state_observations']=[dict(packet(position=['0','0'],velocity=['0','0']),sample_tick=0,received_tick=0)]
    e['force_observations']=[];e['power']['received_tick']=0
    p=prepare(e);assert p['snapshot']['pending_by_delay']['3']==[['-1','1']]*3


@pytest.mark.parametrize('window,expected',[([80,85],[0,0]),([100,103],[0,3]),([110,120],[10,20])])
def test_absolute_deadline_is_not_a_fresh_duration(window,expected):
    e=evidence();e['power']['absolute_cut_ticks']=window;p=prepare(e)
    assert p['diagnostics']['remaining_power_cut_ticks']==expected
    assert p['model']['power_cut_ticks']==expected


def test_expired_power_coasts_even_with_valid_braking_acknowledgements():
    e=evidence();e['power']['absolute_cut_ticks']=[80,85]
    result=assess_feedback(model(),e,**flags())
    final=result['assessment']['branches'][0]['history'][-1]
    assert final['velocity']==['1/2','1/2'] and final['position']==['7/5','7/5']
    assert result['assessment']['finite_horizon_containment'] is False


@pytest.mark.parametrize('sample_tick',[99,100])
def test_nonzero_force_after_certain_power_loss_is_contradictory(sample_tick):
    e=evidence();e['power']['absolute_cut_ticks']=[80,85]
    e['force_observations']=[packet(sample_tick,force=['.8','.8'])]
    r=prepare(e)
    assert r['status']=='CONTRADICTORY_EVIDENCE' and r['snapshot'] is None


def test_certain_power_loss_flushes_initial_fifo_without_inventing_history():
    e=evidence();e['power']['absolute_cut_ticks']=[80,85]
    e['force_observations']=[];e['commands']=[command(t,'.8') for t in (97,98,99)]
    r=prepare(e)
    assert r['snapshot']['force']==['0','0']
    assert r['snapshot']['pending_by_delay']['3']==[['0','0']]*3
    assert r['diagnostics']['power_flush_status']=='CERTAIN_PRIOR_UNPOWERED_STEP'


def test_possible_prior_cutoff_retains_both_flushed_and_powered_queue_values():
    e=evidence();e['power']['absolute_cut_ticks']=[99,102]
    e['commands']=[command(t,'.8') for t in (97,98,99)]
    r=prepare(e)
    assert r['snapshot']['pending_by_delay']['3']==[['0','4/5']]*3
    assert r['model']['power_cut_ticks']==[0,2]
    assert r['diagnostics']['power_flush_status']=='POSSIBLE_PRIOR_UNPOWERED_STEP_ZERO_INCLUDED'


def test_cutoff_at_assessment_has_not_flushed_previous_interval_yet():
    e=evidence();e['power']['absolute_cut_ticks']=[100,100]
    e['commands']=[command(t,'.8') for t in (97,98,99)]
    e['force_observations']=[packet(force=['.8','.8'])]
    r=prepare(e)
    assert r['snapshot']['force']==['4/5','4/5']
    assert r['snapshot']['pending_by_delay']['3']==[['4/5','4/5']]*3
    assert r['model']['power_cut_ticks']==[0,0]


@pytest.mark.parametrize('flag',[k for k in flags() if k!='evidence_status'])
def test_unasserted_premise_prevents_evaluation(flag):
    f=flags();f[flag]=False;r=assess_feedback(model(),evidence(),**f)
    assert r['conclusion']=='UNKNOWN_PHYSICAL_PREMISES' and r['assessment'] is None


@pytest.mark.parametrize('status,expected',[('UNKNOWN','UNKNOWN_EVIDENCE'),('CONTRADICTORY','CONTRADICTORY_EVIDENCE')])
def test_external_evidence_state_not_promoted(status,expected):
    assert prepare(evidence_status=status)['status']==expected


@pytest.mark.parametrize('kind',['state','power'])
def test_missing_essential_evidence_never_defaults_to_reset(kind):
    e=evidence()
    if kind=='state':e['state_observations']=[]
    else:e['power']=None
    r=assess_feedback(model(),e,**flags())
    assert r['conclusion']=='UNKNOWN_EVIDENCE' and r['assessment'] is None


@pytest.mark.parametrize('kind',['clock','frame','future_sample','future_receipt','early_receipt','age','target','future_enqueue','extra','float','bool','exponent','huge_exponent','too_many','power_clock','power_receipt'])
def test_malformed_or_unsupported_inputs_are_unknown(kind):
    e=evidence();row=e['state_observations'][0]
    if kind=='clock':row['clock_id']='different'
    if kind=='frame':row['frame']='BODY_X'
    if kind=='future_sample':row['sample_tick']=101
    if kind=='future_receipt':row['received_tick']=101
    if kind=='early_receipt':row['received_tick']=99
    if kind=='age':row['sample_tick']=91
    if kind=='target':e['commands'][0]['effective_target']=['-2','2']
    if kind=='future_enqueue':e['commands'][0]['enqueue_tick']=100
    if kind=='extra':row['truth_velocity']=.5
    if kind=='float':row['position']=[0.,0.]
    if kind=='bool':row['position']=[False,False]
    if kind=='exponent':row['position']=['1e2','1e2']
    if kind=='huge_exponent':row['position']=['1e999999999999999999','1e999999999999999999']
    if kind=='too_many':e['commands']*=50
    if kind=='power_clock':e['power']['clock_id']='different'
    if kind=='power_receipt':e['power']['received_tick']=101
    r=prepare(e);assert r['status']=='UNKNOWN_INPUT' and r['snapshot'] is None


def test_order_of_compatible_evidence_does_not_change_bounds():
    e=evidence();e['state_observations'].append(packet(99,position=['-.1','.1'],velocity=['.3','.7']))
    original=prepare(e);e['state_observations'].reverse();e['commands'].reverse()
    changed=prepare(e)
    assert original['model']==changed['model'] and original['snapshot']==changed['snapshot']


def test_coherent_false_feedback_is_not_authenticated_by_consistency_checks():
    # A common-mode source can lie coherently about force, queue and velocity.
    # No truth field is supplied to the candidate; this test documents the limit.
    r=assess_feedback(model(),evidence(),**flags())
    assert r['assessment']['finite_horizon_containment'] is True
    assert r['preparation']['trust']=='CALLER_ASSERTIONS_NOT_AUTHENTICATED'
    assert r['assessment']['future_position_containment']=='NOT_ESTABLISHED'
    assert r['action'] is None and not r['operational_authorization']
