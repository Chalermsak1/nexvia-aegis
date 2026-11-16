"""Conditional development references, never authenticated physical truth.

The reference uses a modeled world-frame interval-mean acceleration sensor and
an initial position/velocity anchor. This is not a raw hardware IMU estimator.
Bounds/frame/clock/calibration are caller assertions. Ordinary floating point
and interval consistency do not supply a probability, safety or rest guarantee.
"""
from dataclasses import dataclass
import math
from .bounded_braking import scalar, vector, BoundedStatePacket


def dot(a, b): return math.fsum(x * y for x, y in zip(a, b))


@dataclass(frozen=True)
class IntervalReading:
    kind: str
    start_tick: int
    end_tick: int
    value: object
    error_norm: object
    frame: str = 'WORLD'


def reading(sample, kind, tick):
    if type(tick) is not int or tick < 0: raise ValueError('READING_TICK')
    if not isinstance(sample, IntervalReading) or sample.kind != kind or sample.frame != 'WORLD': raise ValueError('READING_KIND_OR_FRAME')
    if type(sample.start_tick) is not int or type(sample.end_tick) is not int or sample.start_tick != tick or sample.end_tick != tick + 1: raise ValueError('READING_INTERVAL')
    return vector(sample.value), scalar(sample.error_norm, 'reading error')


class KinematicReference:
    def __init__(self, position, velocity, *, position_error_m, velocity_error_m_s, dt_seconds=.02):
        self.position, self.velocity = vector(position), vector(velocity)
        self.ep = scalar(position_error_m, 'anchor position error')
        self.ev = scalar(velocity_error_m_s, 'anchor velocity error')
        self.dt = scalar(dt_seconds, 'reference dt', positive=True)
        self.tick, self.failure = 0, None

    def snapshot(self):
        return {'status': 'UNSUPPORTED' if self.failure else 'CONDITIONAL_REFERENCE', 'reason': self.failure,
                'tick': self.tick, 'position': list(self.position), 'velocity': list(self.velocity),
                'position_error_m': self.ep, 'velocity_error_m_s': self.ev}

    def advance(self, sample):
        if self.failure: return self.snapshot()
        try:
            acc, error = reading(sample, 'ACCELERATION', self.tick)
            v = tuple(x + self.dt * a for x, a in zip(self.velocity, acc))
            ev = self.ev + self.dt * error
            p = tuple(x + self.dt * y for x, y in zip(self.position, v))
            ep = self.ep + self.dt * ev
            if not all(math.isfinite(x) for x in (*p, *v, ep, ev)): raise ValueError('REFERENCE_NUMERIC_RANGE')
            self.position, self.velocity, self.ep, self.ev = p, v, ep, ev
            self.tick += 1
        except (ValueError, TypeError, OverflowError) as exc:
            self.failure = str(exc) or type(exc).__name__
        return self.snapshot()


def state_consistency(packet, reference, *, tick, dt_seconds=.02):
    result = {'status': None, 'position_gap_m': None, 'position_allowance_m': None,
              'velocity_gap_m_s': None, 'velocity_allowance_m_s': None}
    try:
        if reference['status'] != 'CONDITIONAL_REFERENCE' or reference['tick'] != tick: raise ValueError('REFERENCE_UNAVAILABLE')
        if not isinstance(packet, BoundedStatePacket) or packet.frame != 'WORLD' or packet.acquired_seconds != tick * dt_seconds or type(packet.sequence) is not int or packet.sequence != tick: raise ValueError('STATE_TIME_OR_FRAME')
        p, v = vector(packet.position), vector(packet.velocity)
        ep, ev = scalar(packet.position_error_m, 'position error'), scalar(packet.velocity_error_m_s, 'velocity error')
        pg = math.hypot(*(x - y for x, y in zip(p, reference['position'])))
        vg = math.hypot(*(x - y for x, y in zip(v, reference['velocity'])))
        pa, va = ep + reference['position_error_m'], ev + reference['velocity_error_m_s']
        if not all(math.isfinite(x) for x in (pg, vg, pa, va)): raise ValueError('CONSISTENCY_NUMERIC_RANGE')
        result.update(status='INCONSISTENT' if pg > pa or vg > va else 'COMPATIBLE_UNDER_ASSERTED_BOUNDS',
                      position_gap_m=pg, position_allowance_m=pa, velocity_gap_m_s=vg, velocity_allowance_m_s=va)
    except (ValueError, TypeError, OverflowError, KeyError) as exc:
        result.update(status='UNSUPPORTED', reason=str(exc))
    return result


