# LIVE01 computation-window development addendum

Declared before executing the new mode on 2026-11-17. Development-only change; no frozen V9-M4 rule is altered. GATE_B_NOT_AUTHORIZED.

## Observed limitation

The original SNAPSHOT_SAME_TICK mode rejects any advancing cursor. Valid frame computations/publications can repeatedly straddle sample boundaries and cause lease expiry before a planned fault. The 28-case snapshot campaign retained one unqualified conflict-replay exposure for that reason. Do not relabel that run successful.

## New explicit mode and mathematical contract

Retain the original mode and tests. Add STATE_TUBE_WINDOW_V1 as a separately identified development condition. At the initial live beacon cursor K, a source sample S must satisfy 0 <= K-S <= 3 ideal samples and the unchanged native source-age limit. Let h=0.02, A=(primary force cap + disturbance)/minimum mass and T=(K-S+2)h. Exact interval transport encloses position and velocity for every elapsed ideal time in [0,T], including source age, at most one further cursor advance, and one intersample phase.

Run the unchanged EA01 offline algebra on this already enclosed state at an explicitly labelled zero reference coordinate. Zero is a model coordinate, not the host clock or a claim that the plant froze. Bind the original sample hash, epochs, initial beacon and T into the derived packet identity. Preserve actual source timestamps and both actual live beacon readings in the outer proof record.

After computation, require the actual cursor advance to be 0 or 1 with the same epoch; retain the original native computation/publication budget, raw-observation age limits and half-open lease expiry. Publication must match the final recorded cursor. The resulting conditional invariant must cover every state in the entire tube, rather than one favorable endpoint. No parameter/force bounds, safety boundary or evidence requirement is relaxed. The plant continues independently throughout.

## Acceptance evidence

Require exact-rational tests that the tube encloses independent bounded-acceleration paths throughout source age/computation/intersample intervals; reject two advances, stale sources, epoch changes, exact native deadline, unsupported evidence and clock failures. Retain strict-arm assertions. Reconstruct the derived packet, evidence statements, both clocks and lease endpoints from saved raw records. Repeat all relevant tests and full process campaigns under the new source identity.

This is not a retrospective pass for the old mode or a physical real-time guarantee. Same-host virtual-clock trust, bounded-force assumptions, unverified physical measurements, backup capability, independent review and hardware validation remain explicit limitations. Do not pool prior and new runs as independent evidence.
