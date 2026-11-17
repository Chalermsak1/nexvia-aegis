"""Separate ideal held-net-force physical segment diagnostic, not an authorizer.

Exact extrema over elapsed time and interval p/v/constant acceleration. Does not
turn a semi-implicit sampled certificate into a continuous-time invariant proof.
"""
from .recovery_feedback_state_1d import _number, _bounds
from .recovery_envelope_1d import internal, point

DYNAMICS_ID='CONSTANT_NET_FORCE_ZOH_WORLD_X_SI_V1'


def segment(*,position,velocity,force,mass,dt,disturbance,safe_position,dynamics_id):
    out=dict(status='UNKNOWN_HELD_FORCE_INPUT',dispatch=False,operational_authorization=False,
             hardware_validation=False,gate_b='GATE_B_NOT_AUTHORIZED',
             continuous_segment_containment=False,composed_future_containment=False,dynamics_id=DYNAMICS_ID)
    try:
        if dynamics_id!=DYNAMICS_ID:return dict(out,reason='DYNAMICS_MODEL_MISMATCH')
        p,v,f,m,safe=[_bounds(x) for x in (position,velocity,force,mass,safe_position)]
        h,D=_number(dt),_number(disturbance)
        if h<=0 or D<0 or m.lo<=0:raise ValueError('positive duration/mass and nonnegative disturbance required')
        a=(f+internal(-D,D)).divide_positive(m)
        lower_times=[point(0).lo,h];upper_times=list(lower_times)
        if a.lo:
            t=-v.lo/a.lo
            if 0<t<h:lower_times.append(t)
        if a.hi:
            t=-v.hi/a.hi
            if 0<t<h:upper_times.append(t)
        low=min(p.lo+t*v.lo+t*t*a.lo/2 for t in lower_times)
        high=max(p.hi+t*v.hi+t*t*a.hi/2 for t in upper_times)
        path=internal(low,high);end=p+point(h)*v+point(h*h/2)*a
        sampled=p+point(h)*(v+point(h)*a)
        return dict(out,status='CONDITIONAL_HELD_FORCE_SEGMENT',acceleration=a.wire(),
                    continuous_position=path.wire(),physical_endpoint=end.wire(),
                    semi_implicit_endpoint=sampled.wire(),same_held_acceleration_endpoint_defect=(point(h*h/2)*a).wire(),
                    continuous_segment_containment=path.inside(safe),
                    physical_endpoints_contained=p.inside(safe) and end.inside(safe),
                    candidate_extremum_times=sorted({str(t) for t in lower_times+upper_times}),
                    assumptions='CONSTANT_MASS_AND_HELD_NET_FORCE_PER_SEGMENT_NO_CONTACT_OR_IMPULSE',reason=None)
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError,AttributeError) as exc:
        return dict(out,reason=str(exc))
