"""DEVELOPMENT composition of interval parameters and sampled handoff reserve.

Only SEMI_IMPLICIT_WORLD_X_SI_V1. Discrete tick uncertainty is enumerated, not
rounded from arbitrary physical timestamps. No continuous-time claim, durable
executor, authentication or physical dispatch. Existing point artifacts unchanged.
"""
from .passive_backup_supervisor_1d import model, energy_box
from .uncertain_backup_certificate_1d import certificate
from .recovery_feedback_state_1d import _number, _bounds, _fields, _tick, _label
from .recovery_envelope_1d import internal, point, hull
from .runtime_readiness import select_response

DYNAMICS_ID = 'SEMI_IMPLICIT_WORLD_X_SI_V1'
PREMISES = ('state_bounds_asserted active_cap_asserted backup_model_asserted '
            'independent_handoff_asserted power_independent_backup_asserted '
            'no_impulse_handoff_asserted parameter_bounds_asserted clock_grid_asserted')


def bridge(reference, mass_bounds, position, velocity, steps, active_cap, disturbance):
    """Sampled prefix under arbitrary capped force, including carried/FIFO force."""
    if type(steps) is not int or not 0 <= steps <= 48:
        raise ValueError('bounded discrete bridge required')
    if mass_bounds.lo <= 0 or active_cap < 0 or disturbance < 0:
        raise ValueError('positive mass and nonnegative force bounds required')
    acceleration = internal(-(active_cap+disturbance)/mass_bounds.lo,
                             (active_cap+disturbance)/mass_bounds.lo)
    h = reference['dt']; rows = []
    for n in range(steps+1):
        p = position+point(n*h)*velocity+point(h*h*n*(n+1)/2)*acceleration
        v = velocity+point(n*h)*acceleration
        W = energy_box(reference,p,v)
        rows.append(dict(tick=n, position=p.wire(), velocity=v.wire(), lyapunov_upper=str(W),
                         in_backup_set=W <= reference['level'],
                         inside_safe_region=p.inside(reference['safe_position'])))
    return rows


