"""Conditional ideal physical-time ZOH recovery; not a hardware/RT certificate.

Held backup force, fixed sample period, piecewise constant positive mass/k/c,
bounded disturbance, no impulse/contact. Clock/measurement/trigger assertions are
external premises. Keeps fractional mapped times. No physical dispatch.
"""
from itertools import product
from math import isqrt
from fractions import Fraction as Q
from .passive_backup_supervisor_1d import model,energy_box,_quad,_wire
from .recovery_feedback_state_1d import _number,_bounds,_fields,_label
from .recovery_envelope_1d import internal,point

DYNAMICS_ID='IDEAL_ZOH_BACKUP_WORLD_X_SI_V1'
PREMISES='state_bounds_asserted parameter_bounds_asserted clock_map_asserted active_cap_asserted backup_model_asserted backup_timing_asserted independent_handoff_asserted power_independent_backup_asserted no_impulse_handoff_asserted'


def sqrt_upper(x):
    if x<0:raise ValueError('negative square root')
    scale=10**12;n=isqrt(x.numerator*scale*scale//x.denominator)
    if n*n*x.denominator<x.numerator*scale*scale:n+=1
    return Q(n,scale)


def certificate(backup,parameter_bounds):
    out=dict(status='PHYSICAL_MODEL_NOT_ESTABLISHED',conditional_continuous_containment=False,
             operational_authorization=False,hardware_validation=False,dynamics_id=DYNAMICS_ID)
    try:
        s=model(backup);_fields(parameter_bounds,'mass spring damping');f={k:_bounds(v) for k,v in parameter_bounds.items()}
        if any(v.lo<=0 or not v.contains(s[k]) for k,v in f.items()):raise ValueError('positive family containing nominal reference required')
        h,m,k,c,L,V=[s['dt'],f['mass'],f['spring'],f['damping'],s['position_scale'],s['velocity_scale']]
        km,cm=k.divide_positive(m),c.divide_positive(m)
        A=((point(1)-point(h*h/2)*km,point(h*V/L)*(point(1)-point(h/2)*cm)),(-point(h*L/V)*km,point(1)-point(h)*cm))
        P=s['P'];S=[]
        for i in range(2):
            row=[]
            for j in range(2):
                value=point(0)
                for u,v in product(range(2),repeat=2):value=value+A[u][i]*point(P[u][v])*A[v][j]
                row.append(point(P[i][j])-value)
            S.append(row)
        cross=max(abs(x) for i,j in ((0,1),(1,0)) for x in (S[i][j].lo,S[i][j].hi));eta=min(S[0][0].lo-cross,S[1][1].lo-cross)
        rho=1-eta/(2*s['trace']) if 0<eta<=s['trace'] else None
        # Arbitrarily varying bounded disturbance during a sample: independent
        # integral error bounds, rather than one fictitious common average.
        up=h*h*s['disturbance']/(2*m.lo*L);uv=h*s['disturbance']/(m.lo*V)
        beta=max(_quad(P,a,b) for a,b in product((-up,up),(-uv,uv)))
        minimum=beta/(1-rho)**2 if rho is not None else None
        force2=s['level']*max(_quad(s['inverse'],a*L,b*V) for a,b in product((k.lo,k.hi),(c.lo,c.hi)))
        radius=sqrt_upper(s['position_bound_squared'])+h*sqrt_upper(s['velocity_bound_squared'])+h*h*(s['force_cap']+s['disturbance'])/(2*m.lo)
        margin=min(s['anchor']-s['safe_position'].lo,s['safe_position'].hi-s['anchor'])
        checks=dict(common_sample_contraction=rho is not None,disturbance_level=minimum is not None and s['level']>=minimum,
                    backup_cap=force2<=s['force_cap']**2,all_segment_position_projection=margin>=radius)
        ok=all(checks.values())
        return dict(out,status='CONDITIONAL_IDEAL_PHYSICAL_INVARIANT' if ok else 'PHYSICAL_MODEL_NOT_ESTABLISHED',conditional_continuous_containment=ok,
                    checks=checks,P=_wire(P),A_enclosure=[[x.wire() for x in row] for row in A],
                    residual_enclosure=[[x.wire() for x in row] for row in S],uniform_decay_lower=str(eta),
                    contraction_upper=None if rho is None else str(rho),disturbance_integral_norm_squared_upper=str(beta),
                    minimum_level=None if minimum is None else str(minimum),backup_force_bound_squared=str(force2),
                    intersample_radius_upper=str(radius),reason=None if ok else 'SUFFICIENT_IDEAL_MODEL_TEST_NOT_ESTABLISHED')
    except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError,AttributeError) as e:return dict(out,reason=str(e))


