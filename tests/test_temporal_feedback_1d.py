"""Synthetic temporal failure mechanisms; no reserved data or hardware."""
from copy import deepcopy
from fractions import Fraction as Q
import pytest

from aegis.development.temporal_feedback_1d import TemporalFeedbackSession


def model():
    return dict(dt='.02',position=['0','0'],velocity=['.5','.5'],mass=['1','1'],gain=['2','2'],
                cap=['1','1'],slew=['4','4'],disturbance='0',measurement_error='0',delay_ticks=[3,3],
                power_cut_ticks=[160,160],horizon=140,safe_position=['-.5','.32'],terminal_velocity=['-.05','.05'],terminal_samples=25)


def limits():
    return dict(max_transport_ticks=8,max_state_age_ticks=16,max_reaction_ticks=8,reorder_window=4,max_records=128,max_streams=16)


def flags():
    return dict(evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS',measurement_bounds_asserted=True,
                actuator_model_asserted=True,power_bounds_asserted=True,command_records_asserted=True,clock_bounds_asserted=True)


def session(m=None,**changes):
    cfg=limits();cfg.update(changes)
    return TemporalFeedbackSession(model() if m is None else m,session_id='boot-A',clock_id='clock-A',start_tick=0,limits=cfg,assumptions=flags())


def packet(kind,tick,sequence=0,source=None,**payload):
    return dict(session_id='boot-A',clock_id='clock-A',frame='WORLD_X_SI',source_id=source or kind,
                kind=kind,sequence=sequence,event_tick=tick,payload=payload)


def seed(s,*,force='0',target='0',power=(260,260),state_tick=100,receive=100):
    records=[packet('STATE',state_tick,position=['0','0'],velocity=['.5','.5']),
             packet('FORCE',100,force=[force,force]),packet('POWER',100,absolute_cut_ticks=list(power))]
    records += [packet('COMMAND_ENQUEUED',t,sequence=t-97,command_id='cmd-'+str(t),effective_target=[target,target]) for t in (97,98,99)]
    for row in records:assert s.ingest(row,received_tick=receive)['status']=='ACCEPTED'
    return records


def test_complete_zero_reaction_path_preserves_existing_point_result():
    s=session();seed(s);r=s.assess_at(100,reaction_delay_ticks=0)
    assert r['status']=='READY_CONDITIONAL_INPUTS' and r['assessment']['finite_horizon_containment'] is True
    assert r['preparation']['snapshot']['pending_by_delay']['3']==[['0','0']]*3
    assert r['action'] is None and not r['operational_authorization']
    assert r['reaction_prefix_containment'] and r['combined_finite_horizon_containment']


def test_reaction_latency_forecast_does_not_relabel_state_or_assume_zero_queued_inputs():
    s=session();seed(s);r=s.assess_at(100,reaction_delay_ticks=3)
    assert r['effect_tick']==103 and r['assessment_tick']==100
    assert r['preparation']['diagnostics']['transported_state_observations'][0]['age_ticks']==3
    assert r['preparation']['snapshot']['force']==['-1','1']
    assert r['preparation']['snapshot']['pending_by_delay']['3']==[['-1','1']]*3
    assert r['preparation']['model']['velocity']==['11/25','14/25']
    assert r['assessment']['finite_horizon_containment'] is False
    # Forecast does not falsely advance actual time to 103.
    newer=packet('FORCE',101,sequence=1,force=['0','0'])
    assert s.ingest(newer,received_tick=101)['status']=='ACCEPTED'


def test_delayed_feedback_is_transported_from_event_time_not_arrival_time():
    s=session();seed(s,state_tick=96)
    r=s.assess_at(100,reaction_delay_ticks=0)
    assert r['preparation']['model']['velocity']==['21/50','29/50']
    assert r['preparation']['diagnostics']['transported_state_observations'][0]['age_ticks']==4


def test_duplicate_replay_does_not_refresh_original_observation_age():
    s=session();rows=seed(s);first=s.assess_at(100,reaction_delay_ticks=0)
    assert s.ingest(rows[0],received_tick=101)['status']=='REPLAY_IGNORED'
    later=s.assess_at(101,reaction_delay_ticks=0)
    assert later['replays_ignored']==1
    assert later['preparation']['diagnostics']['transported_state_observations'][0]['sample_tick']==100
    assert later['preparation']['model']['velocity']!=first['preparation']['model']['velocity']


def test_duplicate_power_does_not_renew_expired_budget():
    s=session();rows=seed(s,power=(99,100));power=rows[2]
    assert s.ingest(power,received_tick=101)['status']=='REPLAY_IGNORED'
    r=s.assess_at(101,reaction_delay_ticks=0)
    assert r['preparation']['diagnostics']['remaining_power_cut_ticks']==[0,0]


