"""Conservative finite-horizon bound for the new sampled sliding-mass model.

No braking credit: the clipped damping map must be nonexpansive. Bounds on
initial speed, mass and external force are caller assertions. No contact,
trajectory feasibility, true rest or physical calibration is established here.
"""
import math
from .bounded_braking import scalar


def sampled_motion_reference(*, initial_speed_upper_m_s, steps, dt_seconds, mass_lower_kg,
                             command_force_upper_n, disturbance_force_upper_n, damping_gain_upper_kg_s):
    if type(steps) is not int or steps < 0: raise ValueError('steps must be a nonnegative integer')
    s = scalar(initial_speed_upper_m_s, 'speed')
    dt = scalar(dt_seconds, 'dt', positive=True)
    mass = scalar(mass_lower_kg, 'mass', positive=True)
    u = scalar(command_force_upper_n, 'command')
    d = scalar(disturbance_force_upper_n, 'disturbance')
    c = scalar(damping_gain_upper_kg_s, 'gain')
    result = {'classification': None, 'sampled_path_upper_m': None, 'sampled_speed_upper_m_s': None,
              'steps': steps, 'dt_seconds': dt, 'braking_credit': False,
              'assumptions': ['Known upper initial speed and commanded/external force norms; positive lower actual mass.',
                              'Semi-implicit position update; explicit clipped per-axis damping; gain*dt/mass <= 1.',
                              'No contact or other unbounded forces. Gravity-compensation error must be included in external force.',
                              'Sampled path only; not a between-sample collision or safe-stop certificate.',
                              'Caller assertions and ordinary floating point, not authenticated/interval-certified bounds.']}
    try:
        contraction = c * dt / mass
        acceleration = (u + d) / mass
        speed = s + steps * dt * acceleration
        path = steps * dt * s + .5 * acceleration * dt * dt * steps * (steps + 1)
    except OverflowError:
        result['classification'] = 'UNSUPPORTED_NUMERIC_RANGE'; return result
    if not all(math.isfinite(v) for v in (contraction, acceleration, speed, path)):
        result['classification'] = 'UNSUPPORTED_NUMERIC_RANGE'
    elif (u + d > 0 and acceleration == 0) or (steps > 0 and s > 0 and steps * dt * s == 0):
        result['classification'] = 'UNSUPPORTED_NUMERIC_RANGE'
    elif contraction > 1:
        result['classification'] = 'UNSUPPORTED_DAMPING_STEP'
    else:
        result.update(classification='CONDITIONAL_SAMPLED_HORIZON_BOUND', sampled_path_upper_m=path, sampled_speed_upper_m_s=speed)
    return result
