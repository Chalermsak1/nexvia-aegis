"""One-dimensional static-boundary DEVELOPMENT reference only.

All bounds are caller assertions, not sensor estimates authenticated by this
module. Clearance already accounts for footprint and any required reserve.
No multidimensional, aerial, contact, controller or physical-safety guarantee.
"""
from dataclasses import dataclass
import math


ASSUMPTIONS = (
    'One-dimensional approach to a static boundary; clearance is a lower bound after footprint/reserve deductions.',
    'Initial nonnegative approach speed is upper bounded by the supplied speed.',
    'Total detection/decision/switch/actuation delay is upper bounded by the supplied delay.',
    'Total net acceleration toward the boundary during delay is at most the supplied outward acceleration bound.',
    'After delay, opposing disturbance is bounded and guaranteed braking remains available until approach speed reaches zero.',
    'No additional jerk, ramp-up, saturation, mode switching, moving obstacles, estimation error or contact dynamics outside these supplied bounds.',
    'Computed floating-point values are a development reference, not interval-certified numerics or verified real-world bounds.',
)


@dataclass(frozen=True)
class EnvelopeResult:
    classification: str
    delay_travel_m: float | None
    braking_travel_m: float | None
    total_travel_bound_m: float | None
    speed_after_delay_bound_m_s: float | None
    net_braking_m_s2: float
    clearance_margin_m: float | None
    bound_satisfied: bool | None
    assumptions: tuple[str, ...] = ASSUMPTIONS


def nonnegative(value, name):
    if type(value) not in (int, float):
        raise ValueError(name + ' must be a finite numeric scalar, not bool')
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or value < 0:
        raise ValueError(name + ' must be finite and nonnegative')
    return float(value)


def evaluate(*, approach_speed_upper_m_s, clearance_lower_m, total_delay_upper_s,
             outward_acceleration_upper_m_s2, braking_deceleration_lower_m_s2,
             opposing_disturbance_upper_m_s2):
    v = nonnegative(approach_speed_upper_m_s, 'approach speed')
    clearance = nonnegative(clearance_lower_m, 'clearance')
    delay = nonnegative(total_delay_upper_s, 'total delay')
    acceleration = nonnegative(outward_acceleration_upper_m_s2, 'outward acceleration')
    braking = nonnegative(braking_deceleration_lower_m_s2, 'braking deceleration')
    disturbance = nonnegative(opposing_disturbance_upper_m_s2, 'opposing disturbance')
    net = braking - disturbance
    if net <= 0:
        return EnvelopeResult('UNSUPPORTED_NO_POSITIVE_NET_BRAKING', None, None, None, None, net, None, None)
    # The supplied delay acceleration is a TOTAL bound; do not add disturbance
    # again during delay. Disturbance reduces the guaranteed braking here.
    speed_after = v + acceleration * delay
    delay_travel = v * delay + .5 * acceleration * delay * delay
    braking_travel = .5 * speed_after * (speed_after / net)
    total = delay_travel + braking_travel
    if (not all(math.isfinite(x) for x in (speed_after, delay_travel, braking_travel, total)) or
            (speed_after > 0 and braking_travel == 0) or
            (delay > 0 and (v > 0 or acceleration > 0) and delay_travel == 0) or
            (acceleration > 0 and delay > 0 and acceleration * delay == 0)):
        return EnvelopeResult('UNSUPPORTED_NUMERIC_RANGE', None, None, None, None, net, None, None)
    satisfied = total <= clearance
    return EnvelopeResult('BOUND_SATISFIED_UNDER_ASSUMPTIONS' if satisfied else 'BOUND_NOT_SATISFIED',
                          delay_travel, braking_travel, total, speed_after, net, clearance - total, satisfied)
