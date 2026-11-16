"""Finite sampled-window design check for a SIMULATION brake diagnostic.

No operational authorization or post-window recoverability is supplied. The
unknown probe effect is budgeted as an arbitrary bounded force, including wrong
sign; no braking credit is taken. Initial/reference/map/force bounds are caller
assumptions, not independently authenticated hardware facts.
"""
import math
from .bounded_braking import scalar, vector
from .sampled_motion_reference import sampled_motion_reference


def brake_probe_window(reference, geometry, *, delay_ticks=3, pulse_ticks=2, feedback_ticks=1,
                       dt_seconds=.02, mass_lower_kg=1., cap_per_axis_n=1., disturbance_upper_n=0.):
    result = {'design_status': None, 'operational_authorization': False, 'post_window_recoverability_established': False,
              'clearance_lower_m': None, 'sampled_path_upper_m': None, 'window_ticks': None}
    try:
        if reference['status'] != 'CONDITIONAL_REFERENCE': raise ValueError('REFERENCE_UNAVAILABLE')
        if any(type(x) is not int or x < 0 for x in (delay_ticks,pulse_ticks,feedback_ticks)) or pulse_ticks == 0: raise ValueError('INVALID_WINDOW')
        pos,vel = vector(reference['position']),vector(reference['velocity'])
        ep=scalar(reference['position_error_m'],'position radius');ev=scalar(reference['velocity_error_m_s'],'velocity radius')
        radius=scalar(geometry['robot_radius'],'robot radius',positive=True);arena=scalar(geometry['arena_limit'],'arena',positive=True)
        cap=scalar(cap_per_axis_n,'cap',positive=True);d=scalar(disturbance_upper_n,'disturbance')
        limit=arena-radius
        clearances=[pos[2]-radius,limit-pos[2],limit-abs(pos[0]),limit-abs(pos[1])]
        for obstacle in geometry['obstacles']:
            center=vector(obstacle['center']);r=scalar(obstacle['radius'],'obstacle radius')
            clearances.append(math.hypot(*(x-y for x,y in zip(pos,center)))-radius-r)
        lower=min(clearances)-ep
        n=delay_ticks+pulse_ticks+feedback_ticks
        bound=sampled_motion_reference(initial_speed_upper_m_s=math.hypot(*vel)+ev,steps=n,dt_seconds=dt_seconds,
              mass_lower_kg=mass_lower_kg,command_force_upper_n=math.sqrt(3)*cap,
              disturbance_force_upper_n=d,damping_gain_upper_kg_s=0.)
        if not math.isfinite(lower) or bound['sampled_path_upper_m'] is None:raise ValueError('UNSUPPORTED_NUMERIC_OR_MODEL_RANGE')
        travel=bound['sampled_path_upper_m']
        result.update(design_status='WITHIN_ASSERTED_SAMPLED_WINDOW' if lower>travel else 'DECLINED_CLEARANCE_BOUND',
             clearance_lower_m=lower,sampled_path_upper_m=travel,window_ticks=n,
             force_norm_budget_n=math.sqrt(3)*cap,reference_assumptions=bound['assumptions'])
    except (ValueError,TypeError,OverflowError,KeyError) as exc:
        result.update(design_status='UNSUPPORTED',reason=str(exc))
    return result
