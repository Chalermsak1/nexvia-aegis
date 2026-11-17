"""Evidence-gated adapter of the historical ideal recovery proof. No dispatch."""
from copy import deepcopy
from . import physical_time_recovery as physical
from .durable_feedback_session import sha
from .independent_clock_mapping import IndependentClockMap,tick
from .recovery_evidence import PREMISE_NAMES,SCOPE

PREDICATES=dict(zip(PREMISE_NAMES,('ENCLOSES','ENCLOSES','ENCLOSES','ENCLOSES','IDENTITY','ENCLOSES','DISTINCT','DISTINCT','ENCLOSES')))
INPUTS={'backup','parameter_bounds','packet','clock_map','now_local','units_per_second','max_state_age_seconds','local_epoch','boot_id','active_force_cap','handoff_delay_seconds','monitor_seconds','primary_healthy','dynamics_id'}


def policy(*,source_ids,max_age_ticks):
    if set(source_ids)!=set(PREMISE_NAMES):raise ValueError('all premise sources must be explicit')
    return {k:dict(source_id=source_ids[k],predicate=PREDICATES[k],max_age_ticks=max_age_ticks) for k in PREMISE_NAMES}


def input_identity(inputs):
    if type(inputs) is not dict or set(inputs)!=INPUTS:raise ValueError('exact physical inputs without boolean premises required')
    clock=inputs['clock_map']
    if type(clock) is not IndependentClockMap:raise ValueError('explicit supported clock-map implementation required')
    packet=inputs['packet']
    mapping=clock.map_event(packet['remote_time'],local_epoch=inputs['local_epoch'],remote_epoch=packet['remote_epoch'])
    identity={k:deepcopy(v) for k,v in inputs.items() if k!='clock_map'}
    identity['clock_map']=dict(local_epoch=clock.local_epoch,remote_epoch=clock.remote_epoch,rate_bounds=[str(clock.lo),str(clock.hi)],max_extrapolation=clock.extrapolation,mapping=mapping,exchange_sha256=deepcopy(clock._seen))
    return sha(identity),mapping


def statement_for(inputs):
    identity,mapping=input_identity(inputs);b=inputs['backup'];f=inputs['parameter_bounds'];p=inputs['packet']
    if mapping['status']!='CONDITIONAL_INTERVAL_MAPPING':raise ValueError('clock mapping is not established')
    from .recovery_feedback_state_1d import _number,_bounds
    delay=_bounds(inputs['handoff_delay_seconds']);cap=_number(inputs['active_force_cap'])
    if delay.lo<0 or cap<0:raise ValueError('nonnegative delay and cap required')
    expected=[
        [p['position'],p['velocity']],
        [f['mass'],f['spring'],f['damping']],
        [mapping['local_interval']],
        [['0',str(cap)]],
        dict(backup=b,dynamics_id=inputs['dynamics_id']),
        [delay.wire()],
        ['controller','watchdog','plant'],
        ['primary_power','backup_power'],
        [['0','0'],['0','0']],
    ]
    return dict(scope=SCOPE,input_sha256=identity,requirements={k:dict(predicate=PREDICATES[k],expected=deepcopy(v)) for k,v in zip(PREMISE_NAMES,expected)})


def assess(journal,inputs,*,finish_clock):
    out=dict(status='EVIDENCE_WITHHELD',development_action=None,conditional_continuous_containment=False,model_plan=None,evidence=None,dispatch=False,operational_authorization=False,hardware_validation=False,independent_attestation=False,gate_b='GATE_B_NOT_AUTHORIZED',scope=SCOPE,reason=None)
    try:
        start=tick(inputs['now_local']);statement=statement_for(inputs)
        if inputs['boot_id']!=journal.state['boot_id'] or inputs['local_epoch']!=journal.state['clock_domain']:return dict(out,reason='ASSESSMENT_BOOT_OR_DOMAIN_MISMATCH')
        evidence=journal.evaluate(statement,now=start);out['evidence']=evidence
        if evidence['status']!='SIMULATION_PREDICATES_SUPPORTED':return dict(out,reason='CURRENT_BOUND_EVIDENCE_REQUIRED')
        # These booleans now mean only the nine checked, bound simulation
        # predicates. The proof remains conditional on their physical meaning.
        copied={k:deepcopy(v) for k,v in inputs.items() if k!='clock_map'};copied['clock_map']=inputs['clock_map']
        result=physical.assess(**copied,premises={k:True for k in PREMISE_NAMES});out['model_plan']=result
        try:finish=tick(finish_clock())
        except Exception:
            try:journal.record_fault('ASSESSMENT_CLOCK_FAILURE',now=start)
            except Exception:pass  # a failed durable write still cannot issue a candidate
            raise
        final_evidence=journal.evaluate(statement,now=finish);out['evidence']=final_evidence
        if input_identity(inputs)[0]!=statement['input_sha256']:return dict(out,reason='INPUT_CHANGED_DURING_ASSESSMENT')
        if final_evidence['status']!='SIMULATION_PREDICATES_SUPPORTED':return dict(out,reason='EVIDENCE_INVALID_AT_COMPLETION')
        if finish!=start:return dict(out,reason='TIME_ADVANCED_FRESH_ASSESSMENT_REQUIRED')
        if result['status']!='CONDITIONAL_PHYSICAL_TIME_PLAN' or result['conditional_continuous_containment'] is not True:return dict(out,status='MODEL_UNRESOLVED',reason=result.get('reason'))
        return dict(out,status='DEVELOPMENT_EVIDENCE_BACKED_CONDITIONAL_PLAN',development_action=result['development_action'],conditional_continuous_containment=True,statement_sha256=sha(statement),reason=None)
    except Exception as exc:return dict(out,reason='INVALID_OR_UNCOMMITTED_EVIDENCE_INPUT',error_type=type(exc).__name__,detail=str(exc))
