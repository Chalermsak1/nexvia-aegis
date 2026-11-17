"""Conditional sampled common-Lyapunov certificate for a 1D parameter family.

Separate development extension: does not alter the point-model supervisor or
produce a physical action. Parameter intervals and backup availability remain
external premises; no calibration, continuous-time, authentication or approval.
"""
from itertools import product

from .passive_backup_supervisor_1d import model as point_model, _quad, _wire
from .recovery_feedback_state_1d import _bounds, _fields
from .recovery_envelope_1d import point


def certificate(nominal, parameter_bounds):
    """Use nominal P as a common metric; interval residual dominance is sufficient.

    Independently varying positive m,k,c within a rectangular family are covered
    at every sampled step. Failing the sufficient test is NOT an instability
    witness. No handoff bridge or complete supervisor is certified here.
    """
    result = dict(status='UNKNOWN_PARAMETER_INPUT', conditional_sampled_invariance=False,
                  dispatch=False, operational_authorization=False,
                  hardware_validation=False, gate_b='GATE_B_NOT_AUTHORIZED',
                  scope='ASSUMED_PARAMETER_FAMILY_ONLY_NO_HANDOFF_OR_INTERSAMPLE_CLAIM')
    try:
        reference = point_model(nominal)
        _fields(parameter_bounds, 'mass spring damping')
        family = {key: _bounds(parameter_bounds[key]) for key in parameter_bounds}
        if any(bound.lo <= 0 for bound in family.values()):
            raise ValueError('strictly positive explicit parameter intervals required')
        if any(not bound.contains(reference[key]) for key, bound in family.items()):
            raise ValueError('nominal reference must belong to the declared family')
        h, L, V = [reference[key] for key in ('dt', 'position_scale', 'velocity_scale')]
        mass, spring, damping = [family[key] for key in ('mass', 'spring', 'damping')]
        km = spring.divide_positive(mass)
        cm = damping.divide_positive(mass)
        A = ((point(1) - point(h*h)*km, point(h*V/L)*(point(1)-point(h)*cm)),
             (-point(h*L/V)*km, point(1)-point(h)*cm))
        P, inverse, trace = [reference[key] for key in ('P', 'inverse', 'trace')]
        residual = []
        for i in range(2):
            row = []
            for j in range(2):
                total = point(0)
                for u, v in product(range(2), repeat=2):
                    total = total + A[u][i]*point(P[u][v])*A[v][j]
                row.append(point(P[i][j]) - total)
            residual.append(tuple(row))
        cross = max(abs(residual[0][1].lo), abs(residual[0][1].hi),
                    abs(residual[1][0].lo), abs(residual[1][0].hi))
        eta = min(residual[0][0].lo-cross, residual[1][1].lo-cross)
        # S=P-A^T P A >= eta*I uniformly follows from symmetric diagonal
        # dominance. Negative eta is inconclusive, never an instability claim.
        contraction = 0 < eta <= trace
        rho = 1-eta/(2*trace) if contraction else None
        # B=(h*h/L,h/V)/m: the common scalar 1/m is maximized at mass.lo.
        B = (h*h/(L*mass.lo), h/(V*mass.lo))
        beta = _quad(P, *B)
        minimum = reference['disturbance']**2*beta/(1-rho)**2 if contraction else None
        force2 = reference['level']*max(_quad(inverse, k*L, c*V)
                    for k, c in product((spring.lo, spring.hi), (damping.lo, damping.hi)))
        margin = min(reference['anchor']-reference['safe_position'].lo,
                     reference['safe_position'].hi-reference['anchor'])
        checks = dict(common_contraction_sufficient=contraction,
                      disturbance_level_sufficient=minimum is not None and reference['level'] >= minimum,
                      force_cap_sufficient=force2 <= reference['force_cap']**2,
                      safe_projection_sufficient=margin >= 0 and reference['position_bound_squared'] <= margin*margin)
        established = all(checks.values())
        result.update(status='CONDITIONAL_SAMPLED_FAMILY_INVARIANT' if established else 'FAMILY_INVARIANCE_NOT_ESTABLISHED',
                      conditional_sampled_invariance=established, checks=checks,
                      parameter_bounds={k: v.wire() for k, v in family.items()},
                      P=_wire(P), P_inverse=_wire(inverse),
                      A_enclosure=[[x.wire() for x in row] for row in A],
                      residual_enclosure=[[x.wire() for x in row] for row in residual],
                      uniform_decay_lower=str(eta), contraction_upper=None if rho is None else str(rho),
                      disturbance_input_norm_squared_upper=str(beta),
                      minimum_disturbance_level=None if minimum is None else str(minimum),
                      backup_force_bound_squared=str(force2),
                      position_bound_squared=str(reference['position_bound_squared']),
                      reference_level=str(reference['level']), time_varying_parameters_within_family_covered=established,
                      handoff_or_supervisor_integration=False,
                      reason=None if established else 'SUFFICIENT_COMMON_METRIC_TEST_NOT_ESTABLISHED')
    except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError, AttributeError) as exc:
        result['reason'] = str(exc)
    return result