def transport(p,v,acceleration,lo,hi):
    """All elapsed times in [lo,hi], and any acceleration within symmetric bounds."""
    if not 0<=lo<=hi or acceleration<0:raise ValueError('ordered nonnegative time/acceleration')
    # Lower polynomial is concave, upper convex: extrema for position at time
    # in this interval lie at the interval endpoints for these symmetric bounds.
    low=min(p.lo+t*v.lo-t*t*acceleration/2 for t in (lo,hi))
    high=max(p.hi+t*v.hi+t*t*acceleration/2 for t in (lo,hi))
    return internal(low,high),internal(v.lo-hi*acceleration,v.hi+hi*acceleration)


def mapped_state(packet,clock_map,*,now_local,units_per_second,max_age,active_force_cap,mass,disturbance,local_epoch):
    _fields(packet,'remote_time local_epoch remote_epoch frame position velocity source_id')
    _label(packet['source_id']);scale=_number(units_per_second);limit=_number(max_age)
    if type(now_local) is not int or not 0<=now_local<2**63 or scale<=0 or limit<0:raise ValueError('explicit valid local clock/scale/age bound')
    if packet['local_epoch']!=local_epoch or packet['frame']!='WORLD_X_SI':raise ValueError('local epoch/frame mismatch')
    mapped=clock_map.map_event(packet['remote_time'],local_epoch=local_epoch,remote_epoch=packet['remote_epoch'])
    if mapped['status']!='CONDITIONAL_INTERVAL_MAPPING':raise ValueError('clock mapping unavailable: '+mapped['status'])
    times=_bounds(mapped['local_interval']);lo=(now_local-times.hi)/scale;hi=(now_local-times.lo)/scale
    if lo<0 or hi>limit:raise ValueError('future/stale mapped observation interval')
    p,v=_bounds(packet['position']),_bounds(packet['velocity'])
    acc=(active_force_cap+disturbance)/mass.lo;p,v=transport(p,v,acc,lo,hi)
    return dict(position=p,velocity=v,local_interval=times.wire(),age_seconds=[str(lo),str(hi)],clock_result=mapped)


def assess(backup,parameter_bounds,packet,clock_map,*,now_local,units_per_second,max_state_age_seconds,
           local_epoch,boot_id,active_force_cap,handoff_delay_seconds,monitor_seconds,premises,primary_healthy,dynamics_id):
    out=dict(status='UNRESOLVED_PHYSICAL_TIME_RESPONSE',development_action=None,dispatch=False,operational_authorization=False,
             hardware_validation=False,gate_b='GATE_B_NOT_AUTHORIZED',conditional_continuous_containment=False,boot_id=boot_id,dynamics_id=DYNAMICS_ID)
    try:
        _label(boot_id);_label(local_epoch)
        if dynamics_id!=DYNAMICS_ID:raise ValueError('physical dynamics mismatch')
        _fields(premises,PREMISES)
        if any(type(x) is not bool for x in premises.values()) or not all(premises.values()):raise ValueError('unestablished physical/clock/trigger premise')
        if type(primary_healthy) is not bool:raise ValueError('explicit primary health assertion')
        proof=certificate(backup,parameter_bounds);out['backup_certificate']=proof
        if not proof['conditional_continuous_containment']:return dict(out,reason='BACKUP_PHYSICAL_CERTIFICATE_NOT_ESTABLISHED')
        s=model(backup);m=_bounds(parameter_bounds['mass']);cap=_number(active_force_cap)
        if cap<0:raise ValueError('nonnegative active cap')
        state=mapped_state(packet,clock_map,now_local=now_local,units_per_second=units_per_second,max_age=max_state_age_seconds,
                           active_force_cap=cap,mass=m,disturbance=s['disturbance'],local_epoch=local_epoch)
        delays=_bounds(handoff_delay_seconds);monitor=_number(monitor_seconds)
        if delays.lo<0 or monitor<=0:raise ValueError('nonnegative delay and positive monitor duration')
        p,v=state['position'],state['velocity'];acc=(cap+s['disturbance'])/m.lo
        def reserve(offset):
            endp,endv=transport(p,v,acc,offset+delays.lo,offset+delays.hi)
            path,_=transport(p,v,acc,Q(0),offset+delays.hi)
            return dict(supported=path.inside(s['safe_position']) and energy_box(s,endp,endv)<=s['level'],
                        path=path.wire(),handoff_position=endp.wire(),handoff_velocity=endv.wire(),lyapunov_upper=str(energy_box(s,endp,endv)))
        current,future=reserve(Q(0)),reserve(monitor)
        out.update(mapped_time_interval=state['local_interval'],age_seconds=state['age_seconds'],transported_position=p.wire(),transported_velocity=v.wire(),
                   current_reserve=current,future_reserve=future,primary_role='PERMISSIVENESS_ONLY_NOT_A_PHYSICAL_RECOVERY_PROOF')
        if not current['supported']:return dict(out,reason='CURRENT_PHYSICAL_HANDOFF_UNSUPPORTED')
        return dict(out,status='CONDITIONAL_PHYSICAL_TIME_PLAN',development_action='CONTINUE' if primary_healthy and future['supported'] else 'HANDOFF',
                    conditional_continuous_containment=True,reason=None)
    except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError,AttributeError) as e:return dict(out,reason=str(e))
