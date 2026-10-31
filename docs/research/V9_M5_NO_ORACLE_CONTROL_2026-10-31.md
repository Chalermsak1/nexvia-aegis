# V9-M5 estimate-only control interface — development fixture

**Status: exploratory interface.** Initial tests used the isolated interface. A later separate MuJoCo braking micro-study now uses it; it is not integrated into the arrival benchmark. Neither stage executed Holdout, changed a registered evaluator or established any safety/real-robot claim. Gate B remains `GATE_B_NOT_AUTHORIZED` under the standing owner instruction. See `V9_M5_TEAM_INTEGRATED_DEVELOPMENT_2026-10-31.md` for the later micro-study.

## Motivation and scope

The existing exploratory 3D benchmark calculates `action_3d - 0.5 * vel` using the simulated plant velocity. Its `AegisMuJoCo3DEnvironment.step` then passes simulated plant position and velocity to `ControlBarrierFilter3D.compute_safe_control` and, for `force_braking=True`, that filter replaces the requested action with a brake based on the same plant velocity. Thus a candidate controller that receives noisy velocity can still benefit from an oracle in damping, braking and barrier projection. A no-oracle comparison must address **all three paths**, not just the candidate's observation.

`scripts/research/no_oracle_control.py` introduces `EstimateOnlyControl`, a non-integrated command-generation proposal. It consumes position and velocity estimates together with their sequence number and timestamp; applies the existing exploratory `VelocityFreshness` check; computes navigation damping or braking using the measured velocity; and passes **the same estimated position and velocity** to an injected CBF projector with `force_braking=False`. This prevents that project's projector from selecting a brake using a different state. A real-CBF-component test confirms that the proposal can call `ControlBarrierFilter3D` this way, but this is not a simulated episode and does not establish correctness or safety.

`NO_COMMAND` is returned on missing, stale, malformed or rejected input, invalid control mode, projector failure or invalid projected force. It is an evidence/accounting state, **not a braking command or a fail-safe physical response**. A hardware or operational system would need a separately analyzed independent fallback. The API accepts caller-supplied timestamp, frame and source as trusted assertions; its metadata gate cannot authenticate those assertions or detect plausible bias. Its output is explicitly marked `projection_safety=UNVERIFIED`.

## Synthetic falsification example

The command-line demo uses analytic single-step fixtures with a synthetic identity projector; it is not MuJoCo and does not model obstacles, contacts, braking lag or a complete control loop. Simulated true velocity is `[1, 0, 0]` m/s, used only for scoring *after* choosing the requested brake:

| Measured velocity | Proposed brake dot true velocity | Interpretation in the fixture |
|---|---:|---|
| `[1, 0, 0]` | −2.0 | Force opposes motion. |
| `[0.25, 0, 0]` | −0.5 | Force opposes motion but is smaller. |
| `[-1, 0, 0]` | +2.0 | Force points with true motion: wrong-sign data can accelerate rather than brake. |
| unavailable | not computed | Returns `NO_COMMAND`; no physical stop is implied. |

This demonstration is a counterexample to assuming that estimated-velocity braking is safe under arbitrary sensor error; it does not estimate field risk. Example command, writing a new path:

```bash
PYTHONPATH=src .venv/bin/python scripts/research/no_oracle_control.py --output NEW_DEVELOPMENT_FIXTURES.json
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_no_oracle_control.py
```

The output file uses exclusive creation and records hashes for the two listed source files, not full source or runtime provenance. An interrupted write can still leave a partial file. **10 synthetic tests passed**, including estimate forwarding, avoiding the projector's brake override, stale/replayed/missing inputs, invalid projector results, and the wrong-sign counterexample.

## Remaining integration and research

1. The subsequent separate braking micro-study adds a plant-step adapter that accepts a filtered action without recomputing the CBF from truth. It is not a mission-level arrival arm, and its obstacle geometry remains simulator-known. Broader integration and information-parity evaluation remain outstanding; preserve old outputs.
2. Define input provenance, clock/frame validity, position and velocity error/dropout/latency, perception of obstacles and uncertainty; distinguish unavailable controls, infeasible CBF and physical violations from success. Paired streams and independent test evidence require explicit assignment and failure accounting.
3. Simulate delayed, biased, reversed, correlated, stale and missing readings. Compare matched operational outcomes and sampled dwell, including no-command duration and recovery; run actual physics simulation separately before calling this a benchmark arm.
4. Establish a physically appropriate fallback and independent review; do not deploy this proposal as a safety function, treat a CBF residual as certification, or claim a guarantee from the identity-projector fixtures.
