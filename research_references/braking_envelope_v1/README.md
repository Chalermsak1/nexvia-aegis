# One-dimensional braking-envelope development reference

This is a bounded analytical reference, not a safety-certified controller,
flight-recovery model, approved operational criterion or general robotics
recoverability guarantee. No repository or frozen evaluation files were edited.
Gate B remains `GATE_B_NOT_AUTHORIZED`.

For an upper bound on initial approach speed v>=0, a lower clearance c>=0,
upper total detection/decision/switch/actuation delay t>=0, TOTAL net outward
acceleration bound a>=0 during delay, guaranteed braking deceleration b>=0,
and opposing braking-phase disturbance bound d>=0:

- During delay: travel <= v*t + .5*a*t²; approach speed <= v+a*t.
- If b>d, subsequent net braking is at least b-d until approach speed reaches
  zero, giving braking travel <= (v+a*t)² / (2*(b-d)).
- Thus worst-case travel <= v*t + .5*a*t² + (v+a*t)²/(2*(b-d)).
- Compare that bound with the supplied lower clearance. Equality is mathematical
  bound satisfaction with zero reserve; it is not a verified physical-safety claim.
- If b<=d, the module returns UNSUPPORTED_NO_POSITIVE_NET_BRAKING with unknown
  travel/satisfaction, rather than inventing an infinite/zero stopping distance.

The outward delay acceleration already includes all approach-direction forces
and disturbance. Do not add d to it again unless the input definition is changed
explicitly. The braking disturbance d reduces b during braking only. The bound
assumes the static boundary, a one-dimensional normal approach, clearance after
footprint/reserve deductions, and braking authority continuously available after
the bounded delay. Moving obstacles, lateral escape, rotor failure, attitude,
jerk limits, braking ramp-up and additional model/estimation error are excluded
unless already covered by the caller's supplied bounds. No platform thresholds
or acceptable clearance reserve have been selected.

API: `braking_envelope.evaluate(...)` returns explicit component bounds,
speed-after-delay bound, net braking, margin and `bound_satisfied`. Classifications
are BOUND_SATISFIED_UNDER_ASSUMPTIONS, BOUND_NOT_SATISFIED or UNSUPPORTED. Missing,
negative, nonnumeric, bool and nonfinite inputs reject. Overflow and detected
positive-motion underflow return unsupported, not positive evidence. Ordinary
floating-point calculations are not interval-certified, and this implementation
cannot verify the truth or predictability of any physical bounds.

Tests: initial 46 passed; final **47 passed in .03 s** after adding a positive-motion
underflow check. Exact rational analytic case, zero delay/stationary cases,
boundary equality, delay/disturbance monotonicity, insufficient braking, invalid
inputs, overflow and underflow are covered. No unexpected test failures occurred.
These are mathematical development fixtures, not physical trials or a new
confirmatory study. Final selected hashes and test XML identity are recorded in
`verification.json`.

Reproduce:

```
PYTHONDONTWRITEBYTECODE=1 /Users/chalermsak/Documents/ChatGPT/New\ project/nexvia-aegis/.venv/bin/python -m pytest -p no:cacheprovider -q test_braking_envelope.py
```

Before integration, validate sensor-derived speed/clearance bounds, actual delay,
actuator braking authority and disturbance envelopes on the chosen platform;
review the applicable dynamics and reserve requirements independently. This
module does not supply or approve any of those inputs.
