# Mathematical review of aerodynamic benchmark monitoring

Date: 2026-11-16 (Asia/Bangkok). **Read-only mathematical analysis; not independent statistician approval. `GATE_B_NOT_AUTHORIZED`.** No repo, evaluator, frozen statistical rule, policy or historical artifact was modified; no Holdout/reserved outcome/seed access occurred.

## Identity and evidence

Reviewed `/private/tmp/nexvia-review-20261116/benchmark.py`, corresponding to public `experiments/benchmark_rigorous_monte_carlo.py` at GitHub commit `936fbdfeb516cf8b77ba6107c57f9f796293a525`.

SHA-256: `c057bb7c9a58b6a17663784447af046b8eee46d6ab97819abd79fc8ede44890d`.

Authoritative code: https://github.com/Chalermsak1/nexvia-aegis/blob/936fbdfeb516cf8b77ba6107c57f9f796293a525/experiments/benchmark_rigorous_monte_carlo.py

- Lines 93–96 initialize wealth at 1, first-alert state and fixed bet .25.
- Lines 175–185 generate accelerometer measurements from simulated acceleration, add noise/drift, and update a stateful disturbance observer.
- Lines 192–194 calculate squared audit residual `Z_t=||est_force-model_force||²`.
- Lines 196–203 claim a supermartingale, assert an envelope .35, normalize the residual, clip scores from below and above, multiply wealth and floor it at .01.
- Lines 206–207 compare wealth with 20 (nominal alpha .05).
- Lines 275–285 classify pre-injection alerts as false alarms and calculate post-injection delays.
- Lines 350–351 retain delays only when non-null before averaging at 371–376.

## Findings

### 1. The comment states a weaker null than sequential validity needs

The stated `E[Z_t] <= tau` at line 198 does not supply the conditional bound `E[Z_t | F_(t-1)] <= tau_t` required by this multiplicative betting construction. Past observations, model state, controller actions, the observer's memory and the selected sensing process belong in the filtration. Independence is not necessary if the conditional bound holds; marginal calibration alone is insufficient.

The fixed `.35 N²` envelope is asserted in code. This review found no derivation or calibration contract in the inspected function establishing a uniformly valid conditional envelope. That field remains **UNRESOLVED** for the physical benchmark, even after correcting arithmetic.

### 2. Lower clipping invalidates the generic claimed implication even at wealth 1

Let tau=.35 and, under a hypothetical null, Z=0 with probability .75 or Z=1.4 with probability .25. Then E[Z]=.35 exactly. The unmodified normalized scores are -1 and 3, with mean zero. Lower clipping produces -.9 and 3, whose mean is .075. With lambda=.25:

`E[1+.25*clipped_score] = .75*.775 + .25*1.75 = 1.01875 > 1`.

Thus the implemented update need not be a supermartingale even when the stronger conditional mean null holds (e.g., IID draws from this two-point distribution). Upper truncation alone would reduce the score pointwise; raising the negative tail does not.

This counterexample disproves a generic proof from the code's asserted residual-mean bound. It does not claim that this artificial two-point distribution describes the actual aerodynamic simulator.

### 3. The wealth floor independently breaks the same property

At current wealth .01, let the next scores be ±.5 with equal conditional probability. Both lie inside the clipping interval. Before the floor the expected multiplier is one. After applying `max(.01, M*factor)`:

`E[M_next] = (.01 + .01125)/2 = .010625 > .01`.

The floor replenishes capital after losses. Numerical stability must not increase evidence. Removing only this floor does not repair the lower-clipping defect above.

### 4. False-alarm and delay reporting do not establish the claimed operational guarantees

Every current run injects drift. False alarms are alerts before a randomized injection time, rather than alerts over an independently specified full fault-free mission horizon. The reported quantity should be named accordingly. A full-duration fault-free study is required to examine mission-level false-alarm behavior.

Delay means condition on non-null detections. Future evaluation must retain missed detections/right-censoring, terminal events and timing horizon, and report detection fraction jointly with delay. A bounded false-alarm probability does not imply bounded collision probability, fault-isolation correctness or sufficient recovery time.

## Proposed separate DEVELOPMENT-only monitor core

Do not replace the historical benchmark or frozen V9-M4 evaluator with the proposal. Implement it as a separately identified experimental component, with its assumptions carried in the metadata and its guarantee explicitly conditional on them.

Specification:

