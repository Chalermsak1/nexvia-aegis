"""Exploratory two-source command assurance, NOT sensor authentication.

Disjoint error balls reveal inconsistent assertions but cannot identify the
faulty sensor. Overlap does not establish truth. Commands are checked over the
UNION, not an intersected/fused ball: if at least one declared ball contains
truth, the union contains it. Shared errors can violate that assumption.
"""
from dataclasses import asdict
import math
from .bounded_braking import BoundedStateGate, braking_command, scalar


def snapshot(state):
    if state is None:
        return None
    result = asdict(state)
    result['position'], result['velocity'] = list(state.position), list(state.velocity)
    return result


def overlap(center_a, radius_a, center_b, radius_b):
    distance = math.hypot(*(x - y for x, y in zip(center_a, center_b)))
    radius = radius_a + radius_b
    if not math.isfinite(distance) or not math.isfinite(radius):
        raise ValueError('NUMERIC_RANGE_IN_COMPATIBILITY')
    return distance <= radius


class SourceBrakeSupervisor:
    """One episode, terminal refusal. No reset or automatic sensor exclusion.

    Single-source mode is an explicit experimental baseline. Both modes latch
    on any rejected command; a consumer must record physical evolution afterward.
    Input labels do not authenticate hardware, calibration or independence.
    """
    def __init__(self, *, require_secondary=True, force_limit_n=2., mass_kg=1., hold_seconds=.02):
        if type(require_secondary) is not bool:
            raise ValueError('require_secondary must be boolean')
        self.require_secondary = require_secondary
        self.force_limit = scalar(force_limit_n, 'force limit', positive=True)
        self.mass = scalar(mass_kg, 'mass', positive=True)
        self.hold = scalar(hold_seconds, 'hold time', positive=True)
        self.primary = BoundedStateGate(max_age_seconds=.08, acceleration_norm_upper_m_s2=2., source='SIM_PRIMARY')
        self.secondary = BoundedStateGate(max_age_seconds=.08, acceleration_norm_upper_m_s2=2., source='SIM_SECONDARY')
        self.failure = None

    def choose(self, primary, secondary, *, now_seconds):
        result = {'status': 'NO_COMMAND', 'reason': None, 'force_n': None,
                  'primary': None, 'secondary': None, 'input_reasons': None,
                  'position_compatible': None, 'velocity_compatible': None,
                  'union_power_upper_w': None, 'union_hold_energy_upper_j': None}
        if self.failure is not None:
            result['reason'] = 'LATCHED:' + self.failure
            return result
        a, ra = self.primary.accept(primary, now_seconds=now_seconds)
        b, rb = self.secondary.accept(secondary, now_seconds=now_seconds) if self.require_secondary else (None, 'NOT_USED_BASELINE')
        result.update(primary=snapshot(a), secondary=snapshot(b), input_reasons=[ra, rb])
        if a is None or (self.require_secondary and b is None):
            self.failure = result['reason'] = 'REQUIRED_SOURCE_REJECTED'
            return result
        if self.require_secondary:
            try:
                result['position_compatible'] = overlap(a.position, a.position_error_m, b.position, b.position_error_m)
                result['velocity_compatible'] = overlap(a.velocity, a.velocity_error_m_s, b.velocity, b.velocity_error_m_s)
            except ValueError:
                self.failure = result['reason'] = 'COMPATIBILITY_UNSUPPORTED'
                return result
            if not result['position_compatible'] or not result['velocity_compatible']:
                self.failure = result['reason'] = 'CONTRADICTORY_SOURCE_BALLS'
                return result
        proposed = braking_command(a, force_norm_limit_n=self.force_limit, mass_kg=self.mass, hold_seconds=self.hold)
        if proposed['status'] != 'COMMAND_PROPOSED':
            self.failure = result['reason'] = 'PRIMARY_BRAKE_UNSUPPORTED:' + proposed['reason']
            return result
        force = proposed['force_n']
        powers = []
        try:
            for state in (a, b) if self.require_secondary else (a,):
                powers.append(math.fsum(x * y for x, y in zip(force, state.velocity)) + math.hypot(*force) * state.velocity_error_m_s)
            power = max(powers)
            energy = self.hold * power + .5 * self.hold**2 * math.hypot(*force)**2 / self.mass
            if not math.isfinite(power) or not math.isfinite(energy):
                raise ValueError('numeric range')
        except (ValueError, OverflowError):
            self.failure = result['reason'] = 'UNION_NUMERIC_RANGE'
            return result
        result.update(union_power_upper_w=power, union_hold_energy_upper_j=energy)
        if power >= 0 or energy >= 0:
            self.failure = result['reason'] = 'UNION_BRAKE_UNSUPPORTED'
            return result
        result.update(status='COMMAND_PROPOSED', reason='CONDITIONAL_UNION_BRAKE' if self.require_secondary else 'CONDITIONAL_SINGLE_BRAKE', force_n=force)
        return result


class SimulatedDamperSwitch:
    """Sensor-independent schedule for a HYPOTHETICAL passive damping element.

    This class only requests/reports a coefficient. MuJoCo supplies the passive
    dynamics. It neither reads velocity nor computes -c*v as a control command.
    Availability/acknowledgement are synthetic fixture assumptions, not physical
    actuator verification. A missing acknowledgement is retained as FAILED.
    """
    def __init__(self, *, enabled, delay_steps=3, damping_kg_s=2.):
        if type(enabled) is not bool or type(delay_steps) is not int or delay_steps < 0:
            raise ValueError('invalid switch configuration')
        self.enabled, self.delay = enabled, delay_steps
        self.damping = scalar(damping_kg_s, 'damping', positive=True)
        self.request_step = self.last_step = None
        self.failed = False

    def advance(self, *, step, request, available):
        if type(step) is not int or step < 0 or type(request) is not bool or type(available) is not bool:
            raise ValueError('invalid switch event')
        if self.last_step is not None and step != self.last_step + 1:
            raise ValueError('missing/replayed switch step')
        if self.last_step is None and step != 0:
            raise ValueError('switch session must begin at step zero')
        self.last_step = step
        if not self.enabled:
            return {'state': 'DISABLED_COAST_BASELINE', 'request_step': None, 'activation_due_step': None, 'requested_damping_kg_s': 0.}
        if request and self.request_step is None:
            self.request_step = step
        due = self.request_step + self.delay if self.request_step is not None else None
        if due is not None and step >= due and not available:
            self.failed = True
        state = 'NOT_REQUESTED' if due is None else 'PENDING' if step < due else 'FAILED_UNAVAILABLE' if self.failed else 'ACTIVE_ASSUMED'
        return {'state': state, 'request_step': self.request_step, 'activation_due_step': due,
                'requested_damping_kg_s': self.damping if state == 'ACTIVE_ASSUMED' else 0.}
