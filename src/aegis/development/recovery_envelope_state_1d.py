"""DEVELOPMENT 1D reachability from a non-reset actuator-state snapshot.

All state/queue/power bounds refer to one explicit assessment epoch. No stale
snapshot transport, power restoration, physical authentication or online action
admission is implemented. The original reset model remains unchanged.
"""
from fractions import Fraction as Q
from .recovery_envelope_1d import spec,interval_input,internal,point,target_box,force_box,linked_velocity


def snapshot(raw,s):
    fields={'mode','assessment_tick','state_bounds_tick','actuator_bounds_tick','force','pending_by_delay'}
    if not isinstance(raw,dict) or set(raw)!=fields:raise ValueError('exact snapshot fields required')
    for k in ('assessment_tick','state_bounds_tick','actuator_bounds_tick'):
        if type(raw[k]) is not int or raw[k]<0:raise ValueError('nonnegative integer snapshot epochs required')
    if raw['state_bounds_tick']!=raw['assessment_tick'] or raw['actuator_bounds_tick']!=raw['assessment_tick']:
        raise ValueError('STALE_OR_MISALIGNED_STATE_BOUNDS')
    cap=internal(-s['cap'].hi,s['cap'].hi);d0,d1=s['delay_ticks']
    if raw['mode']=='FULL_CAP_UNCERTAINTY':
        if raw['force'] is not None or raw['pending_by_delay'] is not None:raise ValueError('full-cap mode cannot silently ignore explicit values')
        force=cap;queues={d:[cap for _ in range(d)] for d in range(d0,d1+1)}
    elif raw['mode']=='EXPLICIT_INTERVALS':
        force=interval_input(raw['force'],'initial previous force')
        pending=raw['pending_by_delay']
        if not isinstance(pending,dict) or set(pending)!={str(d) for d in range(d0,d1+1)}:raise ValueError('one explicit queue per delay required')
        queues={}
        for d in range(d0,d1+1):
            values=pending[str(d)]
            if not isinstance(values,list) or len(values)!=d:raise ValueError('queue length must equal branch delay')
            queues[d]=[interval_input(x,'pending target') for x in values]
            if any(not x.inside(cap) for x in queues[d]):raise ValueError('pending target bound exceeds cap domain')
        if not force.inside(cap):raise ValueError('initial force bound exceeds cap domain')
    else:raise ValueError('unsupported snapshot mode')
    return force,queues


def propagate(s,delay,cut,initial_force,pending,*,linked=True):
    p,v=s['position'],s['velocity'];force=initial_force;queue=list(pending);zero=point(Q(0));increments=[]
    history=[{'tick':0,'position':p.wire(),'velocity':v.wire(),'force':force.wire(),'pending_targets':[x.wire() for x in queue]}]
    positions=[p];velocities=[]
    for k in range(s['horizon']):
        if k<cut:
            queue.append(target_box(v,s['measurement_error'],s['gain'],s['cap']));due=queue.pop(0)
            fn=force_box(force,due,s['slew'],s['cap'],s['dt'])
            dv=point(s['dt'])*(fn+internal(-s['disturbance'],s['disturbance'])).divide_positive(s['mass'])
            vn=v+dv
            # Initial queued commands have no justified relation to current
            # velocity. Link only after the full pre-assessment queue is gone.
            if linked and k>=delay:
                lag=zero
                for delta in increments[k-delay:k]:lag=lag+delta
                candidate=linked_velocity(v,force,due,lag,s['measurement_error'],s['gain'],s['slew'],s['cap'],s['mass'],s['disturbance'],s['dt'])
                vn=internal(max(vn.lo,candidate.lo),min(vn.hi,candidate.hi))
                if vn.lo>vn.hi:raise ValueError('empty velocity enclosure')
        else:
            fn=zero;queue=[zero for _ in range(delay)]
            dv=point(s['dt'])*internal(-s['disturbance'],s['disturbance']).divide_positive(s['mass']);vn=v+dv
        pn=p+point(s['dt'])*vn;increments.append(dv);p,v,force=pn,vn,fn
        positions.append(p);velocities.append(v)
        history.append({'tick':k+1,'position':p.wire(),'velocity':v.wire(),'force':force.wire(),'pending_targets':[x.wire() for x in queue]})
    return {'delay':delay,'remaining_power_cut_tick':cut,'history':history,
      'finite_containment':all(p.inside(s['safe_position']) for p in positions),
      'terminal_samples':all(v.inside(s['terminal_velocity']) for v in velocities[-s['terminal_samples']:])}


