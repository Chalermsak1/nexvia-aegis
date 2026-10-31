# AEGIS development benchmark tool — product and research brief

**Status:** working hypothesis and engineering draft, not evidence of customer demand. No customer interviews, pilots, sales, pricing commitments, or certification have been verified. Initial proposed user: a robotics research or engineering team testing one simulated aerial robot with multiple sensors.

## Problem to test with users

Teams may spend significant time reproducing a run in which sensor faults lead to a wrong arrival or an overly cautious controller. They need to know which scenario failed, whether the failure repeats, and how a change trades safety against mission completion. This pain, its frequency, economic cost, and buyer must be learned from actual interviews; do not present them as established market facts.

## Value proposition and scope

Provide a local, reproducible workflow that takes an **exploratory simulation benchmark**, validates its records, and explains observed false arrivals, successful arrivals, abstentions, timeouts, and constraint failures by controller and fault scenario. The first product is an analysis and research-development tool. It does not command a real robot, approve a safety case, or certify a release.

The research contribution is a prospectively evaluated approach to evidence-aware decision making and its safety/coverage tradeoff. The product hypothesis is that teams will value repeatable fault scenarios and actionable comparisons enough to integrate them in their workflow. These require different evidence.

## Implemented vertical slice

```text
existing 3D development benchmark JSON
    → validate declared episode design and outcome accounting
    → per-controller and per-bias descriptive summaries
    → CSV + JSON + Markdown report in a new directory
```

Run from the repository root, using an existing development artifact:

```bash
python scripts/research/summarize_3d_development.py \
  results/research_development/dev/3d_probe_ablation_v2.json \
  --baseline AEGIS_3D_NO_ACTIVE_PROBE \
  --output-dir /tmp/aegis-analysis-example
```

The output directory must not already exist. This is an offline CLI with Python standard-library dependencies, not a dashboard or ROS integration. It accepts the specific exploratory benchmark schema and checks data against the design declared inside that file. It does not independently verify assignment manifests, validate safety, reconstruct missing episodes, or compute inferential verdicts. Zero accepted decisions are displayed as undefined selective risk.

## Intended first user journey

1. User chooses a simulator/controller and a bounded task; explicitly labels the data development or prospective confirmation.
2. User configures a sensor fault and seed/world assignment, then freezes or records the versioned inputs.
3. User runs comparable arms and retains all raw outcomes and failures.
4. Tool rejects conflicting or incomplete data; user inspects per-arm and per-scenario outcomes and the safety/coverage tradeoff.
5. User exports a traceable report and uses the observations to investigate a failure. Statistical claims require a separately approved protocol and review.

Steps 1–3 currently rely on existing research scripts, and steps 4–5 cover aggregate outcomes rather than event timelines. Integration with ROS bags, MCAP, a web interface, and arbitrary third-party controllers remains unimplemented.

## Positioning and alternatives

Compare the proposed workflow with Nav2 Collision Monitor, Foxglove log visualization and SOTER runtime assurance. They solve overlapping parts of the problem; a differentiator must be demonstrated in the user's actual workflow, not asserted from feature lists. A candidate differentiator is reliable fault-scenario accounting plus an understandable risk/coverage comparison linked to raw evidence. Test whether existing tools already meet this need before building parallel visualization infrastructure.

## Customer discovery plan

Suggested first interviews: developers, testing leads, and safety/reliability leads at teams developing drones or mobile robots. Recruit based on access to relevant users, not assumed market size. Ask for a recent real incident or difficult validation run:

1. What failed, how was it noticed, and what did the team do next?
2. What logs, simulators, and tools were used? Which parts were difficult to reproduce?
3. How are false alarms, missed failures, and mission completion traded off today?
4. Who owns the workflow and purchasing decision? What integration or data restrictions apply?
5. What would count as a useful pilot, and would the team supply a representative scenario or data under agreed terms?

Record facts and direct quotes with consent, separate assumptions from observed evidence, and compare repeated patterns. Interview counts and conversion targets are planning choices, not proof of demand. Do not imply an interview, purchase intent, or customer validation occurred when it has not.

## Pilot design and acceptance

Co-design a bounded scenario with a consenting partner. Before execution define a baseline workflow, task, inputs, privacy/storage terms, who controls data, failure-handling rules, and what the partner considers useful. Measure independently reproducible failures and time spent investigating them; compare against the partner's current workflow. Do not fabricate improvement targets or use a pilot as evidence of certified safety. If no suitable partner or hardware is available, continue with simulated examples and label them as such.

## Engineering roadmap and gates

| Stage | Deliverable | Gate to progress |
|---|---|---|
| 1. Evidence accounting | Offline development JSON analyzer and tests | Valid inputs reproduce counts; missing/contradictory records fail; existing evidence not overwritten |
| 2. Comparable benchmark | Four arms including an explicitly implemented no-active-verification ablation | Interface parity and sample assignment reviewed; fault taxonomy and raw evidence available |
| 3. Usable analysis | Failure timeline, reproducible scenario selection, report and documented adapter | Tested with synthetic and consenting-user data; privacy and ownership agreed |
| 4. Independent study | Frozen protocol, independent analysis and fresh data | Owner and independent statistician approve rules before confirmatory data access |
| 5. Real platform | SITL, HIL, constrained physical tests | Named platform, validated transport, safety case, emergency stop and approvals |

## Risks and open decisions

- A 3D no-active-probing ablation now exists, but it retains normal range checks and abstains when probing is requested. Its behavior and interface parity require scientific review; comparisons are not yet a final research claim.
- The current live ROS transport is explicitly disabled; in-memory `publish_*` calls are simulation records only.
- A zero observed error count with low coverage is not proof of safety or utility.
- Review ownership, dependency licenses, customer data access, and deployment obligations before commercial distribution.
- Release and H1–H5 governance remain separate; no production ticket, reserved Holdout data, or historical artifact is changed by this product draft.

**Next concrete decision:** identify the first customer segment and task, then interview users while engineering completes the reproducible four-arm benchmark. Keep a dated record of which assumptions are confirmed, rejected, or unresolved.