1. Fix a filtration including all information used to choose actions, sensing requests and bets. Define nonnegative observed residual statistic `Z_t` and a strictly positive, predictable envelope `tau_t`.
2. Explicit null: `E[Z_t | F_(t-1)] <= tau_t` at every supported monitored step. Its physical justification/calibration remains a separate obligation.
3. Choose a finite nonnegative predictable cap `b_t` and predictable bet `lambda_t` in `[0,1)`. Fixed constants are acceptable special cases. They must not be selected using the same current residual before its update.
4. Define `S_t=min(Z_t/tau_t - 1, b_t)`. **No lower clipping**: Z>=0 already gives S>=-1.
5. Define `E_t=1+lambda_t*S_t`, and `M_t=M_(t-1)*E_t`, starting M_0=1. Then E_t>0 and `E[E_t | F_(t-1)] <= 1`. Hence the product is a nonnegative supermartingale under the explicit null. A predeclared threshold `1/alpha` supports Ville's bound for that process under those conditions.
6. Compute log wealth using `log1p(lambda*S)` and addition. Never floor or replenish actual/log wealth. Handle overflow of `Z/tau` by a safe capped calculation rather than creating nonfinite evidence. An underflow-to-zero representation may be conservative but must remain absorbing; log representation is preferable.
7. No implicit reset on alarm, quiet periods, fault isolation or new mission phases. Any future restart/mixture/multiple-monitor scheme needs a separately specified valid construction and error accounting.
8. Malformed, missing, out-of-order or nonfinite measurements/configuration should produce an explicit unsupported/error outcome, not be silently dropped, replaced with favorable values or counted as statistical evidence. If missingness depends on the current observation, skipping it can itself invalidate a selected sequence. Do not assert a continued anytime guarantee without a defined valid observation/missingness model. Preserve the pre-error history and report availability separately.
9. Record configuration, exact score/factor/log-wealth, time/sequence, provenance identity and unsupported conditions. Such self-reported records do not authenticate execution.

**Important limit:** Correct code for this core proves an abstract conditional result, not that the aerodynamic residuals satisfy its null. `.35`, `.25`, cap 3 and alpha .05 are historical implementation parameters, not automatically approved new scientific choices. They should be explicit development inputs; no scientific threshold is approved by this review.

## Calibration and dependence work required

- Prefer an analytically justified conditional envelope when the sensor/observer/control model permits it. Include observer transient, correlation, operating state, adaptive actions, gusts and model mismatch.
- An empirical upper mean from a pooled fault-free sample does not automatically upper-bound each online conditional mean. A finite-sample uncertainty allowance itself needs a justified conditional/robust model; reserve separate calibration and evaluation worlds.
- A possible alternative is an episode/block-level conformal/e-value design under an explicitly justified exchangeability or conditional-validity assumption. It does not supply arbitrary within-step conditional validity merely by renaming pooled residuals.
- Protect calibration against faulty data and online contamination; adaptation changes the null/model and requires predeclared rules.
- Audit common-mode faults: agreement with a model using shared assumptions does not establish truth. An unobservable failure may be indistinguishable from a healthy state under available sensing.
- Conditional/marginal validity, per-stream/familywise validity, full-horizon false alarms, missed faults, recovery deadline and collision risk must remain separate reported quantities.

## Exact development tests proposed before integration

1. Two-point lower-clipping counterexample above: legacy expected multiplier 1.01875; proposed upper-only expected multiplier at most 1.
2. Wealth-floor counterexample above: legacy .010625 vs previous .01; proposed process never replenishes losses.
3. All-zero residuals, equality-bound two-point distribution, conservative null, alternative with positive score, lambda=0 and near-one allowed lambda.
4. Finite-support conditional distributions with known conditional means under adaptive predictable bets/envelopes; verify expected factor <=1 by exact enumeration. Separate deliberately invalid marginal-only constructions and confirm they are outside the theorem assumptions.
5. Log/numeric agreement over moderate histories; extreme loss histories, huge finite Z and small positive tau; no positive evidence created by floor, overflow or reset.
6. Explicit rejection of bool-as-number, negative/nonfinite residual, zero/negative/nonfinite tau, invalid bet/cap, missing measurement and invalid ordering. Document what the API can enforce versus what it cannot authenticate (especially predictability/conditional-null truth).
7. Seeded null simulations for empirical diagnostics, with all seeds/counts/results retained. Treat them as finite checks, not proof of the conditional guarantee or independence of real data.
8. Before physical-model evaluation, a preregistered full-duration no-fault design and faulted design must report detection count, misses, timing and operational outcomes separately. No new confirmatory run is authorized here.

## Review/approval boundary

This report supplies mathematical reasoning and engineering recommendations. It is not an independently authenticated statistical review, owner approval, null calibration, release authorization or Gate B authorization. Independent statistical review should specifically confirm the filtration, conditional envelope justification, missingness/adaptation/restart/multiplicity design and distinction between monitor error control and physical risk before a defensible confirmatory claim.

Background primary reference: Ramdas, Grünwald, Vovk and Shafer, *Game-theoretic statistics and safe anytime-valid inference*, https://arxiv.org/abs/2210.01948 . The core inequalities/counterexamples here are explicitly derived above rather than inferred from a citation.

Counterexample arithmetic and source digest are preserved at `/private/tmp/nexvia-monitor-counterexamples-20261116.json`. Repository and protected artifacts remain unchanged.