def test_sequence_equivocation_latches_even_if_later_packets_look_valid():
    s=session();rows=seed(s);changed=deepcopy(rows[0]);changed['payload']['velocity']=['0','0']
    assert s.ingest(changed,received_tick=100)['status']=='CONTRADICTORY_EVIDENCE'
    assert s.ingest(rows[0],received_tick=100)['status']=='CONTRADICTORY_EVIDENCE'
    assert s.assess_at(100,reaction_delay_ticks=0)['assessment'] is None


def test_bounded_out_of_order_delivery_never_replaces_newer_event_with_older_one():
    s=session()
    newer=packet('STATE',100,sequence=2,position=['0','0'],velocity=['0','0'])
    older=packet('STATE',99,sequence=1,position=['0','0'],velocity=['0','0'])
    assert s.ingest(newer,received_tick=100)['status']=='ACCEPTED'
    assert s.ingest(older,received_tick=100)['status']=='ACCEPTED'
    assert s.ingest(packet('POWER',100,absolute_cut_ticks=[260,260]),received_tick=100)['status']=='ACCEPTED'
    r=s.assess_at(100,reaction_delay_ticks=0)
    assert r['preparation']['diagnostics']['transported_state_observations'][0]['sample_tick']==100


def test_old_sequences_below_window_rejected_after_fingerprint_eviction():
    s=session(reorder_window=2)
    for seq in (0,2):
        assert s.ingest(packet('STATE',100,sequence=seq,position=['0','0'],velocity=['0','0']),received_tick=100)['status']=='ACCEPTED'
    changed=packet('STATE',100,sequence=0,position=['9','9'],velocity=['0','0'])
    assert s.ingest(changed,received_tick=100)['status']=='STALE_SEQUENCE_REJECTED'
    # Rejected content cannot overwrite the retained position.
    s.ingest(packet('POWER',100,absolute_cut_ticks=[260,260]),received_tick=100)
    assert s.assess_at(100,reaction_delay_ticks=0)['preparation']['model']['position']==['0','0']


@pytest.mark.parametrize('which',['receipt','assessment'])
def test_clock_rollback_requires_explicit_new_session(which):
    s=session();seed(s)
    if which=='receipt':r=s.ingest(packet('FORCE',99,sequence=1,force=['0','0']),received_tick=99)
    else:r=s.assess_at(99,reaction_delay_ticks=0)
    assert r['status']=='SESSION_RESYNC_REQUIRED'
    assert s.assess_at(101,reaction_delay_ticks=0)['assessment'] is None


def test_new_session_clears_evidence_but_does_not_assume_physical_reset():
    s=session();old=seed(s,force='.8',target='.8')
    s.begin_session(session_id='boot-B',clock_id='clock-B',start_tick=0)
    assert s.ingest(old[0],received_tick=0)['status']=='SESSION_OR_CLOCK_REJECTED'
    assert s.assess_at(0,reaction_delay_ticks=0)['status']=='UNKNOWN_EVIDENCE'
    for kind,payload in [('STATE',dict(position=['0','0'],velocity=['.5','.5'])),('POWER',dict(absolute_cut_ticks=[160,160]))]:
        row=packet(kind,0,**payload);row.update(session_id='boot-B',clock_id='clock-B')
        assert s.ingest(row,received_tick=0)['status']=='ACCEPTED'
    r=s.assess_at(0,reaction_delay_ticks=0)
    assert r['preparation']['snapshot']['force']==['-1','1']
    assert r['preparation']['snapshot']['pending_by_delay']['3']==[['-1','1']]*3
    with pytest.raises(ValueError):s.begin_session(session_id='boot-A',clock_id='clock-A',start_tick=0)


def test_recreated_process_is_not_a_durable_anti_replay_trust_anchor():
    old=session();row=packet('STATE',100,position=['0','0'],velocity=['0','0'])
    assert old.ingest(row,received_tick=100)['status']=='ACCEPTED'
    recreated=session()
    assert recreated.ingest(row,received_tick=100)['status']=='ACCEPTED'
    assert recreated.assess_at(100,reaction_delay_ticks=0)['trust']=='IN_MEMORY_LABEL_CHECKS_NOT_AUTHENTICATION'


def test_elapsed_time_without_ack_never_becomes_observed_execution():
    s=session();seed(s);r=s.assess_at(104,reaction_delay_ticks=0)
    assert r['command_tracking']['cmd-97']['status']=='EXECUTION_UNCONFIRMED'
    assert r['command_tracking']['cmd-97']['acknowledged_completion_tick'] is None


