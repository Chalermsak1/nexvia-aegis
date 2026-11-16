"""Conditional path-length reference for a hypothetical passive damper.

No guarantee of finite-time rest, obstacle avoidance, physical availability or
sensor accuracy. Any persistent nonzero disturbance allowance prevents this
module from bounding INFINITE-HORIZON displacement by a finite value.
"""
import math
from .bounded_braking import scalar


def passive_path_reference(*, speed_upper_m_s, delay_upper_seconds, mass_kg,
                           damping_lower_kg_s, persistent_force_upper_n, available):
    if type(available) is not bool:
        raise ValueError('available must be boolean')
    v = scalar(speed_upper_m_s, 'speed upper')
    delay = scalar(delay_upper_seconds, 'delay')
    mass = scalar(mass_kg, 'mass', positive=True)
    damping = scalar(damping_lower_kg_s, 'damping')
    force = scalar(persistent_force_upper_n, 'persistent force')
    result = {'classification': None, 'additional_path_upper_m': None,
              'finite_time_rest_claim': False, 'speed_upper_m_s': v,
              'delay_upper_seconds': delay, 'mass_kg': mass,
              'damping_lower_kg_s': damping, 'persistent_force_upper_n': force,
              'assumptions': ['Initial true speed is bounded by the supplied upper bound.',
                              'Zero incremental commanded force after the request; ideal gravity compensation.',
                              'Constant free mass; no contact or other unmodeled forces.',
                              'After a coast-only bounded delay, passive damping >= supplied coefficient remains available.',
                              'Zero persistent disturbance allowance is required for this finite infinite-horizon path bound.',
                              'Ordinary floating-point development reference, not outward-rounded interval verification.']}
    if not available or damping == 0:
        result['classification'] = 'UNSUPPORTED_FALLBACK_UNAVAILABLE'
    elif force > 0:
        # A constant force of this magnitude is admissible: terminal speed F/c>0,
        # so total future travel diverges. Finite-horizon bounds are a different API.
        result['classification'] = 'UNSUPPORTED_PERSISTENT_DISTURBANCE'
    else:
        bound = v * delay + mass * v / damping
        if not math.isfinite(bound) or (v > 0 and bound == 0):
            result['classification'] = 'UNSUPPORTED_NUMERIC_RANGE'
        else:
            result.update(classification='CONDITIONAL_ASYMPTOTIC_PATH_BOUND', additional_path_upper_m=bound)
    return result