def assess(backup, parameter_bounds, state, *, assessment_tick, boot_id, clock_id,
           active_force_cap, environment_force, handoff_delay_ticks, monitor_ticks,
           max_state_age_ticks, premises, primary, dynamics_id):
    """Offline plan; every age/delay alternative must support the conditional claim."""
    out = dict(status='UNRESOLVED_FAMILY_RESPONSE', development_action=None, dispatch=False,
               operational_authorization=False, hardware_validation=False,
               conditional_future_sampled_containment=False, intersample_containment=False,
               gate_b='GATE_B_NOT_AUTHORIZED', dynamics_id=DYNAMICS_ID)
    try:
        if dynamics_id != DYNAMICS_ID:
            return dict(out,reason='DYNAMICS_MODEL_MISMATCH')
        reference = model(backup); proof = certificate(backup,parameter_bounds)
        out['family_certificate'] = proof
        if not proof['conditional_sampled_invariance']:
            return dict(out,reason='FAMILY_INVARIANCE_NOT_ESTABLISHED')
        _fields(premises,PREMISES)
        if any(type(x) is not bool for x in premises.values()):
            raise ValueError('explicit boolean physical/parameter/clock premises required')
        if not all(premises.values()):
            return dict(out,reason='UNESTABLISHED_PHYSICAL_PARAMETER_OR_CLOCK_PREMISE')
        _fields(state,'boot_id clock_id frame epoch_tick_bounds position velocity source_id evidence_status')
        for x in (boot_id,clock_id,state['source_id']): _label(x)
        _tick(assessment_tick)
        if state['boot_id'] != boot_id: return dict(out,reason='BOOT_MISMATCH')
        if state['clock_id'] != clock_id or state['frame'] != 'WORLD_X_SI':
            return dict(out,reason='CLOCK_OR_FRAME_MISMATCH')
        if state['evidence_status'] != 'COMPATIBLE_UNDER_ASSERTED_BOUNDS':
            return dict(out,reason='NO_SUPPORTED_BACKUP_STATE')
        epochs = state['epoch_tick_bounds']
        if not isinstance(epochs,list) or len(epochs)!=2: raise ValueError('two discrete epoch bounds required')
        for x in epochs: _tick(x)
        if epochs[0] > epochs[1]: raise ValueError('epoch interval order')
        if type(max_state_age_ticks) is not int or not 0<=max_state_age_ticks<=16:
            raise ValueError('bounded explicit state age required')
        if epochs[1]>assessment_tick or assessment_tick-epochs[0]>max_state_age_ticks:
            return dict(out,reason='STATE_TIME_INTERVAL_UNSUPPORTED')
        if (not isinstance(handoff_delay_ticks,list) or len(handoff_delay_ticks)!=2
                or any(type(x) is not int or not 0<=x<=16 for x in handoff_delay_ticks)
                or handoff_delay_ticks[0]>handoff_delay_ticks[1]):
            raise ValueError('bounded discrete handoff interval required')
        if type(monitor_ticks) is not int or not 1<=monitor_ticks<=16:
            raise ValueError('bounded explicit monitoring interval required')
        cap, external = _number(active_force_cap), _number(environment_force)
        if cap<0 or external!=reference['disturbance']:
            raise ValueError('consistent persistent force bound required')
        mass = _bounds(parameter_bounds['mass']); p,v = _bounds(state['position']),_bounds(state['velocity'])
        ages = list(range(assessment_tick-epochs[1],assessment_tick-epochs[0]+1))
        transported = [bridge(reference,mass,p,v,n,cap,external)[-1] for n in ages]
        p = hull([_bounds(row['position']) for row in transported])
        v = hull([_bounds(row['velocity']) for row in transported])
        lo,hi = handoff_delay_ticks
        prefix = bridge(reference,mass,p,v,monitor_ticks+hi,cap,external)
        current = all(row['inside_safe_region'] for row in prefix[:hi+1]) and all(prefix[n]['in_backup_set'] for n in range(lo,hi+1))
        future = all(row['inside_safe_region'] for row in prefix) and all(prefix[n]['in_backup_set'] for n in range(monitor_ticks+lo,monitor_ticks+hi+1))
        out.update(current_handoff_supported=current, continued_operation_reserve_supported=future,
                   assessment_tick=assessment_tick, admissible_state_ages=ages,
                   transported_position=p.wire(), transported_velocity=v.wire(), bridge=prefix,
                   transport_hull_relaxes_time_state_correlation=True)
        if not current: return dict(out,reason='CURRENT_HANDOFF_OUTSIDE_CERTIFIED_REGION')
        ready = dict(status='NO_JUSTIFIED_RESPONSE',reason='PRIMARY_RESULT_UNAVAILABLE')
        if primary is not None:
            _fields(primary,'temporal deadline restart calibration')
            t = primary['temporal']
            ready = select_response(t,deadline=primary['deadline'],restart=primary['restart'],
                                    calibration=primary['calibration'],boot_id=boot_id,mode='DEVELOPMENT_SIMULATION')
            if ready['status']=='DEVELOPMENT_RECOVERY_CANDIDATE_ONLY':
                if t.get('assessment_tick')!=assessment_tick:
                    return dict(out,reason='PRIMARY_ASSESSMENT_EPOCH_MISMATCH')
                spec = t['preparation']['model']
                if (not mass.inside(_bounds(spec['mass'])) or _number(spec['dt'])!=reference['dt']
                        or _bounds(spec['cap']).hi>cap or _number(spec['disturbance'])<external
                        or _bounds(spec['safe_position'])!=reference['safe_position']):
                    return dict(out,reason='PRIMARY_FAMILY_PHYSICAL_COVERAGE_NOT_ESTABLISHED')
                for x,y in ((p,_bounds(spec['position'])),(v,_bounds(spec['velocity']))):
                    if max(x.lo,y.lo)>min(x.hi,y.hi):
                        return dict(out,reason='CONTRADICTORY_PRIMARY_AND_BACKUP_STATE')
        action = 'CONTINUE_WITH_FAMILY_RESERVE' if ready['status']=='DEVELOPMENT_RECOVERY_CANDIDATE_ONLY' and future else 'HANDOFF_TO_FAMILY_BACKUP'
        return dict(out,status='CONDITIONAL_FAMILY_DEVELOPMENT_PLAN',development_action=action,
                    conditional_future_sampled_containment=True,primary_decision=ready,reason=None)
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError,AttributeError) as exc:
        return dict(out,status='UNKNOWN_FAMILY_INPUT',reason=str(exc))


def check_step(backup, parameter_bounds, before, after, *, dynamics_id):
    """Necessary family-model consistency, never proof of identity or trajectory safety."""
    out = dict(status='UNKNOWN_FAMILY_OBSERVATION', operational_authorization=False,gate_b='GATE_B_NOT_AUTHORIZED')
    try:
        if dynamics_id!=DYNAMICS_ID: return dict(out,reason='DYNAMICS_MODEL_MISMATCH')
        if before is None or after is None:return dict(out,reason='MISSING_OBSERVATION')
        proof=certificate(backup,parameter_bounds)
        if not proof['conditional_sampled_invariance']:return dict(out,reason='UNESTABLISHED_FAMILY')
        s=model(backup);_fields(before,'position velocity');_fields(after,'position velocity')
        p,v=_bounds(before['position']),_bounds(before['velocity'])
        mass,spring,damping=[_bounds(parameter_bounds[k]) for k in ('mass','spring','damping')]
        force=-(spring*(p-point(s['anchor']))+damping*v);cap=s['force_cap']
        force=internal(max(-cap,min(cap,force.lo)),max(-cap,min(cap,force.hi)))
        acceleration=(force+internal(-s['disturbance'],s['disturbance'])).divide_positive(mass)
        vn=v+point(s['dt'])*acceleration;pn=p+point(s['dt'])*vn
        compatible=all(max(a.lo,b.lo)<=min(a.hi,b.hi) for a,b in ((pn,_bounds(after['position'])),(vn,_bounds(after['velocity']))))
        return dict(out,status='COMPATIBLE_UNDER_ASSERTED_FAMILY' if compatible else 'FAMILY_MODEL_OR_EVIDENCE_CONTRADICTION',
                    predicted_position=pn.wire(),predicted_velocity=vn.wire(),reason=None)
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError,AttributeError) as exc:
        return dict(out,reason=str(exc))