def test_consumed_ack_removed_from_pending_queue_and_not_reinserted_by_replay():
    s=session();rows=seed(s)
    ack=packet('COMMAND_CONSUMED',101,command_id='cmd-97')
    assert s.ingest(ack,received_tick=101)['status']=='ACCEPTED'
    assert s.ingest(rows[3],received_tick=102)['status']=='REPLAY_IGNORED'
    r=s.assess_at(102,reaction_delay_ticks=0)
    assert r['command_tracking']['cmd-97']['status']=='ACKNOWLEDGED_CONSUMED_NOT_PHYSICAL_OUTCOME_PROOF'
    assert r['preparation']['diagnostics']['unknown_queue_ticks_by_delay']['3']==[100,101]
    assert r['preparation']['snapshot']['pending_by_delay']['3']==[['0','0'],['-1','1'],['-1','1']]


def test_consumption_before_enqueue_ack_is_unknown_until_history_arrives():
    s=session()
    ack=packet('COMMAND_CONSUMED',100,command_id='c')
    assert s.ingest(ack,received_tick=100)['status']=='ACCEPTED'
    assert s.assess_at(100,reaction_delay_ticks=0)['status']=='UNKNOWN_COMMAND_HISTORY'
    command=packet('COMMAND_ENQUEUED',96,command_id='c',effective_target=['0','0'])
    assert s.ingest(command,received_tick=100)['status']=='ACCEPTED'
    assert s.assess_at(100,reaction_delay_ticks=0)['status']=='UNKNOWN_EVIDENCE'


@pytest.mark.parametrize('change',['too_early','wrong_delay','id_reuse','two_ids','different_completion','power_flush'])
def test_command_causality_conflicts_latch(change):
    s=session();seed(s)
    if change in ('too_early','wrong_delay'):
        row=packet('COMMAND_CONSUMED',100 if change=='too_early' else 102,command_id='cmd-97')
        result=s.ingest(row,received_tick=row['event_tick'])
    elif change=='id_reuse':
        result=s.ingest(packet('COMMAND_ENQUEUED',96,sequence=3,command_id='cmd-97',effective_target=['0','0']),received_tick=100)
    elif change=='two_ids':
        result=s.ingest(packet('COMMAND_ENQUEUED',97,sequence=3,command_id='other',effective_target=['0','0']),received_tick=100)
    elif change=='different_completion':
        assert s.ingest(packet('COMMAND_CONSUMED',101,command_id='cmd-97'),received_tick=101)['status']=='ACCEPTED'
        result=s.ingest(packet('COMMAND_CONSUMED',102,sequence=1,command_id='cmd-97'),received_tick=102)
    else:
        assert s.ingest(packet('POWER',100,sequence=1,absolute_cut_ticks=[99,100]),received_tick=100)['status']=='CONTRADICTORY_EVIDENCE'
        return
    assert result['status']=='CONTRADICTORY_EVIDENCE'
    assert s.assess_at(103,reaction_delay_ticks=0)['assessment'] is None


def test_consumption_during_certain_power_loss_is_not_execution():
    s=session();seed(s,power=(99,100))
    r=s.ingest(packet('COMMAND_CONSUMED',101,command_id='cmd-97'),received_tick=101)
    assert r['status']=='CONTRADICTORY_EVIDENCE'


def test_consumption_narrows_static_delay_but_does_not_prove_target_force():
    m=model();m['delay_ticks']=[1,3];s=session(m);seed(s)
    r=s.ingest(packet('COMMAND_CONSUMED',100,command_id='cmd-97'),received_tick=100)
    assert r['status']=='ACCEPTED'
    out=s.assess_at(100,reaction_delay_ticks=0)
    assert out['supported_static_delays']==[2]
    assert out['preparation']['snapshot']['pending_by_delay']=={'2':[['0','0'],['0','0']]}
    assert out['command_tracking']['cmd-97']['status']=='ACKNOWLEDGED_CONSUMED_NOT_PHYSICAL_OUTCOME_PROOF'


def test_conflicting_static_delays_cannot_be_combined_as_variable_delay():
    m=model();m['delay_ticks']=[1,3];s=session(m);seed(s)
    assert s.ingest(packet('COMMAND_CONSUMED',100,command_id='cmd-97'),received_tick=100)['status']=='ACCEPTED'  # d=2
    assert s.ingest(packet('COMMAND_CONSUMED',102,sequence=1,command_id='cmd-98'),received_tick=102)['status']=='CONTRADICTORY_EVIDENCE'  # d=3