def assess_state(model,actuator_state,*,evidence_status,measurement_bounds_asserted,
                 actuator_model_asserted,power_bounds_asserted,actuator_state_bounds_asserted,linked=True):
    result={'model_status':'NOT_ASSESSED','conclusion':'UNKNOWN_INPUT','evidence_status':evidence_status,
      'finite_horizon_containment':None,'terminal_sample_condition':None,'branches':[],
      'future_position_containment':'NOT_ESTABLISHED','operational_authorization':False,'registered_criterion':False,
      'scope':'DECLARED_SAMPLED_1D_MODEL_ONLY','power_timing':'CUT_TICKS_RELATIVE_TO_ASSESSMENT_EPOCH',
      'numerical_method':'EXACT_RATIONAL_MODEL_ENCLOSURE_NOT_FORMALLY_VERIFIED_SOFTWARE'}
    try:
        if evidence_status not in ('COMPATIBLE_UNDER_ASSERTED_BOUNDS','CONTRADICTORY','UNKNOWN'):raise ValueError('invalid evidence status')
        flags=(measurement_bounds_asserted,actuator_model_asserted,power_bounds_asserted,actuator_state_bounds_asserted)
        if any(type(x) is not bool for x in flags) or type(linked) is not bool:raise ValueError('explicit boolean assumptions required')
        s=spec(model);f,queues=snapshot(actuator_state,s)
        for d,queue in queues.items():
            for cut in s['cuts']:result['branches'].append(propagate(s,d,cut,f,queue,linked=linked))
        contained=all(b['finite_containment'] for b in result['branches']);terminal=all(b['terminal_samples'] for b in result['branches'])
        result.update(finite_horizon_containment=contained,terminal_sample_condition=terminal,
          model_status='CONDITIONAL_FINITE_CONTAINMENT_AND_TERMINAL_SAMPLES' if contained and terminal else 'CONDITIONAL_FINITE_CONTAINMENT_ONLY' if contained else 'NOT_ESTABLISHED_ENCLOSURE_EXITS_SAFE_SET',
          snapshot_mode=actuator_state['mode'],assessment_tick=actuator_state['assessment_tick'],
          initial_force=f.wire(),initial_pending_by_delay={str(d):[x.wire() for x in q] for d,q in queues.items()})
        if evidence_status=='CONTRADICTORY':result['conclusion']='CONTRADICTORY_EVIDENCE'
        elif evidence_status=='UNKNOWN':result['conclusion']='UNKNOWN_EVIDENCE'
        elif not all(flags):result['conclusion']='UNKNOWN_PHYSICAL_PREMISES'
        elif contained and terminal:result['conclusion']='SUPPORTED_FINITE_MODEL_STATEMENT_ONLY'
        else:result['conclusion']='NOT_ESTABLISHED_BY_THIS_ENCLOSURE'
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
        result.update(model_status='UNSUPPORTED_INPUT_OR_SNAPSHOT',conclusion='UNKNOWN_INPUT',reason=str(exc))
    return result


def remaining_cut_window(absolute_cut_ticks,assessment_tick):
    """Translate a declared absolute cutoff window; never reset spent duration.

    Pure epoch arithmetic, not authentication of the deadline/power source.
    An already elapsed cutoff maps to zero remaining powered ticks.
    """
    if type(assessment_tick) is not int or assessment_tick<0:raise ValueError('invalid assessment epoch')
    if not isinstance(absolute_cut_ticks,list) or len(absolute_cut_ticks)!=2 or any(type(x) is not int or x<0 for x in absolute_cut_ticks) or absolute_cut_ticks[0]>absolute_cut_ticks[1]:raise ValueError('invalid absolute cutoff window')
    return [max(0,x-assessment_tick) for x in absolute_cut_ticks]