def command_energy_reference(force, reference, *, hold_seconds, mass_lower_kg, disturbance_upper_n):
    """Conservative held-command energy bound including a constant net disturbance.

    h*[f.vc+||f||r+D(||vc||+r)] + h²*(||f||+D)²/(2*m_min).
    No active fallback force is included: this is the command interval before
    fallback, with bounded net gravity/other force and no contact.
    """
    try:
        f = vector(force); h = scalar(hold_seconds, 'hold', positive=True)
        m = scalar(mass_lower_kg, 'mass', positive=True); d = scalar(disturbance_upper_n, 'disturbance')
        if reference['status'] != 'CONDITIONAL_REFERENCE': raise ValueError('REFERENCE_UNAVAILABLE')
        v = vector(reference['velocity']); r = scalar(reference['velocity_error_m_s'], 'velocity radius')
        upper_power = dot(f, v) + math.hypot(*f) * r + d * (math.hypot(*v) + r)
        energy = h * upper_power + .5 * h * h * ((math.hypot(*f) + d)**2) / m
        if not all(math.isfinite(x) for x in (upper_power, energy)): raise ValueError('ENERGY_NUMERIC_RANGE')
        return {'status': 'SUPPORTED_UNDER_ASSERTED_MODEL' if energy < 0 else 'UNSUPPORTED_ENERGY_DIRECTION',
                'total_power_upper_w': upper_power, 'hold_energy_upper_j': energy}
    except (ValueError, TypeError, OverflowError, KeyError) as exc:
        return {'status': 'UNSUPPORTED', 'reason': str(exc), 'total_power_upper_w': None, 'hold_energy_upper_j': None}


def brake_feedback_reference(reference, sample, *, tick, requested_gain, cap_per_axis_n):
    result = {'status': None, 'expected_force_intervals_n': None, 'measured_force_intervals_n': None}
    try:
        f, error = reading(sample, 'BRAKE_FORCE', tick)
        gain = scalar(requested_gain, 'gain'); cap = scalar(cap_per_axis_n, 'cap', positive=True)
        if gain == 0:
            result['status'] = 'NOT_REQUESTED'; return result
        if reference['status'] != 'CONDITIONAL_REFERENCE' or reference['tick'] != tick: raise ValueError('REFERENCE_UNAVAILABLE')
        r = scalar(reference['velocity_error_m_s'], 'reference velocity radius')
        v = vector(reference['velocity'])
        clip = lambda x: max(-cap, min(cap, x))
        expected = [[clip(-gain * (x + r)), clip(-gain * (x - r))] for x in v]
        measured = [[x - error, x + error] for x in f]
        if not all(math.isfinite(x) for pair in (*expected, *measured) for x in pair): raise ValueError('FORCE_NUMERIC_RANGE')
        disjoint = any(a[1] < b[0] or b[1] < a[0] for a, b in zip(expected, measured))
        informative = any(lo > 0 or hi < 0 for lo, hi in expected) and math.hypot(*f) > error
        result.update(status='INCONSISTENT' if disjoint else 'MODEL_CONSISTENT_FORCE' if informative else 'UNINFORMATIVE_NEAR_ZERO',
                      expected_force_intervals_n=expected, measured_force_intervals_n=measured)
    except (ValueError, TypeError, OverflowError, KeyError) as exc:
        result.update(status='UNSUPPORTED', reason=str(exc))
    return result


def force_acceleration_reference(command, force_sample, acceleration_sample, *, tick,
                                 mass_lower_kg, mass_upper_kg, disturbance_upper_n):
    """Distance to the allowed inverse-mass segment, with norm-error allowance.

    If F = command+measured_brake, a_true = beta*(F+force_error+disturbance),
    beta in [1/m_max,1/m_min]. The minimum distance of measured a to beta*F
    must be <= accel_error+(force_error+disturbance)/m_min. Inconsistency cannot
    identify which sensor, model, actuator or contact assumption failed.
    """
    try:
        u = vector(command); f, ef = reading(force_sample, 'BRAKE_FORCE', tick)
        a, ea = reading(acceleration_sample, 'ACCELERATION', tick)
        lo = scalar(mass_lower_kg, 'lower mass', positive=True); hi = scalar(mass_upper_kg, 'upper mass', positive=True)
        d = scalar(disturbance_upper_n, 'disturbance')
        if hi < lo: raise ValueError('MASS_ORDER')
        total = tuple(x + y for x, y in zip(u, f))
        # Normalize before projecting, avoiding a squared-force overflow.
        norm = math.hypot(*total)
        if not math.isfinite(norm): raise ValueError('FORCE_ACCEL_NUMERIC_RANGE')
        if norm:
            unit = tuple(x / norm for x in total)
            beta = max(1. / hi, min(1. / lo, dot(a, unit) / norm))
        else: beta = 1. / lo
        residual = math.hypot(*(x - beta * y for x, y in zip(a, total)))
        allowance = ea + (ef + d) / lo
        if not all(math.isfinite(x) for x in (beta, residual, allowance)): raise ValueError('FORCE_ACCEL_NUMERIC_RANGE')
        return {'status': 'INCONSISTENT' if residual > allowance else 'COMPATIBLE_UNDER_ASSERTED_MODEL',
                'minimum_residual_m_s2': residual, 'allowance_m_s2': allowance, 'best_inverse_mass_kg_inv': beta}
    except (ValueError, TypeError, OverflowError) as exc:
        return {'status': 'UNSUPPORTED', 'reason': str(exc), 'minimum_residual_m_s2': None, 'allowance_m_s2': None}