def test_power_bounds_intersect_instead_of_restarting_or_extending():
    s=session();seed(s,power=(250,260))
    assert s.ingest(packet('POWER',101,sequence=1,absolute_cut_ticks=[255,265]),received_tick=101)['status']=='ACCEPTED'
    out=s.assess_at(102,reaction_delay_ticks=0)
    assert out['preparation']['diagnostics']['remaining_power_cut_ticks']==[153,158]
    assert s.ingest(packet('POWER',102,sequence=2,absolute_cut_ticks=[270,280]),received_tick=102)['status']=='CONTRADICTORY_EVIDENCE'


def test_old_state_cannot_hide_a_physical_contradiction_by_arriving_last():
    s=session()
    assert s.ingest(packet('STATE',100,sequence=1,position=['0','0'],velocity=['0','0']),received_tick=100)['status']=='ACCEPTED'
    bad=packet('STATE',99,sequence=0,position=['10','10'],velocity=['0','0'])
    assert s.ingest(bad,received_tick=100)['status']=='CONTRADICTORY_EVIDENCE'


@pytest.mark.parametrize('kind',['STATE','FORCE','COMMAND_ENQUEUED','COMMAND_CONSUMED','POWER'])
def test_transport_limit_does_not_mark_late_events_fresh(kind):
    s=session(max_transport_ticks=2)
    payload={'STATE':dict(position=['0','0'],velocity=['0','0']),'FORCE':dict(force=['0','0']),
             'COMMAND_ENQUEUED':dict(command_id='c',effective_target=['0','0']),
             'COMMAND_CONSUMED':dict(command_id='c'),'POWER':dict(absolute_cut_ticks=[200,200])}[kind]
    assert s.ingest(packet(kind,97,**payload),received_tick=100)['status']=='TRANSPORT_LATENCY_REJECTED'


def test_expired_state_is_reported_and_never_reused_as_current():
    s=session();seed(s);r=s.assess_at(117,reaction_delay_ticks=0)
    assert r['status']=='UNKNOWN_EVIDENCE'
    assert r['preparation']['reason']=='no state observation; no reset state invented'


def test_safe_effect_state_cannot_hide_unsafe_reaction_start():
    m=model();m.update(horizon=10,terminal_samples=2,terminal_velocity=['-1','1'])
    s=session(m)
    rows=seed(s)
    # Use a separate session with an initially out-of-bounds state moving inward.
    s=session(m)
    rows[0]['payload'].update(position=['.33','.33'],velocity=['-.5','-.5'])
    for row in rows:assert s.ingest(row,received_tick=100)['status']=='ACCEPTED'
    r=s.assess_at(100,reaction_delay_ticks=3)
    assert r['assessment']['finite_horizon_containment'] is True
    assert r['reaction_prefix_containment'] is False
    assert r['combined_finite_horizon_containment'] is False
    assert r['conclusion']=='NOT_ESTABLISHED_REACTION_PREFIX_EXITS_SAFE_SET'


@pytest.mark.parametrize('field,value',[('reaction_delay_ticks',True),('reaction_delay_ticks',9),('reaction_delay_ticks',-1)])
def test_unsupported_reaction_forecast_is_unknown(field,value):
    s=session();seed(s);assert s.assess_at(100,**{field:value})['status']=='UNKNOWN_INPUT'


@pytest.mark.parametrize('change',['future','bool_sequence','negative_sequence','bad_frame','extra_truth','float','bad_kind'])
def test_invalid_packets_do_not_consume_valid_sequence(change):
    s=session();row=packet('STATE',100,position=['0','0'],velocity=['0','0']);bad=deepcopy(row)
    if change=='future':bad['event_tick']=101
    if change=='bool_sequence':bad['sequence']=True
    if change=='negative_sequence':bad['sequence']=-1
    if change=='bad_frame':bad['frame']='BODY_X'
    if change=='extra_truth':bad['truth_velocity']=0
    if change=='float':bad['payload']['velocity']=[0.,0.]
    if change=='bad_kind':bad['kind']='TRUTH'
    assert s.ingest(bad,received_tick=100)['status']=='UNKNOWN_INPUT'
    assert s.ingest(row,received_tick=100)['status']=='ACCEPTED'


def test_record_budget_exhaustion_requires_resync_without_evidence_eviction():
    s=session(max_records=1)
    a=packet('STATE',100,position=['0','0'],velocity=['0','0'])
    assert s.ingest(a,received_tick=100)['status']=='ACCEPTED'
    assert s.ingest(packet('POWER',100,absolute_cut_ticks=[200,200]),received_tick=100)['status']=='SESSION_RESYNC_REQUIRED'
    assert s.assess_at(100,reaction_delay_ticks=0)['assessment'] is None


