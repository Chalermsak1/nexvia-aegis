"""Exact conservative positive-axis first-stop analysis, not a controller.

Declared lower brake force ramps in held samples after bounded delay. Adverse
force is bounded throughout; mass may vary in its interval. No impulses/contact.
Each trajectory is bounded only until its own first stop. Post-stop control,
opposite-direction motion and hardware force/power availability are NOT proved.
"""
from fractions import Fraction as Q
from .recovery_feedback_state_1d import _bounds,_number


def segment(p,v,a,duration):
    if duration<0:raise ValueError('nonnegative segment duration')
    times=[Q(0),duration]
    if a and 0<-v/a<duration:times.append(-v/a)
    values=[p+t*v+t*t*a/2 for t in times]
    return dict(position=p+duration*v+duration*duration*a/2,velocity=v+duration*a,minimum=min(values),maximum=max(values))


def analyze(*,position,velocity,mass,adverse_force_max,brake_force_min,delay_seconds,ramp_rate_min,sample_seconds,horizon_seconds,safe_position):
    p=_bounds(position);v=_bounds(velocity);m=_bounds(mass);safe=_bounds(safe_position)
    w,cap,delay,ramp,h,horizon=map(_number,(adverse_force_max,brake_force_min,delay_seconds,ramp_rate_min,sample_seconds,horizon_seconds))
    if m.lo<=0 or v.lo<0 or min(w,cap,delay,ramp)<0 or h<=0 or horizon<=0:raise ValueError('positive mass/time, outward velocity and nonnegative forces/delay/ramp required')
    if horizon/h>4096:raise ValueError('bounded development trace required')
    if delay>horizon:delay_end=horizon
    else:delay_end=delay
    now=Q(0);px=p.hi;vx=v.hi;rows=[];minimum=p.lo;maximum=p.hi;stopped=False
    def advance(duration,force,phase):
        nonlocal now,px,vx,minimum,maximum,stopped
        net=w-force;acc=net/(m.lo if net>=0 else m.hi)
        duration=min(duration,horizon-now)
        if acc<0 and vx+acc*duration<=0:duration=-vx/acc;stopped=True
        r=segment(px,vx,acc,duration)
        rows.append(dict(start_seconds=str(now),duration_seconds=str(duration),phase=phase,brake_force_lower=str(force),acceleration_upper=str(acc),position_upper_before=str(px),velocity_upper_before=str(vx),position_upper_after=str(r['position']),velocity_upper_after=str(r['velocity']),segment_position_upper=str(r['maximum'])))
        now+=duration;px=r['position'];vx=r['velocity'];maximum=max(maximum,r['maximum'])
    if vx==0 and w==0:stopped=True
    if delay_end and not stopped:advance(delay_end,Q(0),'DELAY')
    ramp_tick=0
    while now<horizon and not stopped:
        force=min(cap,ramp*ramp_tick*h)
        advance(h,force,'RAMP_OR_HOLD');ramp_tick+=1
    finite_contained=minimum>=safe.lo and maximum<=safe.hi
    worst_stop_possible=(cap>w and ramp>0) or (v.hi==0 and w==0)
    return dict(classification='CONDITIONAL_POSITIVE_AXIS_FIRST_STOP_CAPABILITY_ONLY',finite_trace_contained=finite_contained,
        stop_observed_in_bound=stopped,stopping_capability='FIRST_STOP_BOUNDED' if stopped else 'NO_WORST_CASE_STOPPING_CAPABILITY' if not worst_stop_possible else 'HORIZON_INCOMPLETE',
        first_stop_prefix_contained=finite_contained if stopped else None,stop_time_upper_seconds=str(now) if stopped else None,stop_position_upper=str(px) if stopped else None,
        simulated_until_seconds=str(now),finite_position_upper=str(maximum),initial_position_lower=str(p.lo),safe_position=safe.wire(),
        post_stop_containment='UNRESOLVED_REST_CONTROL_REQUIRED',full_trajectory_containment=None,dispatch=False,operational_authorization=False,hardware_validation=False,gate_b='GATE_B_NOT_AUTHORIZED',
        model_assumptions=['positive-axis until each trajectory first stops','known lower brake force including power availability','bounded delay and lower ramp rate','bounded adverse force and positive mass','no impulse/contact','held-sample brake lower bound; no post-stop guarantee'],segments=rows)
