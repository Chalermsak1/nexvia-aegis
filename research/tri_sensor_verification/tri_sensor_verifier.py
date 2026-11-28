"""
Self-Verifying Tri-Sensor Cross-Check, Fault Isolation & Quarantine Engine.

Core research goal (CEO assignment):
  - 3 sensors observe the same physical environment simultaneously.
  - Sensors cross-check one another automatically without ground truth.
  - Detect gradual drift, heavy drift, sudden bias, outlier spikes,
    retimestamped freeze (fresh metadata + stale physical value), and blackout.
  - Quarantine faulty sensor(s) and STRICTLY EXCLUDE faulty readings from both:
      (a) display_pos  (operator / UI display output)
      (b) control_pos  (navigation / mapping operational output)
    while logging rejected values separately for auditability.
  - Fail-Closed (ABSTAIN_SAFE_STOP) when >= 2 sensors disagree or fail so no
    unverified majority exists.

Scientific Integrity Note (aligned with NEXVIA CORE cusum_monitor.py):
  The pairwise drift accumulator below uses deterministic Page's CUSUM
  S_k = max(0, S_{k-1} + (z_k - k_allow)). Because it reflects at zero, it is
  NOT a nonnegative supermartingale and must NEVER be described as
  Ville-anytime-valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import numpy as np

from research.tri_sensor_verification.sensor_suite import SensorReading


@dataclass(frozen=True)
class VerifierConfig:
    """Tunable parameters for TriSensorVerifier (editable in VS Code!)."""
    # Arena physical bounds for fail-closed sanity check
    bounds_min: Tuple[float, float, float] = (-5.5, -5.5, -0.5)
    bounds_max: Tuple[float, float, float] = (5.5, 5.5, 3.5)

    # Instantaneous pairwise normalized disagreement threshold (spike / sudden bias)
    # Under nominal Gaussian noise in 3D, E[||e_i - e_j|| / sqrt(3*(s_i^2+s_j^2))] ~ 0.92
    spike_z_threshold: float = 3.2

    # Deterministic Page CUSUM drift detection parameters
    cusum_allowance_k: float = 1.65      # Slack above nominal expected z (~0.92)
    cusum_alarm_h: float = 4.0           # Cumulative alarm threshold for slow/heavy drift
    cusum_max_cap: float = 40.0          # Cap to prevent unbounded growth

    # Retimestamped-Freeze detector (LIVE01 #1 vulnerability mitigation)
    freeze_eps_m: float = 1e-4           # Max step delta considered "physically frozen"
    peer_motion_eps_m: float = 0.08      # Minimum peer displacement confirming robot moved
    freeze_consecutive_steps: int = 2    # Steps frozen while peers move before quarantine

    # Hysteresis recovery for transient faults (e.g. OUTLIER_BURSTS)
    enable_recovery: bool = True
    recovery_z_threshold: float = 2.0
    recovery_confirm_steps: int = 4      # Consecutive clean steps required to re-admit
    latch_freeze_fault: bool = True      # Keep frozen sensors quarantined once confirmed


@dataclass
class VerificationOutput:
    """Output emitted at every tick — strictly separates trusted vs. quarantined data."""
    step: int
    trusted: bool
    mode: str                                     # HEALTHY_3, DEGRADED_2_ISOLATED, FAIL_CLOSED_ABSTAIN
    action: str                                   # CONTINUE or ABSTAIN_SAFE_STOP
    display_pos: Optional[np.ndarray]             # Shown to user/UI (NEVER includes faulty sensor!)
    control_pos: Optional[np.ndarray]             # Used by controller/map (NEVER includes faulty sensor!)
    used_sensors: List[str] = field(default_factory=list)
    quarantined_sensors: Dict[str, str] = field(default_factory=dict)
    excluded_raw_values: Dict[str, List[float]] = field(default_factory=dict)
    pairwise_z: Dict[str, float] = field(default_factory=dict)
    pairwise_cusum: Dict[str, float] = field(default_factory=dict)
    audit_events: List[Dict[str, object]] = field(default_factory=list)


class TriSensorVerifier:
    """
    Self-verifying 3-sensor cross-checker with Page CUSUM, freeze detection,
    majority fault isolation, inverse-variance fusion, and fail-closed abstention.
    """

    def __init__(self, sensor_ids: Tuple[str, str, str], config: Optional[VerifierConfig] = None) -> None:
        if len(sensor_ids) != 3:
            raise ValueError("TriSensorVerifier requires exactly 3 sensor IDs.")
        self.sensor_ids = sensor_ids
        self.cfg = config or VerifierConfig()
        self.pairs: Tuple[Tuple[str, str], ...] = (
            (sensor_ids[0], sensor_ids[1]),
            (sensor_ids[1], sensor_ids[2]),
            (sensor_ids[0], sensor_ids[2]),
        )
        self.reset()

    def reset(self) -> None:
        self.cusum: Dict[str, float] = {f"{a}_vs_{b}": 0.0 for a, b in self.pairs}
        self.prev_positions: Dict[str, np.ndarray] = {}
        self.freeze_counters: Dict[str, int] = {sid: 0 for sid in self.sensor_ids}
        self.quarantined_reason: Dict[str, str] = {}
        self.clean_streak: Dict[str, int] = {sid: 0 for sid in self.sensor_ids}

    def _is_physically_valid(self, r: SensorReading) -> Tuple[bool, str]:
        if r.position is None or len(r.position) != 3:
            return False, "INVALID_SHAPE"
        if not bool(np.all(np.isfinite(r.position))):
            return False, "BLACKOUT_OR_NAN"
        b_min = np.asarray(self.cfg.bounds_min, dtype=np.float64)
        b_max = np.asarray(self.cfg.bounds_max, dtype=np.float64)
        if np.any(r.position < b_min) or np.any(r.position > b_max):
            return False, "OUT_OF_ARENA_BOUNDS"
        return True, "OK"

    @staticmethod
    def _normalized_pair_z(ra: SensorReading, rb: SensorReading) -> float:
        diff_norm = float(np.linalg.norm(ra.position - rb.position))
        denom = math.sqrt(3.0 * (ra.nominal_sigma ** 2 + rb.nominal_sigma ** 2))
        return diff_norm / max(denom, 1e-9)

    @staticmethod
    def _inverse_variance_fuse(readings: List[SensorReading]) -> np.ndarray:
        weights = np.array([1.0 / max(r.nominal_sigma ** 2, 1e-9) for r in readings], dtype=np.float64)
        weights /= np.sum(weights)
        fused = np.zeros(3, dtype=np.float64)
        for w, r in zip(weights, readings):
            fused += w * r.position
        return fused

    def verify_and_fuse(self, readings: Dict[str, SensorReading]) -> VerificationOutput:
        step = next(iter(readings.values())).step
        audit_events: List[Dict[str, object]] = []

        # --- Layer 1: Physical Validity Guard (NaN / Inf / Bounds) ---
        valid_ids: List[str] = []
        instant_rejected: Dict[str, str] = {}
        for sid in self.sensor_ids:
            r = readings[sid]
            ok, reason = self._is_physically_valid(r)
            if ok:
                valid_ids.append(sid)
            else:
                instant_rejected[sid] = reason
                self.quarantined_reason[sid] = reason
                self.clean_streak[sid] = 0
                audit_events.append({
                    "step": step,
                    "event": "PHYSICAL_REJECT",
                    "sensor_id": sid,
                    "reason": reason,
                })

        # --- Layer 2: Retimestamped-Freeze Detector ---
        # Detect sensor whose physical output does not change while peers genuinely move.
        step_deltas: Dict[str, float] = {}
        for sid in valid_ids:
            if sid in self.prev_positions:
                step_deltas[sid] = float(np.linalg.norm(readings[sid].position - self.prev_positions[sid]))

        for sid in list(valid_ids):
            if sid in step_deltas:
                peer_deltas = [step_deltas[p] for p in valid_ids if p != sid and p in step_deltas]
                peers_moving = len(peer_deltas) >= 1 and float(np.median(peer_deltas)) >= self.cfg.peer_motion_eps_m
                if step_deltas[sid] <= self.cfg.freeze_eps_m and peers_moving:
                    self.freeze_counters[sid] += 1
                else:
                    self.freeze_counters[sid] = 0

                if self.freeze_counters[sid] >= self.cfg.freeze_consecutive_steps:
                    reason = "RETIMESTAMPED_FREEZE"
                    instant_rejected[sid] = reason
                    self.quarantined_reason[sid] = reason
                    self.clean_streak[sid] = 0
                    valid_ids.remove(sid)
                    audit_events.append({
                        "step": step,
                        "event": "FREEZE_DETECTED",
                        "sensor_id": sid,
                        "reason": reason,
                        "delta_m": round(step_deltas[sid], 6),
                    })
                elif self.cfg.latch_freeze_fault and self.quarantined_reason.get(sid) == "RETIMESTAMPED_FREEZE":
                    instant_rejected[sid] = "RETIMESTAMPED_FREEZE"
                    valid_ids.remove(sid)

        # Update previous valid positions (always store raw valid reading for next step delta)
        for sid in self.sensor_ids:
            if np.all(np.isfinite(readings[sid].position)):
                self.prev_positions[sid] = readings[sid].position.copy()

        # --- Layer 3: Pairwise Normalized Disagreement + Deterministic Page CUSUM ---
        pairwise_z: Dict[str, float] = {}
        pair_bad: Dict[Tuple[str, str], bool] = {}
        pair_reason: Dict[Tuple[str, str], str] = {}

        for a, b in self.pairs:
            key = f"{a}_vs_{b}"
            if a in valid_ids and b in valid_ids:
                z = self._normalized_pair_z(readings[a], readings[b])
                pairwise_z[key] = round(z, 4)
                # Deterministic Page CUSUM update (NOT Ville-anytime-valid)
                s_new = max(0.0, self.cusum[key] + (z - self.cfg.cusum_allowance_k))
                self.cusum[key] = min(self.cfg.cusum_max_cap, s_new)

                is_spike = z > self.cfg.spike_z_threshold
                is_drift = self.cusum[key] > self.cfg.cusum_alarm_h
                pair_bad[(a, b)] = is_spike or is_drift
                if is_spike and is_drift:
                    pair_reason[(a, b)] = "DRIFT_AND_SPIKE"
                elif is_drift:
                    pair_reason[(a, b)] = "CUSUM_DRIFT"
                elif is_spike:
                    pair_reason[(a, b)] = "INSTANT_DISAGREEMENT"
                else:
                    pair_reason[(a, b)] = "OK"
            else:
                pairwise_z[key] = float("nan")
                pair_bad[(a, b)] = True
                pair_reason[(a, b)] = "SENSOR_UNAVAILABLE"

        # --- Layer 4A: Tri-Sensor Consensus Candidate Selection ---
        candidate_sensors: List[str] = []
        active_quarantine: Dict[str, str] = dict(instant_rejected)
        already_abstained = False

        if len(valid_ids) == 3:
            s0, s1, s2 = self.sensor_ids
            bad_01 = pair_bad[(s0, s1)]
            bad_12 = pair_bad[(s1, s2)]
            bad_02 = pair_bad[(s0, s2)]

            if not bad_01 and not bad_12 and not bad_02:
                candidate_sensors = list(self.sensor_ids)

            elif bad_01 and bad_02 and not bad_12:
                # s0 disagrees with BOTH s1 and s2, while s1 & s2 agree -> Isolate s0!
                reason = pair_reason[(s0, s1)] if pair_reason[(s0, s1)] != "OK" else pair_reason[(s0, s2)]
                self.quarantined_reason[s0] = reason
                self.clean_streak[s0] = 0
                active_quarantine[s0] = reason
                candidate_sensors = [s1, s2]
                audit_events.append({"step": step, "event": "QUARANTINE_ISOLATED", "sensor_id": s0, "reason": reason})

            elif bad_01 and bad_12 and not bad_02:
                # s1 disagrees with BOTH s0 and s2, while s0 & s2 agree -> Isolate s1!
                reason = pair_reason[(s0, s1)] if pair_reason[(s0, s1)] != "OK" else pair_reason[(s1, s2)]
                self.quarantined_reason[s1] = reason
                self.clean_streak[s1] = 0
                active_quarantine[s1] = reason
                candidate_sensors = [s0, s2]
                audit_events.append({"step": step, "event": "QUARANTINE_ISOLATED", "sensor_id": s1, "reason": reason})

            elif bad_02 and bad_12 and not bad_01:
                # s2 disagrees with BOTH s0 and s1, while s0 & s1 agree -> Isolate s2!
                reason = pair_reason[(s0, s2)] if pair_reason[(s0, s2)] != "OK" else pair_reason[(s1, s2)]
                self.quarantined_reason[s2] = reason
                self.clean_streak[s2] = 0
                active_quarantine[s2] = reason
                candidate_sensors = [s0, s1]
                audit_events.append({"step": step, "event": "QUARANTINE_ISOLATED", "sensor_id": s2, "reason": reason})

            elif (bad_01 + bad_12 + bad_02) == 1:
                # Borderline single-pair disagreement (transient noise / early drift onset):
                # Keep the tightest agreeing pair conservatively; recovery gate below still applies.
                good_pairs = [
                    (p, pairwise_z[f"{p[0]}_vs_{p[1]}"])
                    for p in self.pairs
                    if not pair_bad[p]
                ]
                best_pair = min(good_pairs, key=lambda item: item[1])[0]
                odd_one = [s for s in self.sensor_ids if s not in best_pair][0]
                active_quarantine[odd_one] = "BORDERLINE_EXCLUDED"
                if odd_one in self.quarantined_reason:
                    self.clean_streak[odd_one] = 0
                candidate_sensors = list(best_pair)
            else:
                # All 3 pairs disagree -> NO MAJORITY CONSENSUS -> FAIL CLOSED!
                for sid in self.sensor_ids:
                    active_quarantine[sid] = "NO_MAJORITY_CONSENSUS"
                    if sid in self.quarantined_reason:
                        self.clean_streak[sid] = 0
                candidate_sensors = []
                already_abstained = True
                audit_events.append({
                    "step": step,
                    "event": "FAIL_CLOSED_ABSTAIN",
                    "reason": "ALL_PAIRS_DISAGREE",
                })

        elif len(valid_ids) == 2:
            a, b = valid_ids[0], valid_ids[1]
            pair_key = (a, b) if (a, b) in pair_bad else (b, a)
            if not pair_bad[pair_key]:
                candidate_sensors = [a, b]
            else:
                # 1 sensor already dead/frozen AND the remaining 2 disagree -> FAIL CLOSED!
                for sid in valid_ids:
                    active_quarantine[sid] = "DUAL_FAULT_NO_QUORUM"
                    if sid in self.quarantined_reason:
                        self.clean_streak[sid] = 0
                candidate_sensors = []
                already_abstained = True
                audit_events.append({
                    "step": step,
                    "event": "FAIL_CLOSED_ABSTAIN",
                    "reason": "DUAL_FAULT_NO_QUORUM",
                })
        else:
            # <= 1 valid sensor left -> Cannot cross-verify -> FAIL CLOSED!
            for sid in valid_ids:
                active_quarantine[sid] = "INSUFFICIENT_QUORUM"
                if sid in self.quarantined_reason:
                    self.clean_streak[sid] = 0
            candidate_sensors = []
            already_abstained = True
            audit_events.append({
                "step": step,
                "event": "FAIL_CLOSED_ABSTAIN",
                "reason": "INSUFFICIENT_QUORUM",
            })

        # --- Layer 4B: Universal Recovery Probation & Quarantine Enforcement Gate ---
        # Enforced across ALL fusion branches so no quarantined sensor can ever leak
        # into display_pos or control_pos before completing recovery_confirm_steps.
        unquarantined_candidates = [s for s in candidate_sensors if s not in self.quarantined_reason]
        quarantined_candidates = [s for s in candidate_sensors if s in self.quarantined_reason]
        used_sensors: List[str] = list(unquarantined_candidates)

        for sid in quarantined_candidates:
            if self.cfg.latch_freeze_fault and self.quarantined_reason.get(sid) == "RETIMESTAMPED_FREEZE":
                self.clean_streak[sid] = 0
                active_quarantine[sid] = "RETIMESTAMPED_FREEZE"
                continue

            # Require at least one unquarantined agreeing peer to vouch for recovery
            vouching_peers = unquarantined_candidates
            if self.cfg.enable_recovery and len(vouching_peers) >= 1:
                peer_pairs = [
                    (a, b) for a, b in self.pairs
                    if sid in (a, b) and (b if a == sid else a) in candidate_sensors
                ]
                clean_against_peers = bool(peer_pairs) and all(
                    (not pair_bad[p])
                    and math.isfinite(pairwise_z[f"{p[0]}_vs_{p[1]}"])
                    and pairwise_z[f"{p[0]}_vs_{p[1]}"] <= self.cfg.recovery_z_threshold
                    for p in peer_pairs
                )
            else:
                clean_against_peers = False

            if clean_against_peers:
                self.clean_streak[sid] += 1
                if self.clean_streak[sid] >= self.cfg.recovery_confirm_steps:
                    old_r = self.quarantined_reason.pop(sid)
                    self.clean_streak[sid] = 0
                    used_sensors.append(sid)
                    audit_events.append({
                        "step": step,
                        "event": "SENSOR_RECOVERED",
                        "sensor_id": sid,
                        "previous_reason": old_r,
                    })
                else:
                    active_quarantine[sid] = (
                        f"RECOVERY_PROBATION({self.clean_streak[sid]}/{self.cfg.recovery_confirm_steps})"
                    )
            else:
                self.clean_streak[sid] = 0
                active_quarantine[sid] = self.quarantined_reason[sid]

        # Preserve deterministic sensor ordering
        used_sensors = [s for s in self.sensor_ids if s in used_sensors]

        if len(used_sensors) < 2 and not already_abstained:
            # Remaining non-quarantined quorum is < 2 (e.g. a peer is still in probation) -> FAIL CLOSED!
            for sid in used_sensors:
                active_quarantine[sid] = "INSUFFICIENT_TRUSTED_QUORUM_AFTER_QUARANTINE"
            used_sensors = []
            audit_events.append({
                "step": step,
                "event": "FAIL_CLOSED_ABSTAIN",
                "reason": "INSUFFICIENT_TRUSTED_QUORUM_AFTER_QUARANTINE",
            })

        # Hard safety invariant: no currently quarantined sensor may enter fusion
        assert all(s not in self.quarantined_reason for s in used_sensors), (
            f"Invariant violation: quarantined sensor leaked into used_sensors={used_sensors}"
        )

        # --- Final Output Packaging (Strictly Exclude Quarantined Values) ---
        excluded_raw: Dict[str, List[float]] = {}
        for sid in active_quarantine:
            pos = readings[sid].position
            excluded_raw[sid] = [
                round(float(v), 5) if math.isfinite(float(v)) else None  # type: ignore[misc]
                for v in pos
            ]

        if len(used_sensors) >= 2:
            fused = self._inverse_variance_fuse([readings[s] for s in used_sensors])
            mode = "HEALTHY_3" if len(used_sensors) == 3 else "DEGRADED_2_ISOLATED"
            return VerificationOutput(
                step=step,
                trusted=True,
                mode=mode,
                action="CONTINUE",
                display_pos=fused.copy(),
                control_pos=fused.copy(),
                used_sensors=used_sensors,
                quarantined_sensors=active_quarantine,
                excluded_raw_values=excluded_raw,
                pairwise_z=pairwise_z,
                pairwise_cusum={k: round(v, 4) for k, v in self.cusum.items()},
                audit_events=audit_events,
            )

        # Fail-closed: NEVER display or feed corrupted sensor values!
        return VerificationOutput(
            step=step,
            trusted=False,
            mode="FAIL_CLOSED_ABSTAIN",
            action="ABSTAIN_SAFE_STOP",
            display_pos=None,
            control_pos=None,
            used_sensors=[],
            quarantined_sensors=active_quarantine,
            excluded_raw_values=excluded_raw,
            pairwise_z=pairwise_z,
            pairwise_cusum={k: round(v, 4) for k, v in self.cusum.items()},
            audit_events=audit_events,
        )


# ---------------------------------------------------------------------------
# Comparison Baselines (for fair scientific A/B/C benchmarking)
# ---------------------------------------------------------------------------

class NaiveAverageFusion:
    """Arm A: Blindly averages all finite sensor readings without self-verification."""

    def __init__(self, sensor_ids: Tuple[str, str, str]) -> None:
        self.sensor_ids = sensor_ids

    def reset(self) -> None:
        pass

    def verify_and_fuse(self, readings: Dict[str, SensorReading]) -> VerificationOutput:
        step = next(iter(readings.values())).step
        finite = [readings[s] for s in self.sensor_ids if np.all(np.isfinite(readings[s].position))]
        if not finite:
            return VerificationOutput(
                step=step, trusted=False, mode="NAIVE_NO_DATA", action="ABSTAIN_SAFE_STOP",
                display_pos=None, control_pos=None,
            )
        avg = np.mean([r.position for r in finite], axis=0)
        return VerificationOutput(
            step=step, trusted=True, mode="NAIVE_AVG", action="CONTINUE",
            display_pos=avg.copy(), control_pos=avg.copy(),
            used_sensors=[r.sensor_id for r in finite],
        )


class TwoSensorMinSigmaBaseline:
    """
    Arm B: Replicates the limitation of src/aegis/sensing.py (SensorArbitrator).
    Compares primary (S1_VIO) vs verifier (S2_LIDAR); on mismatch falls back to
    the sensor with smaller nominal sigma (S1_VIO). Works when S2 fails, but
    fails catastrophically whenever S1_VIO itself drifts or freezes!
    """

    def __init__(self, sensor_ids: Tuple[str, str, str], mismatch_z: float = 3.2) -> None:
        self.sensor_ids = sensor_ids
        self.mismatch_z = mismatch_z

    def reset(self) -> None:
        pass

    def verify_and_fuse(self, readings: Dict[str, SensorReading]) -> VerificationOutput:
        step = next(iter(readings.values())).step
        r1 = readings[self.sensor_ids[0]]
        r2 = readings[self.sensor_ids[1]]
        ok1 = bool(np.all(np.isfinite(r1.position)))
        ok2 = bool(np.all(np.isfinite(r2.position)))

        if ok1 and ok2:
            diff = float(np.linalg.norm(r1.position - r2.position))
            denom = math.sqrt(3.0 * (r1.nominal_sigma ** 2 + r2.nominal_sigma ** 2))
            if diff / max(denom, 1e-9) > self.mismatch_z:
                # Mirror sensing.py: pick sensor with smaller nominal sigma (r1)
                chosen = r1 if r1.nominal_sigma <= r2.nominal_sigma else r2
                return VerificationOutput(
                    step=step, trusted=True, mode="TWO_SENSOR_FALLBACK_MIN_SIGMA",
                    action="CONTINUE", display_pos=chosen.position.copy(),
                    control_pos=chosen.position.copy(), used_sensors=[chosen.sensor_id],
                )
            w1 = 1.0 / (r1.nominal_sigma ** 2)
            w2 = 1.0 / (r2.nominal_sigma ** 2)
            fused = (w1 * r1.position + w2 * r2.position) / (w1 + w2)
            return VerificationOutput(
                step=step, trusted=True, mode="TWO_SENSOR_FUSED",
                action="CONTINUE", display_pos=fused.copy(),
                control_pos=fused.copy(), used_sensors=[r1.sensor_id, r2.sensor_id],
            )
        if ok1:
            return VerificationOutput(
                step=step, trusted=True, mode="TWO_SENSOR_SINGLE_S1", action="CONTINUE",
                display_pos=r1.position.copy(), control_pos=r1.position.copy(), used_sensors=[r1.sensor_id],
            )
        if ok2:
            return VerificationOutput(
                step=step, trusted=True, mode="TWO_SENSOR_SINGLE_S2", action="CONTINUE",
                display_pos=r2.position.copy(), control_pos=r2.position.copy(), used_sensors=[r2.sensor_id],
            )
        return VerificationOutput(
            step=step, trusted=False, mode="TWO_SENSOR_LOST", action="ABSTAIN_SAFE_STOP",
            display_pos=None, control_pos=None,
        )
