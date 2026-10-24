"""
NEXVIA AEGIS V9.0 — Symmetric Fail-Closed Anchor/Range Disagreement Gate (Decision 3).

Implements Section 3.4.3 of `docs/v9_experiment_protocol.md`:
- Treats neither range nor anchor as an unquestionable oracle.
- Parameterizes normalized radial discrepancy:
      Delta_tilde_{ar,t} = | ||z_{anc,t}||_2 - r_t | / sqrt(sigma_anc^2 + sigma_r^2)
  against candidate tolerance tau_{ar}^{(j)} (demoting V8's 0.35 m ~= 5.47 * sigma_ar
  to an unvalidated Tier-5 candidate rather than a certified safety bound).
- Defaults to fail-closed `ABSTAIN_DISAGREEMENT` whenever Delta_tilde_{ar,t} > tau_{ar},
  overriding ONLY when two valid anchor/range observation epochs t_1 < t_2 satisfy all
  prespecified drift-free vector-chord and directional/curvature range-increment criteria:
    1. t_2 - t_1 >= min_epoch_separation_steps (10)
    2. Unclamped positive ranges r_{t_1} > 1e-4 and r_{t_2} > 1e-4
    3. Drift-free vector chord ||Delta z_{k*, t_1->t_2}||_2 >= min_chord_m (0.40 m)
       with two-epoch anchor-chord agreement
       ||Delta z_{anc} - Delta z_{k*}||_2 <= 3.0 * sqrt(2 * (sigma_anc^2 + sigma_{k*}^2))
    4. Range-increment curvature separation rejecting static anchor corruption (e.g.,
       corrupted_bias = (1.2, -1.0) m in CORRUPTED_ANCHOR_STRESS, which cancels in
       Delta z_{anc} = z_{anc,t_2} - z_{anc,t_1}!).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import math
import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading


class AnchorRangeStatus(str, Enum):
    """Symmetric anchor/range gate verdict."""

    NO_OBSERVATION = "NO_OBSERVATION"
    INVALID_INPUT = "INVALID_INPUT"
    CONSISTENT = "CONSISTENT"
    CORROBORATED_ANCHOR_RANGE_BIASED = "CORROBORATED_ANCHOR_RANGE_BIASED"
    CORROBORATED_RANGE_ANCHOR_CORRUPTED = "CORROBORATED_RANGE_ANCHOR_CORRUPTED"
    ABSTAIN_DISAGREEMENT = "ABSTAIN_DISAGREEMENT"


@dataclass(frozen=True)
class _AnchorEpochRecord:
    """Stored valid observation epoch for two-epoch displacement corroboration."""

    step: int
    z_anchor: np.ndarray
    sigma_anchor: float
    range_dist: float
    sigma_range: float
    vec_estimates: dict[str, np.ndarray]
    vec_sigmas: dict[str, float]
    signed_discrepancy: float
    sigma_ar: float
    normalized_discrepancy: float


@dataclass(frozen=True)
class AnchorRangeGateResult:
    """Detailed audit output for SymmetricAnchorRangeGate."""

    status: AnchorRangeStatus
    normalized_discrepancy: float
    raw_discrepancy_m: float
    tau_ar: float
    disagreement_ever_observed: bool
    corroborating_sensor: str | None
    chord_length_m: float
    delta_r_observed: float
    delta_r_pred_anchor: float
    delta_r_pred_range: float
    reason: str


class SymmetricAnchorRangeGate:
    """
    Fail-closed symmetric disagreement gate between AEGIS-Anchor and scalar RangeSensor.
    """

    def __init__(
        self,
        tau_ar: float = 4.60,
        min_chord_m: float = 0.40,
        min_epoch_separation_steps: int = 10,
        min_unclamped_range_m: float = 1e-4,
    ) -> None:
        if not math.isfinite(tau_ar) or tau_ar <= 0.0:
            raise ValueError(f"tau_ar must be finite and > 0, got {tau_ar}.")
        if not math.isfinite(min_chord_m) or min_chord_m <= 0.0:
            raise ValueError(f"min_chord_m must be finite and > 0, got {min_chord_m}.")
        if min_epoch_separation_steps < 1:
            raise ValueError("min_epoch_separation_steps must be >= 1.")

        self.tau_ar: float = float(tau_ar)
        self.min_chord_m: float = float(min_chord_m)
        self.min_epoch_separation_steps: int = int(min_epoch_separation_steps)
        self.min_unclamped_range_m: float = float(min_unclamped_range_m)

        self._epochs: list[_AnchorEpochRecord] = []
        self._disagreement_ever_observed: bool = False
        self._latest_status: AnchorRangeStatus = AnchorRangeStatus.NO_OBSERVATION
        self._invalid_latched: bool = False

    @property
    def disagreement_ever_observed(self) -> bool:
        return self._disagreement_ever_observed

    @property
    def latest_status(self) -> AnchorRangeStatus:
        return self._latest_status

    @property
    def num_epochs(self) -> int:
        return len(self._epochs)

    def reset(self) -> None:
        self._epochs.clear()
        self._disagreement_ever_observed = False
        self._latest_status = AnchorRangeStatus.NO_OBSERVATION
        self._invalid_latched = False

    def has_unresolved_disagreement(self) -> bool:
        """True if an anchor/range disagreement occurred and has not been corroborated."""
        if self._invalid_latched:
            return True
        if not self._disagreement_ever_observed:
            return False
        return self._latest_status not in (
            AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED,
            AnchorRangeStatus.CORROBORATED_RANGE_ANCHOR_CORRUPTED,
        )

    def evaluate(
        self,
        anchor_reading: AnchorReading | None,
        range_reading: RangeReading,
        reading_a: SensorReading,
        reading_b: SensorReading,
        *,
        step: int,
        drift_suspected: Mapping[str, bool] | None = None,
        calibrated_biases: Mapping[str, np.ndarray] | None = None,
        calibrated_valid_flags: Mapping[str, bool] | None = None,
    ) -> AnchorRangeGateResult:
        """
        Evaluates anchor/range agreement on step `step` using only observable sensor fields.
        """
        if self._invalid_latched:
            return self._make_result(
                AnchorRangeStatus.INVALID_INPUT,
                reason="LATCHED_INVALID_SENSOR_INPUT",
            )

        # Validate active inputs for NaN / Inf / malformed dimensions even if only one is valid
        if anchor_reading is not None and anchor_reading.valid:
            z_anc = np.asarray(anchor_reading.estimate, dtype=np.float64)
            sig_anc = float(anchor_reading.sigma)
            if (
                z_anc.shape != (2,)
                or not np.all(np.isfinite(z_anc))
                or not math.isfinite(sig_anc)
                or sig_anc <= 0.0
            ):
                self._invalid_latched = True
                self._latest_status = AnchorRangeStatus.INVALID_INPUT
                return self._make_result(
                    AnchorRangeStatus.INVALID_INPUT,
                    reason="MALFORMED_ANCHOR_READING",
                )
        else:
            return self._make_result(
                AnchorRangeStatus.NO_OBSERVATION,
                reason="ANCHOR_NOT_QUERIED_OR_INVALID",
            )

        if range_reading.valid:
            r_dist = float(range_reading.distance)
            sig_r = float(range_reading.sigma)
            if (
                not math.isfinite(r_dist)
                or r_dist < 0.0
                or not math.isfinite(sig_r)
                or sig_r <= 0.0
            ):
                self._invalid_latched = True
                self._latest_status = AnchorRangeStatus.INVALID_INPUT
                return self._make_result(
                    AnchorRangeStatus.INVALID_INPUT,
                    reason="MALFORMED_RANGE_READING",
                )
        else:
            # Anchor arrived on a step where range dropped out: cannot verify cross-modally yet
            return self._make_result(
                AnchorRangeStatus.NO_OBSERVATION,
                reason="RANGE_DROPPED_ON_ANCHOR_STEP",
            )

        vec_ests: dict[str, np.ndarray] = {}
        vec_sigs: dict[str, float] = {}
        for key, rd in (("vec_a", reading_a), ("vec_b", reading_b)):
            if rd.valid:
                arr = np.asarray(rd.estimate, dtype=np.float64)
                sig_v = float(rd.sigma)
                if (
                    arr.shape != (2,)
                    or not np.all(np.isfinite(arr))
                    or not math.isfinite(sig_v)
                    or sig_v <= 0.0
                ):
                    self._invalid_latched = True
                    self._latest_status = AnchorRangeStatus.INVALID_INPUT
                    return self._make_result(
                        AnchorRangeStatus.INVALID_INPUT,
                        reason=f"MALFORMED_{key.upper()}_READING",
                    )
                vec_ests[key] = arr.copy()
                vec_sigs[key] = sig_v

        sigma_ar = math.sqrt(sig_anc**2 + sig_r**2)
        anc_norm = float(np.linalg.norm(z_anc))
        signed_disc = anc_norm - r_dist
        raw_disc = abs(signed_disc)
        inst_norm_disc = raw_disc / sigma_ar

        epoch = _AnchorEpochRecord(
            step=int(step),
            z_anchor=z_anc.copy(),
            sigma_anchor=sig_anc,
            range_dist=r_dist,
            sigma_range=sig_r,
            vec_estimates=vec_ests,
            vec_sigmas=vec_sigs,
            signed_discrepancy=signed_disc,
            sigma_ar=sigma_ar,
            normalized_discrepancy=inst_norm_disc,
        )
        self._epochs.append(epoch)

        # Multi-epoch inverse-variance pooled signed radial discrepancy across valid anchor
        # epochs (exact unit variance under zero anchor/range bias, gaining sqrt(m) power
        # against persistent range shifts such as -0.30m in COMPOUND_ANTIPODAL_RANGE_SHIFT).
        inv_var_sum = sum(1.0 / (ep.sigma_ar**2) for ep in self._epochs)
        weighted_signed_sum = sum(ep.signed_discrepancy / (ep.sigma_ar**2) for ep in self._epochs)
        pooled_norm_disc = abs(weighted_signed_sum) / math.sqrt(max(inv_var_sum, 1e-12))
        norm_disc = max(inst_norm_disc, pooled_norm_disc)

        drift_map = drift_suspected or {}
        bias_map = calibrated_biases or {}
        cal_valid_map = calibrated_valid_flags or {}

        # Even when current norm_disc <= tau_ar, if a previous epoch disagreed OR if we have
        # a >= 0.40 m baseline that exposes static anchor corruption (where epoch 1 happened
        # by geometric coincidence to satisfy ||d_1 + b_anc|| ~= r_1), run two-epoch check!
        if norm_disc > self.tau_ar:
            self._disagreement_ever_observed = True

        corroboration = self._check_two_epoch_corroboration(
            epoch,
            drift_map=drift_map,
            bias_map=bias_map,
            cal_valid_map=cal_valid_map,
        )

        if not self._disagreement_ever_observed:
            # Check if a 2-epoch baseline caught a hidden static anchor corruption
            if (
                corroboration is not None
                and corroboration.status == AnchorRangeStatus.CORROBORATED_RANGE_ANCHOR_CORRUPTED
            ):
                self._disagreement_ever_observed = True
                self._latest_status = AnchorRangeStatus.ABSTAIN_DISAGREEMENT
                return self._make_result(
                    AnchorRangeStatus.ABSTAIN_DISAGREEMENT,
                    normalized_discrepancy=norm_disc,
                    raw_discrepancy_m=raw_disc,
                    corroborating_sensor=corroboration.corroborating_sensor,
                    chord_length_m=corroboration.chord_length_m,
                    delta_r_observed=corroboration.delta_r_observed,
                    delta_r_pred_anchor=corroboration.delta_r_pred_anchor,
                    delta_r_pred_range=corroboration.delta_r_pred_range,
                    reason="STATIC_ANCHOR_BIAS_DETECTED_ACROSS_EPOCHS",
                )

            self._latest_status = AnchorRangeStatus.CONSISTENT
            return self._make_result(
                AnchorRangeStatus.CONSISTENT,
                normalized_discrepancy=norm_disc,
                raw_discrepancy_m=raw_disc,
                reason="ANCHOR_AND_RANGE_CONSISTENT",
            )

        # Disagreement has been observed (either on this step or an earlier step).
        # Default fail-closed unless full two-epoch corroboration unambiguously succeeds.
        if corroboration is not None and corroboration.status in (
            AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED,
            AnchorRangeStatus.CORROBORATED_RANGE_ANCHOR_CORRUPTED,
        ):
            self._latest_status = corroboration.status
            return corroboration

        self._latest_status = AnchorRangeStatus.ABSTAIN_DISAGREEMENT
        if corroboration is not None:
            return corroboration
        return self._make_result(
            AnchorRangeStatus.ABSTAIN_DISAGREEMENT,
            normalized_discrepancy=norm_disc,
            raw_discrepancy_m=raw_disc,
            reason="SINGLE_EPOCH_DISAGREEMENT_FAIL_CLOSED",
        )

    def _check_two_epoch_corroboration(
        self,
        e2: _AnchorEpochRecord,
        *,
        drift_map: Mapping[str, bool],
        bias_map: Mapping[str, np.ndarray],
        cal_valid_map: Mapping[str, bool],
    ) -> AnchorRangeGateResult | None:
        if len(self._epochs) < 2:
            return None

        best_failure: AnchorRangeGateResult | None = None

        # Search prior valid epochs e1 from earliest to maximize spatial baseline L
        for e1 in self._epochs[:-1]:
            dt_steps = e2.step - e1.step
            if dt_steps < self.min_epoch_separation_steps:
                best_failure = self._make_result(
                    AnchorRangeStatus.ABSTAIN_DISAGREEMENT,
                    normalized_discrepancy=e2.normalized_discrepancy,
                    raw_discrepancy_m=abs(float(np.linalg.norm(e2.z_anchor)) - e2.range_dist),
                    reason=f"EPOCH_SEPARATION_TOO_SHORT ({dt_steps} < {self.min_epoch_separation_steps})",
                )
                continue

            if (
                e1.range_dist <= self.min_unclamped_range_m
                or e2.range_dist <= self.min_unclamped_range_m
            ):
                best_failure = self._make_result(
                    AnchorRangeStatus.ABSTAIN_DISAGREEMENT,
                    normalized_discrepancy=e2.normalized_discrepancy,
                    raw_discrepancy_m=abs(float(np.linalg.norm(e2.z_anchor)) - e2.range_dist),
                    reason="CLAMPED_ZERO_RANGE_REJECTED",
                )
                continue

            delta_r_obs = e2.range_dist - e1.range_dist
            delta_z_anc = e2.z_anchor - e1.z_anchor

            for k_name in ("vec_a", "vec_b"):
                if k_name not in e1.vec_estimates or k_name not in e2.vec_estimates:
                    continue

                if bool(drift_map.get(k_name, False)):
                    best_failure = self._make_result(
                        AnchorRangeStatus.ABSTAIN_DISAGREEMENT,
                        normalized_discrepancy=e2.normalized_discrepancy,
                        raw_discrepancy_m=abs(float(np.linalg.norm(e2.z_anchor)) - e2.range_dist),
                        corroborating_sensor=k_name,
                        reason=f"COMMON_MODE_DRIFT_SUSPECTED_ON_{k_name.upper()}",
                    )
                    continue

                delta_z_k = e2.vec_estimates[k_name] - e1.vec_estimates[k_name]
                chord_len = float(np.linalg.norm(delta_z_k))
                if chord_len < self.min_chord_m:
                    best_failure = self._make_result(
                        AnchorRangeStatus.ABSTAIN_DISAGREEMENT,
                        normalized_discrepancy=e2.normalized_discrepancy,
                        raw_discrepancy_m=abs(float(np.linalg.norm(e2.z_anchor)) - e2.range_dist),
                        corroborating_sensor=k_name,
                        chord_length_m=chord_len,
                        reason=f"INSUFFICIENT_CHORD_DISPLACEMENT ({chord_len:.3f}m < {self.min_chord_m:.2f}m)",
                    )
                    continue

                sig_k = max(e1.vec_sigmas[k_name], e2.vec_sigmas[k_name])
                sig_anc = max(e1.sigma_anchor, e2.sigma_anchor)
                sig_r = max(e1.sigma_range, e2.sigma_range)

                # Condition 1: Two-epoch anchor-chord vs vector-chord consistency.
                # Note: static anchor bias cancels here, so Condition 2 below is mandatory!
                chord_tol = 3.0 * math.sqrt(2.0 * (sig_anc**2 + sig_k**2))
                chord_diff = float(np.linalg.norm(delta_z_anc - delta_z_k))
                if chord_diff > chord_tol:
                    best_failure = self._make_result(
                        AnchorRangeStatus.ABSTAIN_DISAGREEMENT,
                        normalized_discrepancy=e2.normalized_discrepancy,
                        raw_discrepancy_m=abs(float(np.linalg.norm(e2.z_anchor)) - e2.range_dist),
                        corroborating_sensor=k_name,
                        chord_length_m=chord_len,
                        reason="ANCHOR_VECTOR_CHORD_MISMATCH",
                    )
                    continue

                # Condition 2: Directional / spherical-curvature range-increment test.
                # Anchor position hypothesis at t1: d_anc_1 = z_{anc,1}
                pred_dr_anc = float(
                    np.linalg.norm(e1.z_anchor + delta_z_k) - np.linalg.norm(e1.z_anchor)
                )

                # Range-circle position hypothesis at t1:
                if k_name in bias_map:
                    d_rng_1 = e1.vec_estimates[k_name] - np.asarray(
                        bias_map[k_name], dtype=np.float64
                    )
                else:
                    anc_norm_1 = float(np.linalg.norm(e1.z_anchor))
                    u_dir = (
                        e1.z_anchor / anc_norm_1
                        if anc_norm_1 > 1e-6
                        else np.array([1.0, 0.0], dtype=np.float64)
                    )
                    d_rng_1 = e1.range_dist * u_dir

                pred_dr_rng = float(np.linalg.norm(d_rng_1 + delta_z_k) - np.linalg.norm(d_rng_1))
                sigma_dr = math.sqrt(2.0 * (sig_r**2 + sig_k**2 + sig_anc**2))

                err_anc = abs(pred_dr_anc - delta_r_obs)
                err_rng = abs(pred_dr_rng - delta_r_obs)

                if err_anc <= 2.5 * sigma_dr and err_rng > 3.5 * sigma_dr:
                    return self._make_result(
                        AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED,
                        normalized_discrepancy=e2.normalized_discrepancy,
                        raw_discrepancy_m=abs(float(np.linalg.norm(e2.z_anchor)) - e2.range_dist),
                        corroborating_sensor=k_name,
                        chord_length_m=chord_len,
                        delta_r_observed=delta_r_obs,
                        delta_r_pred_anchor=pred_dr_anc,
                        delta_r_pred_range=pred_dr_rng,
                        reason="ANCHOR_CORROBORATED_STATIC_RANGE_BIAS_IDENTIFIED",
                    )

                if (
                    err_anc > 3.5 * sigma_dr
                    and bool(cal_valid_map.get(k_name, False))
                    and err_rng <= 2.5 * sigma_dr
                ):
                    return self._make_result(
                        AnchorRangeStatus.CORROBORATED_RANGE_ANCHOR_CORRUPTED,
                        normalized_discrepancy=e2.normalized_discrepancy,
                        raw_discrepancy_m=abs(float(np.linalg.norm(e2.z_anchor)) - e2.range_dist),
                        corroborating_sensor=k_name,
                        chord_length_m=chord_len,
                        delta_r_observed=delta_r_obs,
                        delta_r_pred_anchor=pred_dr_anc,
                        delta_r_pred_range=pred_dr_rng,
                        reason="RANGE_CORROBORATED_STATIC_ANCHOR_CORRUPTION_REJECTED",
                    )

                best_failure = self._make_result(
                    AnchorRangeStatus.ABSTAIN_DISAGREEMENT,
                    normalized_discrepancy=e2.normalized_discrepancy,
                    raw_discrepancy_m=abs(float(np.linalg.norm(e2.z_anchor)) - e2.range_dist),
                    corroborating_sensor=k_name,
                    chord_length_m=chord_len,
                    delta_r_observed=delta_r_obs,
                    delta_r_pred_anchor=pred_dr_anc,
                    delta_r_pred_range=pred_dr_rng,
                    reason="AMBIGUOUS_CURVATURE_SEPARATION_FAIL_CLOSED",
                )

        return best_failure

    def _make_result(
        self,
        status: AnchorRangeStatus,
        *,
        normalized_discrepancy: float = 0.0,
        raw_discrepancy_m: float = 0.0,
        corroborating_sensor: str | None = None,
        chord_length_m: float = 0.0,
        delta_r_observed: float = 0.0,
        delta_r_pred_anchor: float = 0.0,
        delta_r_pred_range: float = 0.0,
        reason: str = "",
    ) -> AnchorRangeGateResult:
        return AnchorRangeGateResult(
            status=status,
            normalized_discrepancy=float(normalized_discrepancy),
            raw_discrepancy_m=float(raw_discrepancy_m),
            tau_ar=self.tau_ar,
            disagreement_ever_observed=self._disagreement_ever_observed,
            corroborating_sensor=corroborating_sensor,
            chord_length_m=float(chord_length_m),
            delta_r_observed=float(delta_r_observed),
            delta_r_pred_anchor=float(delta_r_pred_anchor),
            delta_r_pred_range=float(delta_r_pred_range),
            reason=reason,
        )
