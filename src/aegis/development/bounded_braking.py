"""Estimate-only braking diagnostic with caller-asserted Euclidean error balls.

No simulator/environment/CBF access. A bound is an assumption, not a covariance,
calibration result or authenticated sensor guarantee. NO_COMMAND is an interface
failure, not an implemented physical fallback. Ordinary floating-point arithmetic
is not a formally verified interval implementation.
"""
from dataclasses import dataclass
import math


def scalar(value, name, *, positive=False):
    if type(value) not in (int, float):
        raise ValueError(name + ': finite numeric scalar required')
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError(name + ': numeric range') from exc
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(name + ': invalid range')
    return value


def vector(value):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError('vector must contain three finite numeric components')
    result = []
    for x in value:
        if type(x) not in (int, float):
            raise ValueError('invalid vector component')
        try:
            x = float(x)
        except OverflowError as exc:
            raise ValueError('vector numeric range') from exc
        if not math.isfinite(x):
            raise ValueError('nonfinite vector')
        result.append(x)
    return tuple(result)


@dataclass(frozen=True)
class BoundedStatePacket:
    position: object
    velocity: object
    position_error_m: object
    velocity_error_m_s: object
    sequence: object
    acquired_seconds: object
    frame: object
    source: object
    bound_basis: object


@dataclass(frozen=True)
class PropagatedState:
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    position_error_m: float
    velocity_error_m_s: float
    age_seconds: float
    sequence: int
    acquired_seconds: float
    now_seconds: float
    frame: str
    source: str
    bound_basis: str


class BoundedStateGate:
    """Single-session, monotone input contract. Any rejection latches this gate.

    Transport under ||acceleration|| <= A and simultaneous measurement errors:
    p_c = p_m + v_m*age; r_p = e_p + e_v*age + A*age**2/2;
    v_c = v_m; r_v = e_v + A*age. No extrapolated acceleration estimate.
    Both position and velocity MUST share acquisition time/frame/source.
    """
    def __init__(self, *, max_age_seconds, acceleration_norm_upper_m_s2,
                 frame='WORLD', source='SIM_STATE_SENSOR_V1'):
        self.max_age = scalar(max_age_seconds, 'maximum age')
        self.acceleration = scalar(acceleration_norm_upper_m_s2, 'acceleration')
        if not isinstance(frame, str) or not frame.strip() or not isinstance(source, str) or not source.strip():
            raise ValueError('frame and source must be nonempty')
        self.frame, self.source = frame, source
        self.last_sequence = self.last_acquired = self.last_now = None
        self.failure = None

    def accept(self, packet, *, now_seconds):
        if self.failure is not None:
            return None, 'LATCHED:' + self.failure
        try:
            now = scalar(now_seconds, 'now')
            if not isinstance(packet, BoundedStatePacket):
                raise ValueError('MISSING_PACKET')
            if type(packet.sequence) is not int or packet.sequence < 0:
                raise ValueError('INVALID_SEQUENCE')
            acquired = scalar(packet.acquired_seconds, 'acquisition time')
            if packet.frame != self.frame or packet.source != self.source:
                raise ValueError('FRAME_OR_SOURCE_MISMATCH')
            if not isinstance(packet.bound_basis, str) or not packet.bound_basis.strip():
                raise ValueError('MISSING_BOUND_BASIS')
            if acquired > now:
                raise ValueError('FUTURE_PACKET')
            if (self.last_now is not None and (now < self.last_now or acquired < self.last_acquired
                                             or packet.sequence <= self.last_sequence)):
                raise ValueError('REPLAY_OR_CLOCK_REGRESSION')
            age = now - acquired
            if age > self.max_age:
                raise ValueError('STALE_PACKET')
            p, v = vector(packet.position), vector(packet.velocity)
            ep = scalar(packet.position_error_m, 'position error')
            ev = scalar(packet.velocity_error_m_s, 'velocity error')
            rp = ep + ev * age + 0.5 * self.acceleration * age * age
            rv = ev + self.acceleration * age
            pc = tuple(x + y * age for x, y in zip(p, v))
            if not all(math.isfinite(x) for x in (*pc, rp, rv)):
                raise ValueError('PROPAGATION_NUMERIC_RANGE')
            # Detect erased positive transport increments at floating point limits.
            if age > 0 and self.acceleration > 0 and self.acceleration * age == 0:
                raise ValueError('PROPAGATION_NUMERIC_UNDERFLOW')
            estimate = PropagatedState(pc, v, rp, rv, age, packet.sequence, acquired,
                                       now, self.frame, self.source, packet.bound_basis)
        except (ValueError, TypeError, OverflowError) as exc:
            self.failure = str(exc) or type(exc).__name__
            return None, self.failure
        self.last_sequence, self.last_acquired, self.last_now = packet.sequence, acquired, now
        return estimate, 'ACCEPTED_UNDER_ASSERTED_BOUNDS'