def test_unasserted_clock_or_common_mode_false_feedback_never_authorizes_actions():
    s=session();seed(s);r=s.assess_at(100,reaction_delay_ticks=0)
    assert r['assessment']['finite_horizon_containment'] is True
    assert r['trust']=='IN_MEMORY_LABEL_CHECKS_NOT_AUTHENTICATION'
    assert not r['operational_authorization'] and r['action'] is None
    f=flags();f['clock_bounds_asserted']=False
    other=TemporalFeedbackSession(model(),session_id='boot-A',clock_id='clock-A',start_tick=0,limits=limits(),assumptions=f)
    seed(other);assert other.assess_at(100,reaction_delay_ticks=0)['status']=='UNKNOWN_PHYSICAL_PREMISES'


@pytest.mark.parametrize('reaction',[0,1,2,3,4])
def test_reaction_then_recovery_encloses_independent_exact_actuator_trajectory(reaction):
    m=model();m.update(horizon=20,terminal_samples=2,safe_position=['-5','5'])
    s=session(m);seed(s,force='.8',target='.8')
    r=s.assess_at(100,reaction_delay_ticks=reaction)
    p,v,f=Q(0),Q('.5'),Q('.8');queue=[Q('.8')]*3;h=Q('.02')
    def step(request):
        nonlocal p,v,f
        queue.append(max(Q(-1),min(Q(1),request)));due=queue.pop(0)
        f+=max(Q('-.08'),min(Q('.08'),due-f));v+=h*f;p+=h*v
    # Uncontrolled pre-enqueue latency can contain accelerating commands.
    for i in range(reaction):step(Q(1) if i%2==0 else Q(-1))
    history=r['assessment']['branches'][0]['history']
    for row in history:
        for key,value in (('position',p),('velocity',v),('force',f)):
            lo,hi=map(Q,row[key]);assert lo<=value<=hi
        for bound,target in zip(row['pending_targets'],queue):
            lo,hi=map(Q,bound);assert lo<=target<=hi
        step(-2*v)


def test_foreign_session_or_clock_never_claims_sequence_or_switches_active_session():
    s=session();row=packet('STATE',100,position=['0','0'],velocity=['0','0'])
    for field in ('session_id','clock_id'):
        bad=deepcopy(row);bad[field]='foreign'
        assert s.ingest(bad,received_tick=100)['status']=='SESSION_OR_CLOCK_REJECTED'
    assert s.ingest(row,received_tick=100)['status']=='ACCEPTED'


def test_stream_budget_does_not_drop_previous_evidence_to_admit_new_source():
    s=session(max_streams=1)
    assert s.ingest(packet('STATE',100,position=['0','0'],velocity=['0','0']),received_tick=100)['status']=='ACCEPTED'
    assert s.ingest(packet('POWER',100,absolute_cut_ticks=[200,200]),received_tick=100)['status']=='SESSION_RESYNC_REQUIRED'


def test_inputs_and_returned_models_cannot_mutate_session_records():
    s=session();rows=seed(s);before=deepcopy(rows)
    out=s.assess_at(100,reaction_delay_ticks=0)
    assert rows==before
    out['preparation']['model']['position'][0]='99'
    rows[0]['payload']['position']=['99','99']
    again=s.assess_at(100,reaction_delay_ticks=0)
    assert again['preparation']['model']['position']==['0','0']


@pytest.mark.parametrize('field,value',[('max_transport_ticks',True),('max_state_age_ticks',65),('max_reaction_ticks',-1),('reorder_window',0),('max_records',129),('max_streams',33)])
def test_explicit_development_resource_limits_are_validated(field,value):
    with pytest.raises(ValueError):session(**{field:value})


def test_start_epoch_feedback_adapter_conflict_remains_latched(monkeypatch):
    # Boundary fault injection: an adapter contradiction must not be forgotten
    # when a later packet arrives, even before the effect-epoch analysis begins.
    from aegis.development import temporal_feedback_1d as temporal
    s=session();seed(s)
    monkeypatch.setattr(temporal,'prepare_feedback',lambda *a,**kw:dict(
        status='CONTRADICTORY_EVIDENCE',reason='synthetic start-epoch feedback conflict'))
    assert s.assess_at(100,reaction_delay_ticks=0)['status']=='CONTRADICTORY_EVIDENCE'
    later=packet('FORCE',101,sequence=1,force=['0','0'])
    assert s.ingest(later,received_tick=101)['status']=='CONTRADICTORY_EVIDENCE'
