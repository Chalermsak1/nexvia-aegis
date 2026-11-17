# Owner research core — 1D uncertainty-aware recovery specification

Prepared 2026-11-16, Asia/Bangkok. **Development specification, not an approved operational requirement or preregistered evaluation rule. Gate B remains `GATE_B_NOT_AUTHORIZED`.**

## Research question and scope

Can a declared one-dimensional measured-velocity braking policy establish containment of every modeled sampled position and a caller-specified terminal velocity condition despite bounded uncertainty in initial state, mass, gain, force cap, force slew, measurement error, disturbance, delay and brake-power cutoff?

The first implementation answers this question conditionally in a discrete-time point-mass model. It does not claim continuous/inter-sample containment, physical sensor authenticity, a real robot, three-dimensional obstacle avoidance or a position-invariant terminal set. The allowed center-coordinate interval must already incorporate any required body size, clearance and initial-position uncertainty; the module does not infer robot geometry or an intended application.

The model is a provisional research abstraction of supported translation. It is not a platform/product selection. In particular, the native point corroboration retains powered vertical support for its 1 kg model when brake power is cut; it cannot represent a whole-aircraft power failure.

## Declared dynamics

For time step h, actual position p, velocity v, measured-velocity error e, mass m, gain g, force cap C, force slew R, disturbance w, static integer request delay d and a single power-cut tick B:

```text
measurement_k = v_k + e_k                 |e_k| <= measurement_error
request_k     = clip(-g*measurement_k, -C, C)
due_k         = request_(k-d)              zero for initially empty queue
f_k           = f_(k-1) + clip(due_k-f_(k-1), -R*h, R*h), if k < B
f_k           = 0, and queue reset,        if k >= B
v_(k+1)       = v_k + h*(f_k+w_k)/m        |w_k| <= disturbance
p_(k+1)       = p_k + h*v_(k+1)
```

Initial force and all queued targets are zero. Mass, gain, cap, slew and delay are unknown but constant within one trajectory and lie in the caller's declared intervals. Noise/disturbance may vary arbitrarily within bounds at every step. The enclosure permits independent parameter extrema during propagation, which enlarges the set but must not exclude a trajectory with an admissible constant parameter.

Power is available until B, then absent for the remainder of the horizon. Restoration, repeated outages, time-varying transport delay/jitter, contact, actuator release dynamics and unbounded measurement deception are outside this version's model. The earlier measured monitor can abstain on missing/contradictory data; this core's candidate policy assumes fresh bounded measurements throughout. A claim about this model is not a claim that every monitor-abstention trajectory follows this policy.

## Exact input and computation semantics

The API accepts explicit integers, Fraction values, or decimal/fraction strings. Bool and binary-float inputs are rejected; `.02` as a decimal string means exactly 1/50. Arithmetic inside the enclosure retains exact rational endpoints without float rounding or interval truncation. This establishes an arithmetic representation, not formal verification of Python/software or physical calibration.

`dt`, position/velocity intervals, mass/gain/cap/slew intervals, disturbance/error bounds, delay/cut ranges, horizon, allowed position interval, terminal velocity interval and number of terminal endpoint samples are all explicit required inputs. No operational criteria are defaulted by the API. Horizon/delay/branch budgets bound the declared workload; this is offline development tooling, not a hardened untrusted-input service.

The supported feedback-step condition is `h*gain_max/mass_min <= 1`. An unsupported step, missing field, malformed bound or exceeded branch budget returns `UNKNOWN_INPUT`; it does not become a favorable model statement.

## Enclosure construction and argument to review

1. **Independent interval reference.** Propagate current velocity, force and queued request intervals with exact endpoint arithmetic. This contains admissible model values but can lose useful dependence between velocity and its own braking request.
2. **Delay-linked update.** Use the identity `v_(k-d) = v_k - sum(delta_v_j, j=k-d..k-1)`. Store interval bounds on each actual velocity increment directly from the force equation. This links the due request to current velocity without assuming that history and state are independent.
3. **Monotonic endpoint optimization.** With fixed history correction, error and parameters, clipped proportional braking followed by the slew operator is nonincreasing and gain-Lipschitz in current velocity. Under the feedback-step condition, `v+h*f(v)/m` is nondecreasing in v. Thus velocity endpoints suffice; monotonicity supplies extremal prior force, measurement error and history correction. Remaining gain/cap/slew/mass endpoint alternatives are enumerated. The queued-request interval supplies another valid target constraint.
4. **Intersection.** Intersect the delay-linked velocity range with the independent force-equation range. Both are intended to contain the same actual next velocity. An empty intersection is an unsupported calculation, never evidence of physical success.
5. **Static alternatives.** Enumerate each admissible integer delay and distinguish power-cut times that affect the finite horizon. Cut times after the horizon are behaviorally equivalent for that horizon; a representative allowed cut value is retained.
6. **Parameter subdivision.** Optionally cover static parameter intervals with closed rational subintervals. Their union is the complete original domain. Every subproblem must establish a property before that property is established for the aggregate. Failed cells are retained; boundary overlap is harmless. Cell counts are not independent trials or probabilities.