def braking_command(estimate, *, force_norm_limit_n, use_uncertainty=True,
                    hold_seconds=0., mass_kg=1.):
    """Full-norm braking proposal; no obstacle-avoidance or stopping claim.

    For v in B(v_c,r_v), max f.dot(v) = f.dot(v_c)+||f||r_v.
    The bounded arm requires a strictly negative maximum. It refuses a direction
    that could accelerate a velocity in the ball. The point baseline deliberately
    ignores the radius; both arms still require the same validated input contract.
    For a positive hold time, additionally require an ideal constant-force
    kinetic-energy bound < 0. This assumes known mass and no unmodeled force or
    contact during that interval; it is not a platform safety certificate.
    Zero/rejected commands do not prove physical rest and must remain unevaluable.
    """
    hold = scalar(hold_seconds, 'command hold time')
    mass = scalar(mass_kg, 'mass', positive=True)
    limit = scalar(force_norm_limit_n, 'force limit', positive=True)
    if type(use_uncertainty) is not bool:
        raise ValueError('use_uncertainty must be bool')
    if estimate is None:
        return {'status': 'NO_COMMAND', 'reason': 'NO_ACCEPTED_ESTIMATE', 'force_n': None,
                'worst_case_power_w': None}
    if not isinstance(estimate, PropagatedState):
        raise ValueError('validated propagated state required')
    # Revalidate value fields: dataclasses alone do not enforce their annotations.
    v = vector(estimate.velocity)
    radius = scalar(estimate.velocity_error_m_s, 'velocity radius')
    speed = math.hypot(*v)
    if not math.isfinite(speed):
        return {'status': 'NO_COMMAND', 'reason': 'NUMERIC_RANGE', 'force_n': None,
                'worst_case_power_w': None}
    if speed == 0 or (use_uncertainty and speed <= radius):
        return {'status': 'NO_COMMAND', 'reason': 'DIRECTION_UNRESOLVED', 'force_n': None,
                'worst_case_power_w': None}
    force = tuple(-limit * (x / speed) for x in v)
    try:
        upper = math.fsum(x * y for x, y in zip(force, v)) + math.hypot(*force) * radius
    except (OverflowError, ValueError):
        upper = math.nan
    if not all(math.isfinite(x) for x in (*force, upper)) or (use_uncertainty and upper >= 0):
        return {'status': 'NO_COMMAND', 'reason': 'POWER_BOUND_UNSUPPORTED', 'force_n': None,
                'worst_case_power_w': None}
    # Exact finite-hold kinetic-energy change for an ideal constant-force mass,
    # with no unmodeled force/contact. A dissipative instantaneous command alone
    # can overshoot zero and ADD kinetic energy before the next control tick.
    try:
        energy_upper = (hold * upper + .5 * hold * hold * math.hypot(*force)**2 / mass) if hold else 0.
    except OverflowError:
        energy_upper = math.nan
    if not math.isfinite(energy_upper) or (use_uncertainty and hold > 0 and energy_upper >= 0):
        return {'status': 'NO_COMMAND', 'reason': 'HOLD_ENERGY_BOUND_UNSUPPORTED', 'force_n': None,
                'worst_case_power_w': upper, 'worst_case_hold_energy_change_j': energy_upper if math.isfinite(energy_upper) else None}
    return {'status': 'COMMAND_PROPOSED', 'reason': 'BOUNDED_DIRECTION' if use_uncertainty else 'POINT_BASELINE',
            'force_n': list(force), 'worst_case_power_w': upper,
            'worst_case_hold_energy_change_j': energy_upper, 'hold_seconds': hold, 'mass_kg': mass,
            'claim': 'INSTANTANEOUS_DISSIPATION_UNDER_ASSERTED_BOUNDS' if use_uncertainty else 'NO_BOUND_CLAIM'}
