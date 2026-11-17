# FC01 — Family recovery reserve and physical-model boundaries

**Status:** Proposed for independent architecture/control review; implemented as an exploratory prototype.

**Date:** 2026-11-17, Asia/Bangkok.

**Deciders:** Owner for research scope; independent control/verification and security/runtime reviewers for the corresponding claims. No such approval is supplied by this record.

**Governance:** `GATE_B_NOT_AUTHORIZED`; release BLOCKED.

## Context

The point-model supervisor and subsequent parameter-family certificate were separate. Applying the nominal-mass bridge to a family could admit a future handoff state outside the common backup set. Separately, the semi-implicit position update used in the native development fixtures does not equal physical constant-force integration. Sample endpoints therefore cannot be silently promoted to a continuous-time safety guarantee.

The new work preserves every earlier source/evidence identity. The results report (workspace record `V9_M5_FAMILY_RECOVERY_COMPOSITION_RESULTS_2026-11-17.md`; not included in this lightweight upload) records the exact tests and negative findings. The paper workflow (workspace record `NEXVIA_SIMULATION_PAPER_WORKFLOW_2026-11-17.md`; not included in this lightweight upload) records the remaining scientific and engineering closure requirements.

## Decision

Add a separate sampled family supervisor that combines the existing common-metric certificate with a minimum-mass force-cap bridge, explicit finite tick-age alternatives, all admitted handoff delays and existing primary temporal/readiness results. Require primary physical bounds to cover the full parameter family before permitting continuation. Every physical/parameter/clock premise stays explicit; missing evidence stays unresolved. No source-authentication or executor authority is introduced.

Add a separate ideal held-force segment diagnostic with a different dynamics identifier. It computes physical path extrema and the single-step endpoint difference from semi-implicit Euler under the same held acceleration. It cannot supply a global continuous-time invariant certificate or replace the sampled supervisor model.

## Options considered

| Option | Benefit | Risk or cost | Disposition |
|---|---|---|---|
| Reuse nominal mass throughout | Minimal implementation work | Fails to cover admitted lower-mass acceleration and can overstate future backup reserve. | Rejected for the family claim. |
| Rewrite old modules and reclassify old results | One apparent interface | Breaks recorded source identities and confuses historical model scope. | Rejected. |
| Separate family composition and held-force diagnostic | Preserves old evidence; exposes explicit model and timing boundaries. | More interfaces; requires careful scope communication and future integration work. | Implemented for development. |
| Claim physical-time safety from native Euler samples | Simpler narrative | Lacks a physical interpolation/model-error argument. | Unsupported. |

## Trade-offs and consequences

The bridge admits arbitrary capped force, including nonzero carried force and queued commands, using the smallest mass. The bound is conservative. Hulls over possible ages deliberately lose time/state correlation, so failure to certify need not mean every real trajectory is unsafe. Refusing an insufficiently covered primary result is a documented conservative decision of the prototype, not a universally optimal operational response.

State epochs are integer alternatives on an asserted common sample grid. Arbitrary fractional mapped times are not rounded into that grid. General independent-clock uncertainty therefore remains open. The current Python path is stateless/offline; its input assertions do not authenticate sources or enforce physical deadlines. A separately implemented trigger/executor with durable uncertain-effect handling is still required for operation.

The existing family certificate retains its standalone scope fields unchanged. The new composition separately checks the bridge and reserve; it does not rewrite the certificate's old metadata. The held-force diagnostic retains `composed_future_containment=False` even for a contained segment.

## Action items and review gates

1. Independent control review of the common metric, minimum-mass bridge, age hull and all-delay composition.
2. Select the first paper's exact sampled-versus-physical-time claim before freezing evaluation.
3. Develop a durable simulation-only supervisor/executor lifecycle with explicit uncertain effects, command expiry, boot identity and one-shot consumption.
4. Integrate interval clock mapping without assuming physical observations lie on an unverified common grid.
5. Review the proposed backup's physical feasibility and provide actual calibration before hardware claims.
6. Establish novelty against existing sampled-data, interval-control and runtime-assurance literature; implement and check fair baselines.

All operational approvals remain **UNAPPROVED**. No V9-M4 statistical rule or frozen artifact is changed. Gate B remains `GATE_B_NOT_AUTHORIZED`.

## Publication scope note

Historical results and full evidence remain unchanged in the original workspace. This publication copy preserves the development criteria and identifies unavailable workspace records explicitly. The [current NEXVIA team handoff](NEXVIA_AEGIS_RECOVERY_HANDOFF_2026-11-17.md) provides source entry points, review summaries and remaining blockers. Publication does not approve a criterion or authorize Gate B.