The scalar slew map is monotone in prior force and target; at fixed prior force/target its extrema over a positive slew interval occur at rate endpoints. Force remains between previous force and capped target. A prior-force bound paired with an unrealizable cap endpoint can enlarge the enclosure; it must not be used to exclude actual states. Static parameter dependence and state/history correlation are only partially retained, so a failure to establish a property can be conservative.

The reasoning is an implementation argument requiring independent control/numerical review. Random rational witnesses and corner tests provide useful implementation evidence but do not replace that review or a formal proof of software.

## Separate evidence from feasibility

| Axis | Meaning |
|---|---|
| Evidence compatible under asserted bounds | Measurements are treated as satisfying the specified model assumptions; this does not authenticate the channels |
| Evidence contradictory / unknown | The combined conclusion stays contradictory/unknown even if a counterfactual model calculation fits |
| Finite containment | Every enclosed sampled position, including the initial state, lies in the caller's allowed interval |
| Terminal samples | Every enclosed velocity in the last caller-specified number of endpoint samples lies in the caller's terminal interval |
| Enclosure exits the allowed interval | The enclosure cannot establish containment; it does not prove all physical recovery is impossible |
| Exact point witness crosses a boundary | A specific declared-model counterexample, distinct from an inconclusive overapproximation |
| Future position containment | `NOT_ESTABLISHED` in this implementation, even when finite conditions hold |
| Operational authorization | Always false |

With 25 endpoint samples at .02 s spacing, first-to-last endpoint span is .48 s. This is not continuous .5 s dwell. Semi-implicit sampled dynamics do not establish a continuous physical path without additional inter-sample/discretization bounds.

## Provisional development settings

The retained study uses position 0, initial velocity [.49,.51] m/s, mass [1,1.5] kg, gain 2 kg/s, force cap 1 N, slew [3,5] N/s, measurement error .005 m/s, disturbance .01 N, delay 2–4 ticks, 140 integration ticks and a power cut after the assessed horizon. Its allowed interval [-.5,1.5] m, terminal interval [-.05,.05] m/s and 25 terminal samples are explicit synthetic inputs. They are not owner-approved operational thresholds.

Point counterexamples use fixed parameters and zero declared sensor error/disturbance. A boundary at .27 m is a deliberately constructed development counterexample separating a fast-brake point model from its delayed/ramped counterpart. These inspected examples cannot be promoted to untouched confirmatory data.

## Owner decisions still required for physical use

| Requirement | Current state | Owner/reviewer input needed |
|---|---|---|
| Primary platform/use case | UNRESOLVED | Intended supported/airborne dynamics and operational environment |
| Physical safe region | SYNTHETIC ONLY | Robot size, obstacle/clearance treatment and consequences of crossing |
| Terminal condition | SYNTHETIC ENDPOINTS ONLY | Speed/position/dwell definition and maintained safe terminal set |
| Calibration | ASSERTED BOUNDS ONLY | Justified mass, actuator, measurement, disturbance, timing and power intervals |
| Sensor trust | NOT AUTHENTICATED | Independent reference/clock/frame assumptions and shared-deception limits |
| Backup behavior | SINGLE CUTOFF MODEL | Power topology, reserve/release behavior and feasible sustained fallback |
| Scientific claim | DEVELOPMENT ONLY | Independent unit, baselines, missingness, sample size/multiplicity and prospective review |

A mathematical result cannot provide an unavailable brake, trusted sensor or sustained position-holding mechanism. Independent statistical/security decisions remain separate. Existing V9-M4 decisions and frozen evaluation rules are unchanged.
