"""
NEXVIA AEGIS V9.0 — Risk-Calibrated Runtime-Assurance Controller (`AegisV9Controller`).

Integrates Approved Preregistration Decisions 1–4 (`docs/v9_risk_calibration_design.md`,
`docs/v9_experiment_protocol.md`):
- Decision 1: Parallel Channel A (exact gamma=1.0 nonnegative Ville e-process mixture) and
  Channel B (Page CUSUM drift detector, explicitly NOT Ville-anytime-valid), keeping
  monitor false alarms, fault detection delay, and episode-level selective risk distinct.
- Decision 2: Disjoint per-sensor bias calibration (`vec_a`, `vec_b`) over I_fit={1..22},
  I_gap={23,24}, I_val={25..36} with immutable post-fit bias freeze and single-sensor
  fault/dropout isolation.
- Decision 3: Fail-closed symmetric anchor/range disagreement gate (`SymmetricAnchorRangeGate`)
  defaulting to `"ABSTAIN"` unless two-epoch drift-free chord + curvature corroboration holds.
- Decision 4: Strict four-input sensor-interface parity:
      update(reading_a, reading_b, range_reading, anchor_reading=None, step=0)
  accessing ONLY observable fields (`.estimate`, `.distance`, `.sigma`, `.valid`) and past
  controller actions, never ground-truth sensor `.bias`, `.drift`, `.anomaly`, or world state.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from aegis.next.velocity_controller import KinematicVelocityController, VelocityProfileConfig
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.anchor_range_gate import (
    AnchorRangeGateResult,
    AnchorRangeStatus,
    SymmetricAnchorRangeGate,
)
from aegis.v9.cusum_monitor import CusumChannelSpec, CusumStepResult, MultiChannelCusumMonitor
from aegis.v9.risk_statistics import PREREGISTERED_CANDIDATE_FAMILY, V9CandidateParams
from aegis.v9.sensor_calibration import (
    DisjointPerSensorCalibrator,
    PerSensorCalibrationState,
    SensorCalStatus,
)
from aegis.v9.ville_monitor import MultiChannelVilleMonitor, VilleChannelSpec, VilleStepResult


@dataclass(frozen=True)
class AegisV9Telemetry:
    """Complete per-step audit snapshot of AegisV9Controller internal decision state."""

    step: int
    mode: str
    decision: str
    probing_step: int
    active_sensors: tuple[str, ...]
    sensor_a_state: PerSensorCalibrationState
    sensor_b_state: PerSensorCalibrationState
    raw_inter_sensor_disagreement: float | None
    calibrated_inter_sensor_disagreement: float | None
    residuals: dict[str, float | None]
    ville_wealth: float
    ville_anytime_p: float
    ville_alarm: bool
    cusum_max: float
    cusum_alarm: bool
    cusum_channels: dict[str, float]
    anchor_gate_status: AnchorRangeStatus
    anchor_gate_discrepancy: float
    total_anchor_queries: int
    terminal_reason: str


class AegisV9Controller:
    """
    NEXVIA AEGIS V9.0 closed-loop runtime-assurance policy pi_{lambda^{(j)}}.

    Preserves exact 4-input signature parity with V4–V8 benchmark controllers:
        update(reading_a, reading_b, range_reading, anchor_reading=None, step=0)
            -> (force_action, decision_type, calibrated_vector, query_anchor_next)
    """

    def __init__(
        self,
        params: V9CandidateParams | None = None,
        *,
        use_anchor: bool = True,
    ) -> None:
        self.params: V9CandidateParams = params or PREREGISTERED_CANDIDATE_FAMILY[2]
        self.use_anchor: bool = bool(use_anchor)

        self.velocity_controller = KinematicVelocityController(
            config=VelocityProfileConfig(
                arrival_tolerance=self.params.arrival_tolerance_m,
            )
        )
        self.calibrator = DisjointPerSensorCalibrator(
            fit_start=self.params.fit_start,
            fit_end=self.params.fit_end,
            gap_start=self.params.gap_start,
            gap_end=self.params.gap_end,
            val_start=self.params.val_start,
            val_end=self.params.val_end,
            n_fit_min=self.params.n_fit_min,
            n_val_min=self.params.n_val_min,
            lambda_fim_min=self.params.lambda_fim_min,
        )
        self.anchor_gate = SymmetricAnchorRangeGate(
            tau_ar=self.params.tau_ar,
            min_chord_m=self.params.chord_min_m,
            min_epoch_separation_steps=self.params.chord_min_steps,
        )

        self._nominal_ville: MultiChannelVilleMonitor | None = None
        self._nominal_cusum: MultiChannelCusumMonitor | None = None
        self._post_cal_ville: MultiChannelVilleMonitor | None = None
        self._post_cal_cusum: MultiChannelCusumMonitor | None = None

        self.mode: str = "NOMINAL"
        self.probing_step_count: int = 0
        self.total_anchor_queries: int = 0
        self.terminal_reason: str = "ACTIVE"

        self._nominal_sigmas: tuple[float, float, float] = (0.05, 0.05, 0.05)
        self._consecutive_inst_breaches: int = 0
        self._consecutive_blind_steps: int = 0
        self._consecutive_invalid_range_at_arrival: int = 0
        self._consecutive_arrival_mismatch: int = 0
        self._nominal_approach_steps: int = 0

        self._prev_a_vec: np.ndarray | None = None
        self._prev_a_step: int = -10
        self._prev_b_vec: np.ndarray | None = None
        self._prev_b_step: int = -10
        self._est_velocity: np.ndarray = np.zeros(2, dtype=np.float64)
        self._prev_action: np.ndarray = np.zeros(2, dtype=np.float64)
        self._last_nav_vector: np.ndarray = np.zeros(2, dtype=np.float64)

        self._last_gate_result: AnchorRangeGateResult | None = None
        self._last_telemetry: AegisV9Telemetry | None = None

    @property
    def last_telemetry(self) -> AegisV9Telemetry | None:
        return self._last_telemetry

    def reset(self) -> None:
        """Erases all intra-episode state, preserving strict inter-episode independence."""
        self.calibrator.reset()
        self.anchor_gate.reset()
        self._nominal_ville = None
        self._nominal_cusum = None
        self._post_cal_ville = None
        self._post_cal_cusum = None

        self.mode = "NOMINAL"
        self.probing_step_count = 0
        self.total_anchor_queries = 0
        self.terminal_reason = "ACTIVE"

        self._nominal_sigmas = (0.05, 0.05, 0.05)
        self._consecutive_inst_breaches = 0
        self._consecutive_blind_steps = 0
        self._consecutive_invalid_range_at_arrival = 0
        self._consecutive_arrival_mismatch = 0
        self._nominal_approach_steps = 0

        self._prev_a_vec = None
        self._prev_a_step = -10
        self._prev_b_vec = None
        self._prev_b_step = -10
        self._est_velocity = np.zeros(2, dtype=np.float64)
        self._prev_action = np.zeros(2, dtype=np.float64)
        self._last_nav_vector = np.zeros(2, dtype=np.float64)

        self._last_gate_result = None
        self._last_telemetry = None

    def _ensure_nominal_monitors(self, sig_a: float, sig_b: float, sig_r: float) -> None:
        if self._nominal_ville is not None and self._nominal_cusum is not None:
            return
        self._nominal_sigmas = (sig_a, sig_b, sig_r)
        v_specs = [
            VilleChannelSpec.inter_sensor_ab(sig_a, sig_b, name="ab"),
            VilleChannelSpec.vector_range("vr_a", sig_a, sig_r),
            VilleChannelSpec.vector_range("vr_b", sig_b, sig_r),
        ]
        c_specs = [
            CusumChannelSpec.inter_sensor_ab(sig_a, sig_b, name="ab", kappa_drift=1.80),
            CusumChannelSpec.vector_range("vr_a", sig_a, sig_r, kappa_drift=1.60),
            CusumChannelSpec.vector_range("vr_b", sig_b, sig_r, kappa_drift=1.60),
        ]
        self._nominal_ville = MultiChannelVilleMonitor(v_specs, alpha=self.params.alpha_mon)
        self._nominal_cusum = MultiChannelCusumMonitor(c_specs, threshold_h=self.params.h_cusum)

    def _rebuild_post_calibration_monitors(self, range_corroborated_biased: bool) -> None:
        """
        Initializes operational post-calibration sequential monitors over CALIBRATED_VALID
        sensors. Note: because frozen bias estimates b_hat_k carry finite estimation error,
        post-calibration Channel A is an operational consistency monitor, NOT an exact
        nominal zero-bias Ville test.
        """
        sig_a, sig_b, sig_r = self._nominal_sigmas
        # Account for finite calibration estimation noise (~0.04 m anchor / fit floor)
        eff_sig_a = math.sqrt(sig_a**2 + 0.04**2)
        eff_sig_b = math.sqrt(sig_b**2 + 0.04**2)

        a_ok = self.calibrator.state_a.status == SensorCalStatus.CALIBRATED_VALID
        b_ok = self.calibrator.state_b.status == SensorCalStatus.CALIBRATED_VALID

        v_specs: list[VilleChannelSpec] = []
        c_specs: list[CusumChannelSpec] = []

        if a_ok and b_ok:
            v_specs.append(VilleChannelSpec.inter_sensor_ab(eff_sig_a, eff_sig_b, name="ab"))
            c_specs.append(
                CusumChannelSpec.inter_sensor_ab(eff_sig_a, eff_sig_b, name="ab", kappa_drift=1.85)
            )
        if a_ok and not range_corroborated_biased:
            v_specs.append(VilleChannelSpec.vector_range("vr_a", eff_sig_a, sig_r))
            c_specs.append(
                CusumChannelSpec.vector_range("vr_a", eff_sig_a, sig_r, kappa_drift=1.65)
            )
        if b_ok and not range_corroborated_biased:
            v_specs.append(VilleChannelSpec.vector_range("vr_b", eff_sig_b, sig_r))
            c_specs.append(
                CusumChannelSpec.vector_range("vr_b", eff_sig_b, sig_r, kappa_drift=1.65)
            )

        if v_specs:
            self._post_cal_ville = MultiChannelVilleMonitor(v_specs, alpha=self.params.alpha_mon)
            self._post_cal_cusum = MultiChannelCusumMonitor(
                c_specs, threshold_h=self.params.h_cusum
            )
        else:
            self._post_cal_ville = None
            self._post_cal_cusum = None

    def _update_velocity_estimate(
        self,
        a_vec: np.ndarray | None,
        b_vec: np.ndarray | None,
        step: int,
    ) -> None:
        """
        Estimates robot velocity using ONLY same-sensor consecutive differences (canceling
        static per-sensor biases identically without single-sensor dropout bias jumps) plus
        MuJoCo rolling-sphere acceleration (5/7)*u_{t-1} on dropped steps (`Diagnostic D5`).
        """
        vel_samples: list[np.ndarray] = []
        if a_vec is not None:
            if self._prev_a_vec is not None and (step - self._prev_a_step) == 1:
                vel_samples.append(-(a_vec - self._prev_a_vec) / 0.02)
            self._prev_a_vec = a_vec.copy()
            self._prev_a_step = step

        if b_vec is not None:
            if self._prev_b_vec is not None and (step - self._prev_b_step) == 1:
                vel_samples.append(-(b_vec - self._prev_b_vec) / 0.02)
            self._prev_b_vec = b_vec.copy()
            self._prev_b_step = step

        if vel_samples:
            obs_vel = np.mean(np.asarray(vel_samples, dtype=np.float64), axis=0)
            obs_vel = np.clip(obs_vel, -1.5, 1.5)
            self._est_velocity = 0.65 * self._est_velocity + 0.35 * obs_vel
        else:
            # Rolling solid sphere dynamics a_roll = (5/7) * u_prev (m=1 kg)
            self._est_velocity = np.clip(
                self._est_velocity + 0.02 * (5.0 / 7.0) * self._prev_action,
                -1.5,
                1.5,
            )

    def _plan_v9_probing_action(self, target_vec: np.ndarray, probing_step: int) -> np.ndarray:
        """
        Plans deterministic 36-step probing trajectory spanning I_fit={1..22}, I_gap={23,24},
        and I_val={25..36}, delegating terminal active counter-thrust braking (steps 31..36)
        to `KinematicVelocityController.plan_probing_action`.
        """
        total = self.params.probing_steps
        if probing_step >= total - 5:
            return self.velocity_controller.plan_probing_action(
                target_relative_vector=target_vec,
                current_velocity=self._est_velocity,
                step_in_probing=probing_step,
                probing_steps=total,
            )

        norm_r = float(np.linalg.norm(target_vec))
        if norm_r > 1e-6:
            r_unit = target_vec / norm_r
            ortho = np.array([-r_unit[1], r_unit[0]], dtype=np.float64)
        else:
            r_unit = np.array([1.0, 0.0], dtype=np.float64)
            ortho = np.array([0.0, 1.0], dtype=np.float64)

        if probing_step <= 14:
            cmd = 0.85 * ortho - 0.15 * self._est_velocity
        elif probing_step <= self.params.fit_end:
            cmd = -0.65 * ortho + 0.45 * r_unit - 0.15 * self._est_velocity
        elif probing_step <= self.params.gap_end:
            cmd = -0.80 * ortho - 0.30 * self._est_velocity
        else:
            cmd = -0.75 * ortho - 0.20 * self._est_velocity

        return np.clip(cmd, -1.0, 1.0)

    def _abstain(
        self,
        *,
        step: int,
        reason: str,
        nav_vec: np.ndarray,
        raw_dis: float | None = None,
        cal_dis: float | None = None,
        residuals: dict[str, float | None] | None = None,
        ville_res: VilleStepResult | None = None,
        cusum_res: CusumStepResult | None = None,
        active_sensors: tuple[str, ...] = (),
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        self.mode = "ABSTAIN"
        self.terminal_reason = reason
        zero_act = np.zeros(2, dtype=np.float64)
        self._prev_action = zero_act
        self._record_telemetry(
            step=step,
            decision="ABSTAIN",
            active_sensors=active_sensors,
            raw_dis=raw_dis,
            cal_dis=cal_dis,
            residuals=residuals or {},
            ville_res=ville_res,
            cusum_res=cusum_res,
        )
        return zero_act, "ABSTAIN", nav_vec, False

    def _record_telemetry(
        self,
        *,
        step: int,
        decision: str,
        active_sensors: tuple[str, ...],
        raw_dis: float | None,
        cal_dis: float | None,
        residuals: dict[str, float | None],
        ville_res: VilleStepResult | None,
        cusum_res: CusumStepResult | None,
    ) -> None:
        gate_st = (
            self._last_gate_result.status
            if self._last_gate_result is not None
            else self.anchor_gate.latest_status
        )
        gate_disc = (
            self._last_gate_result.normalized_discrepancy
            if self._last_gate_result is not None
            else 0.0
        )
        self._last_telemetry = AegisV9Telemetry(
            step=int(step),
            mode=self.mode,
            decision=decision,
            probing_step=self.probing_step_count,
            active_sensors=active_sensors,
            sensor_a_state=self.calibrator.state_a,
            sensor_b_state=self.calibrator.state_b,
            raw_inter_sensor_disagreement=raw_dis,
            calibrated_inter_sensor_disagreement=cal_dis,
            residuals=dict(residuals),
            ville_wealth=ville_res.wealth if ville_res is not None else 1.0,
            ville_anytime_p=ville_res.anytime_p_value if ville_res is not None else 1.0,
            ville_alarm=ville_res.is_alarm if ville_res is not None else False,
            cusum_max=cusum_res.max_cusum if cusum_res is not None else 0.0,
            cusum_alarm=cusum_res.is_alarm if cusum_res is not None else False,
            cusum_channels=dict(cusum_res.channel_statistics) if cusum_res is not None else {},
            anchor_gate_status=gate_st,
            anchor_gate_discrepancy=gate_disc,
            total_anchor_queries=self.total_anchor_queries,
            terminal_reason=self.terminal_reason,
        )

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        """
        Closed-loop V9 runtime-assurance decision step.

        Strictly reads ONLY observable fields (`.valid`, `.estimate`, `.distance`, `.sigma`)
        from the four sensor inputs. Never accesses ground-truth `.bias`, `.drift`, or `.anomaly`.
        """
        # 0. Latched terminal abstention
        if self.mode == "ABSTAIN":
            return self._abstain(
                step=step,
                reason=self.terminal_reason,
                nav_vec=self._last_nav_vector,
            )

        # 1. Fail-closed input hygiene check on all valid sensor channels
        a_valid = bool(reading_a.valid)
        b_valid = bool(reading_b.valid)
        r_valid = bool(range_reading.valid)
        anc_valid = bool(anchor_reading is not None and anchor_reading.valid)

        a_vec: np.ndarray | None = None
        b_vec: np.ndarray | None = None
        sig_a = self._nominal_sigmas[0]
        sig_b = self._nominal_sigmas[1]
        sig_r = self._nominal_sigmas[2]
        r_dist: float | None = None

        if a_valid:
            arr_a = np.asarray(reading_a.estimate, dtype=np.float64)
            sig_a = float(reading_a.sigma)
            if (
                arr_a.shape != (2,)
                or not np.all(np.isfinite(arr_a))
                or not math.isfinite(sig_a)
                or sig_a <= 0.0
            ):
                return self._abstain(
                    step=step,
                    reason="MALFORMED_SENSOR_A_INPUT",
                    nav_vec=self._last_nav_vector,
                )
            a_vec = arr_a.copy()

        if b_valid:
            arr_b = np.asarray(reading_b.estimate, dtype=np.float64)
            sig_b = float(reading_b.sigma)
            if (
                arr_b.shape != (2,)
                or not np.all(np.isfinite(arr_b))
                or not math.isfinite(sig_b)
                or sig_b <= 0.0
            ):
                return self._abstain(
                    step=step,
                    reason="MALFORMED_SENSOR_B_INPUT",
                    nav_vec=self._last_nav_vector,
                )
            b_vec = arr_b.copy()

        if r_valid:
            r_val = float(range_reading.distance)
            sig_r = float(range_reading.sigma)
            if (
                not math.isfinite(r_val)
                or r_val < 0.0
                or not math.isfinite(sig_r)
                or sig_r <= 0.0
            ):
                return self._abstain(
                    step=step,
                    reason="MALFORMED_RANGE_INPUT",
                    nav_vec=self._last_nav_vector,
                )
            r_dist = r_val

        if anc_valid:
            assert anchor_reading is not None
            arr_anc = np.asarray(anchor_reading.estimate, dtype=np.float64)
            sig_anc = float(anchor_reading.sigma)
            if (
                arr_anc.shape != (2,)
                or not np.all(np.isfinite(arr_anc))
                or not math.isfinite(sig_anc)
                or sig_anc <= 0.0
            ):
                return self._abstain(
                    step=step,
                    reason="MALFORMED_ANCHOR_INPUT",
                    nav_vec=self._last_nav_vector,
                )

        self._ensure_nominal_monitors(sig_a, sig_b, sig_r)
        self._update_velocity_estimate(a_vec, b_vec, step)

        # Evaluate anchor/range gate whenever a valid anchor observation arrives
        verified_anchor_for_fit: np.ndarray | None = None
        verified_anchor_sigma: float = 0.04
        if anc_valid and anchor_reading is not None:
            cal_biases: dict[str, np.ndarray] = {}
            cal_flags: dict[str, bool] = {}
            if self.calibrator.is_fit_frozen:
                cal_biases["vec_a"] = self.calibrator.state_a.bias
                cal_biases["vec_b"] = self.calibrator.state_b.bias
                cal_flags["vec_a"] = (
                    self.calibrator.state_a.status == SensorCalStatus.CALIBRATED_VALID
                )
                cal_flags["vec_b"] = (
                    self.calibrator.state_b.status == SensorCalStatus.CALIBRATED_VALID
                )

            cusum_stats = (
                self._nominal_cusum.statistics if self._nominal_cusum is not None else {}
            )
            drift_suspected = {
                "vec_a": cusum_stats.get("ab", 0.0) >= 0.6 * self.params.h_cusum
                or cusum_stats.get("vr_a", 0.0) >= 0.6 * self.params.h_cusum,
                "vec_b": cusum_stats.get("ab", 0.0) >= 0.6 * self.params.h_cusum
                or cusum_stats.get("vr_b", 0.0) >= 0.6 * self.params.h_cusum,
            }

            gate_res = self.anchor_gate.evaluate(
                anchor_reading,
                range_reading,
                reading_a,
                reading_b,
                step=step,
                drift_suspected=drift_suspected,
                calibrated_biases=cal_biases,
                calibrated_valid_flags=cal_flags,
            )
            self._last_gate_result = gate_res
            if gate_res.status == AnchorRangeStatus.INVALID_INPUT:
                return self._abstain(
                    step=step,
                    reason=gate_res.reason,
                    nav_vec=self._last_nav_vector,
                )
            if gate_res.status in (
                AnchorRangeStatus.CONSISTENT,
                AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED,
            ):
                verified_anchor_for_fit = np.asarray(
                    anchor_reading.estimate, dtype=np.float64
                ).copy()
                verified_anchor_sigma = float(anchor_reading.sigma)

        # Complete vector dropout guard
        if a_vec is None and b_vec is None:
            self._consecutive_blind_steps += 1
            if self._consecutive_blind_steps > 6:
                return self._abstain(
                    step=step,
                    reason="PERSISTENT_TOTAL_VECTOR_DROPOUT",
                    nav_vec=self._last_nav_vector,
                )
            zero_act = np.zeros(2, dtype=np.float64)
            self._prev_action = zero_act
            self._record_telemetry(
                step=step,
                decision="VERIFY",
                active_sensors=(),
                raw_dis=None,
                cal_dis=None,
                residuals={},
                ville_res=None,
                cusum_res=None,
            )
            return zero_act, "VERIFY", self._last_nav_vector, False
        self._consecutive_blind_steps = 0

        # =====================================================================
        # MODE 1: NOMINAL (Pre-Fusion Hybrid Monitoring + Terminal Range Gate)
        # =====================================================================
        if self.mode == "NOMINAL":
            assert self._nominal_ville is not None and self._nominal_cusum is not None

            e_ab = float(np.linalg.norm(a_vec - b_vec)) if (a_vec is not None and b_vec is not None) else 0.0
            v_ab = a_vec is not None and b_vec is not None

            e_vr_a = (
                abs(float(np.linalg.norm(a_vec)) - r_dist)
                if (a_vec is not None and r_dist is not None)
                else 0.0
            )
            v_vr_a = a_vec is not None and r_dist is not None

            e_vr_b = (
                abs(float(np.linalg.norm(b_vec)) - r_dist)
                if (b_vec is not None and r_dist is not None)
                else 0.0
            )
            v_vr_b = b_vec is not None and r_dist is not None

            obs_map = {
                "ab": (e_ab, v_ab),
                "vr_a": (e_vr_a, v_vr_a),
                "vr_b": (e_vr_b, v_vr_b),
            }
            ville_res = self._nominal_ville.update(obs_map)
            cusum_res = self._nominal_cusum.update(obs_map)

            if ville_res.invalid_input_detected or cusum_res.invalid_input_detected:
                return self._abstain(
                    step=step,
                    reason="NOMINAL_MONITOR_INVALID_INPUT",
                    nav_vec=self._last_nav_vector,
                    ville_res=ville_res,
                    cusum_res=cusum_res,
                )

            sig_diff = math.sqrt(sig_a**2 + sig_b**2)
            inst_ab_breach = v_ab and (e_ab / max(sig_diff, 1e-6) > self.params.tau_diff)
            inst_vr_a_breach = v_vr_a and (
                e_vr_a / math.sqrt(sig_a**2 + sig_r**2) > self.params.tau_ar
            )
            inst_vr_b_breach = v_vr_b and (
                e_vr_b / math.sqrt(sig_b**2 + sig_r**2) > self.params.tau_ar
            )
            any_inst_breach = inst_ab_breach or inst_vr_a_breach or inst_vr_b_breach
            if any_inst_breach:
                self._consecutive_inst_breaches += 1
            else:
                self._consecutive_inst_breaches = 0

            # Pre-fusion navigation vector ONLY after disagreement check!
            if a_vec is not None and b_vec is not None:
                w_a = 1.0 / (sig_a**2)
                w_b = 1.0 / (sig_b**2)
                nav_vec = (w_a * a_vec + w_b * b_vec) / (w_a + w_b)
                active_names: tuple[str, ...] = ("vec_a", "vec_b")
            elif a_vec is not None:
                nav_vec = a_vec.copy()
                active_names = ("vec_a",)
            else:
                assert b_vec is not None
                nav_vec = b_vec.copy()
                active_names = ("vec_b",)
            self._last_nav_vector = nav_vec

            residuals_dict: dict[str, float | None] = {
                "ab": e_ab if v_ab else None,
                "vr_a": e_vr_a if v_vr_a else None,
                "vr_b": e_vr_b if v_vr_b else None,
            }

            trigger_probing = (
                ville_res.is_alarm
                or cusum_res.is_alarm
                or self._consecutive_inst_breaches >= 2
            )

            # FIX AUDIT BUG #1: Nominal-to-probing transition returns "PROBE" IMMEDIATELY
            # and NEVER falls through to the NOMINAL arrival "STOP" check!
            if trigger_probing:
                self.mode = "ACTIVE_PROBING"
                self.probing_step_count = 0
                self.calibrator.reset()
                self._consecutive_invalid_range_at_arrival = 0
                brake_act = np.clip(-0.80 * self._est_velocity, -1.0, 1.0)
                self._prev_action = brake_act
                self._record_telemetry(
                    step=step,
                    decision="PROBE",
                    active_sensors=active_names,
                    raw_dis=e_ab if v_ab else None,
                    cal_dis=None,
                    residuals=residuals_dict,
                    ville_res=ville_res,
                    cusum_res=cusum_res,
                )
                return brake_act, "PROBE", nav_vec, False

            # Check terminal arrival with mandatory valid-range verification (FIX AUDIT BUG #2)
            nav_dist = float(np.linalg.norm(nav_vec))
            if nav_dist <= self.params.arrival_tolerance_m:
                # Never commit "STOP" on a single-step anomaly breach or invalid/dropped range!
                if any_inst_breach:
                    zero_act = np.zeros(2, dtype=np.float64)
                    self._prev_action = zero_act
                    self._record_telemetry(
                        step=step,
                        decision="VERIFY",
                        active_sensors=active_names,
                        raw_dis=e_ab if v_ab else None,
                        cal_dis=None,
                        residuals=residuals_dict,
                        ville_res=ville_res,
                        cusum_res=cusum_res,
                    )
                    return zero_act, "VERIFY", nav_vec, False

                if r_dist is None or r_dist <= 1e-4:
                    self._consecutive_invalid_range_at_arrival += 1
                    if self._consecutive_invalid_range_at_arrival > 5:
                        return self._abstain(
                            step=step,
                            reason="INVALID_OR_DROPPED_RANGE_AT_ARRIVAL",
                            nav_vec=nav_vec,
                            raw_dis=e_ab if v_ab else None,
                            residuals=residuals_dict,
                            ville_res=ville_res,
                            cusum_res=cusum_res,
                            active_sensors=active_names,
                        )
                    zero_act = np.zeros(2, dtype=np.float64)
                    self._prev_action = zero_act
                    self._record_telemetry(
                        step=step,
                        decision="VERIFY",
                        active_sensors=active_names,
                        raw_dis=e_ab if v_ab else None,
                        cal_dis=None,
                        residuals=residuals_dict,
                        ville_res=ville_res,
                        cusum_res=cusum_res,
                    )
                    return zero_act, "VERIFY", nav_vec, False

                self._consecutive_invalid_range_at_arrival = 0
                elevated_pre_arrival_suspicion = (
                    cusum_res.max_cusum >= 0.40 * self.params.h_cusum
                    or ville_res.wealth >= min(6.0, 0.25 / self.params.alpha_mon)
                )
                range_disagreement = abs(nav_dist - r_dist) > self.params.tau_diff
                if r_dist > self.params.tau_stop or elevated_pre_arrival_suspicion or range_disagreement:
                    # Uncalibrated range discrepancy or accumulated sequential suspicion at
                    # supposed arrival -> enter ACTIVE_PROBING before committing STOP!
                    self.mode = "ACTIVE_PROBING"
                    self.probing_step_count = 0
                    self.calibrator.reset()
                    zero_act = np.zeros(2, dtype=np.float64)
                    self._prev_action = zero_act
                    self._record_telemetry(
                        step=step,
                        decision="PROBE",
                        active_sensors=active_names,
                        raw_dis=e_ab if v_ab else None,
                        cal_dis=None,
                        residuals=residuals_dict,
                        ville_res=ville_res,
                        cusum_res=cusum_res,
                    )
                    return zero_act, "PROBE", nav_vec, False

                # V9-M2R1: Temporal approach verification vs. Independent initial corroboration
                has_temporal_approach = (self._nominal_approach_steps >= 3)
                if not has_temporal_approach:
                    # Temporal evidence is unavailable or insufficient (e.g. step == 0).
                    # A single spatial snapshot cannot distinguish common-mode vector bias
                    # coupled with range bias from true goal arrival.
                    # Independent corroboration via anchor is required.
                    corroborated_initial_goal = False
                    if anc_valid and anchor_reading is not None:
                        arr_anc = np.asarray(anchor_reading.estimate, dtype=np.float64)
                        anc_dist = float(np.linalg.norm(arr_anc))
                        gate_st = (
                            self._last_gate_result.status
                            if self._last_gate_result is not None
                            else None
                        )
                        gate_valid = gate_st in (
                            AnchorRangeStatus.CONSISTENT,
                            AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED,
                        )
                        anc_arr_ok = (anc_dist <= self.params.arrival_tolerance_m)
                        anc_nav_agree = (
                            float(np.linalg.norm(arr_anc - nav_vec))
                            <= self.params.tau_diff * sig_diff
                        )
                        anc_range_agree = (
                            abs(anc_dist - r_dist)
                            <= self.params.tau_ar * math.sqrt(sig_anc**2 + sig_r**2)
                        )
                        if gate_valid and anc_arr_ok and anc_nav_agree and anc_range_agree:
                            corroborated_initial_goal = True

                    if corroborated_initial_goal:
                        self.terminal_reason = "CORROBORATED_INITIAL_GOAL_ARRIVAL"
                        zero_act = np.zeros(2, dtype=np.float64)
                        self._prev_action = zero_act
                        self._record_telemetry(
                            step=step,
                            decision="STOP",
                            active_sensors=active_names,
                            raw_dis=e_ab if v_ab else None,
                            cal_dis=None,
                            residuals=residuals_dict,
                            ville_res=ville_res,
                            cusum_res=cusum_res,
                        )
                        return zero_act, "STOP", nav_vec, False

                    # If anchor has not yet been queried and queries are within budget, request anchor
                    can_query_anchor = (
                        self.use_anchor
                        and self.total_anchor_queries < self.params.max_anchor_queries
                        and not anc_valid
                    )
                    if can_query_anchor:
                        self.total_anchor_queries += 1
                        zero_act = np.zeros(2, dtype=np.float64)
                        self._prev_action = zero_act
                        self._record_telemetry(
                            step=step,
                            decision="VERIFY",
                            active_sensors=active_names,
                            raw_dis=e_ab if v_ab else None,
                            cal_dis=None,
                            residuals=residuals_dict,
                            ville_res=ville_res,
                            cusum_res=cusum_res,
                        )
                        return zero_act, "VERIFY", nav_vec, True

                    # Uncorroborated initial arrival cannot be verified: FAIL CLOSED to ACTIVE_PROBING
                    self.mode = "ACTIVE_PROBING"
                    self.probing_step_count = 0
                    self.calibrator.reset()
                    self.terminal_reason = "UNCORROBORATED_INITIAL_ARRIVAL_PROBE"
                    zero_act = np.zeros(2, dtype=np.float64)
                    self._prev_action = zero_act
                    self._record_telemetry(
                        step=step,
                        decision="PROBE",
                        active_sensors=active_names,
                        raw_dis=e_ab if v_ab else None,
                        cal_dis=None,
                        residuals=residuals_dict,
                        ville_res=ville_res,
                        cusum_res=cusum_res,
                    )
                    return zero_act, "PROBE", nav_vec, False

                # All nominal multi-modal checks passed -> commit terminal "STOP"
                self.terminal_reason = "NOMINAL_VERIFIED_ARRIVAL"
                zero_act = np.zeros(2, dtype=np.float64)
                self._prev_action = zero_act
                self._record_telemetry(
                    step=step,
                    decision="STOP",
                    active_sensors=active_names,
                    raw_dis=e_ab if v_ab else None,
                    cal_dis=None,
                    residuals=residuals_dict,
                    ville_res=ville_res,
                    cusum_res=cusum_res,
                )
                return zero_act, "STOP", nav_vec, False

            # Smooth pursuit control
            self._nominal_approach_steps += 1
            action, _ = self.velocity_controller.plan_approach_action(nav_vec, self._est_velocity)
            self._prev_action = action
            self._record_telemetry(
                step=step,
                decision="ACT",
                active_sensors=active_names,
                raw_dis=e_ab if v_ab else None,
                cal_dis=None,
                residuals=residuals_dict,
                ville_res=ville_res,
                cusum_res=cusum_res,
            )
            return action, "ACT", nav_vec, False

        # =====================================================================
        # MODE 2: ACTIVE_PROBING (Disjoint Fit / Gap / Val + Symmetric Anchor Gate)
        # =====================================================================
        if self.mode == "ACTIVE_PROBING":
            self.probing_step_count += 1
            p_step = self.probing_step_count

            is_range_biased = (
                self.anchor_gate.latest_status
                == AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED
            )

            ok = self.calibrator.record_probing_step(
                p_step,
                reading_a,
                reading_b,
                range_reading,
                verified_anchor_estimate=verified_anchor_for_fit,
                verified_anchor_sigma=verified_anchor_sigma,
                range_corroborated_biased=is_range_biased,
            )
            if not ok or self.calibrator.invalid_input_detected:
                return self._abstain(
                    step=step,
                    reason="INVALID_INPUT_DURING_PROBING",
                    nav_vec=self._last_nav_vector,
                )

            # Reference vector for orthogonal excitation planning
            ref_vec = a_vec if a_vec is not None else b_vec
            assert ref_vec is not None
            self._last_nav_vector = ref_vec
            probe_action = self._plan_v9_probing_action(ref_vec, p_step)

            # Schedule anchor queries strictly inside I_fit = {1..22} (steps 2 & 12 -> arrive 3 & 13,
            # with retry on step 5 or 15 if range dropped on the arrival step).
            query_next = False
            if (
                self.use_anchor
                and self.total_anchor_queries < self.params.max_anchor_queries
                and p_step < self.params.fit_end
            ):
                if p_step in (2, 12):
                    query_next = True
                elif (
                    p_step in (5, 15)
                    and self.anchor_gate.num_epochs < (1 if p_step == 5 else 2)
                ):
                    query_next = True

            if query_next:
                self.total_anchor_queries += 1

            # Finalize calibration at the end of I_val (step 36)
            if p_step >= self.params.probing_steps:
                if self.anchor_gate.has_unresolved_disagreement():
                    return self._abstain(
                        step=step,
                        reason="ANCHOR_RANGE_DISAGREEMENT_UNCORROBORATED",
                        nav_vec=ref_vec,
                    )

                is_range_biased = (
                    self.anchor_gate.latest_status
                    == AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED
                )
                st_a, st_b = self.calibrator.finalize_validation(
                    tau_val=self.params.tau_val,
                    tau_diff=self.params.tau_diff,
                    range_corroborated_biased=is_range_biased,
                )

                if not self.calibrator.has_any_valid_calibrated_sensor():
                    return self._abstain(
                        step=step,
                        reason=f"CALIBRATION_FAILED (a={st_a.status.value}, b={st_b.status.value})",
                        nav_vec=ref_vec,
                    )

                self.mode = "CALIBRATED"
                self._consecutive_invalid_range_at_arrival = 0
                self._consecutive_arrival_mismatch = 0
                self._rebuild_post_calibration_monitors(is_range_biased)

            self._prev_action = probe_action
            self._record_telemetry(
                step=step,
                decision="PROBE",
                active_sensors=(),
                raw_dis=float(np.linalg.norm(a_vec - b_vec)) if (a_vec is not None and b_vec is not None) else None,
                cal_dis=None,
                residuals={},
                ville_res=None,
                cusum_res=None,
            )
            return probe_action, "PROBE", ref_vec, query_next

        # =====================================================================
        # MODE 3: CALIBRATED (Frozen Bias Approach + Post-Calibration Guard)
        # =====================================================================
        if self.mode == "CALIBRATED":
            if self.anchor_gate.has_unresolved_disagreement():
                return self._abstain(
                    step=step,
                    reason="POST_CAL_ANCHOR_RANGE_DISAGREEMENT",
                    nav_vec=self._last_nav_vector,
                )

            fusion = self.calibrator.fuse_calibrated(
                reading_a,
                reading_b,
                range_reading=range_reading,
                tau_diff=self.params.tau_diff,
            )
            if fusion.invalid_input_detected:
                return self._abstain(
                    step=step,
                    reason="INVALID_INPUT_IN_CALIBRATED_FUSION",
                    nav_vec=self._last_nav_vector,
                )

            if not fusion.valid:
                # Transient dropout on active calibrated sensor(s)
                self._consecutive_blind_steps += 1
                if self._consecutive_blind_steps > 6:
                    return self._abstain(
                        step=step,
                        reason="CALIBRATED_SENSOR_DROPOUT_EXCEEDED",
                        nav_vec=self._last_nav_vector,
                    )
                zero_act = np.zeros(2, dtype=np.float64)
                self._prev_action = zero_act
                self._record_telemetry(
                    step=step,
                    decision="VERIFY",
                    active_sensors=(),
                    raw_dis=fusion.raw_disagreement_norm,
                    cal_dis=fusion.calibrated_disagreement_norm,
                    residuals={},
                    ville_res=None,
                    cusum_res=None,
                )
                return zero_act, "VERIFY", self._last_nav_vector, False

            cal_vec = fusion.fused_vector
            self._last_nav_vector = cal_vec

            is_range_biased = (
                self.anchor_gate.latest_status
                == AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED
            )

            # Evaluate post-calibration monitors without mutating frozen biases
            a_ok = self.calibrator.state_a.status == SensorCalStatus.CALIBRATED_VALID
            b_ok = self.calibrator.state_b.status == SensorCalStatus.CALIBRATED_VALID

            e_vr_a_cal = (
                abs(float(np.linalg.norm(a_vec - self.calibrator.state_a.bias)) - r_dist)
                if (a_ok and a_vec is not None and r_dist is not None and not is_range_biased)
                else 0.0
            )
            v_vr_a_cal = bool(a_ok and a_vec is not None and r_dist is not None and not is_range_biased)

            e_vr_b_cal = (
                abs(float(np.linalg.norm(b_vec - self.calibrator.state_b.bias)) - r_dist)
                if (b_ok and b_vec is not None and r_dist is not None and not is_range_biased)
                else 0.0
            )
            v_vr_b_cal = bool(b_ok and b_vec is not None and r_dist is not None and not is_range_biased)

            e_ab_cal = (
                fusion.calibrated_disagreement_norm
                if (a_ok and b_ok and fusion.calibrated_disagreement_norm is not None)
                else 0.0
            )
            v_ab_cal = bool(a_ok and b_ok and fusion.calibrated_disagreement_norm is not None)

            post_ville_res: VilleStepResult | None = None
            post_cusum_res: CusumStepResult | None = None
            if self._post_cal_ville is not None and self._post_cal_cusum is not None:
                post_obs: dict[str, tuple[float, bool]] = {
                    "ab": (e_ab_cal, v_ab_cal),
                    "vr_a": (e_vr_a_cal, v_vr_a_cal),
                    "vr_b": (e_vr_b_cal, v_vr_b_cal),
                }
                post_ville_res = self._post_cal_ville.update(post_obs)
                post_cusum_res = self._post_cal_cusum.update(post_obs)

                if post_ville_res.is_alarm or post_cusum_res.is_alarm:
                    # If both sensors were active and ONLY ONE sensor diverged from range
                    # (e.g., ongoing drift in SENSOR_DRIFT), isolate that faulty sensor
                    # WITHOUT refitting the healthy sensor's frozen bias!
                    isolated_one = False
                    if a_ok and b_ok and r_dist is not None and not is_range_biased:
                        tol_a = 2.4 * math.sqrt(sig_a**2 + sig_r**2)
                        tol_b = 2.4 * math.sqrt(sig_b**2 + sig_r**2)
                        w_vra = post_ville_res.subchannel_wealths.get("vr_a", 1.0)
                        w_vrb = post_ville_res.subchannel_wealths.get("vr_b", 1.0)
                        c_vra = post_cusum_res.channel_statistics.get("vr_a", 0.0)
                        c_vrb = post_cusum_res.channel_statistics.get("vr_b", 0.0)

                        b_clean = (
                            v_vr_b_cal
                            and e_vr_b_cal <= tol_b
                            and w_vrb < 0.25 * (1.0 / self.params.alpha_mon)
                            and c_vrb < 0.50 * self.params.h_cusum
                        )
                        a_clean = (
                            v_vr_a_cal
                            and e_vr_a_cal <= tol_a
                            and w_vra < 0.25 * (1.0 / self.params.alpha_mon)
                            and c_vra < 0.50 * self.params.h_cusum
                        )
                        if b_clean and not a_clean:
                            self.calibrator.isolate_faulty_sensor(
                                "vec_a", reason="POST_CAL_DRIFT_ISOLATED_VEC_A"
                            )
                            self._rebuild_post_calibration_monitors(is_range_biased)
                            assert b_vec is not None
                            cal_vec = b_vec - self.calibrator.state_b.bias
                            self._last_nav_vector = cal_vec
                            isolated_one = True
                        elif a_clean and not b_clean:
                            self.calibrator.isolate_faulty_sensor(
                                "vec_b", reason="POST_CAL_DRIFT_ISOLATED_VEC_B"
                            )
                            self._rebuild_post_calibration_monitors(is_range_biased)
                            assert a_vec is not None
                            cal_vec = a_vec - self.calibrator.state_a.bias
                            self._last_nav_vector = cal_vec
                            isolated_one = True

                    if not isolated_one:
                        return self._abstain(
                            step=step,
                            reason="POST_CALIBRATION_MONITOR_ALARM",
                            nav_vec=cal_vec,
                            raw_dis=fusion.raw_disagreement_norm,
                            cal_dis=fusion.calibrated_disagreement_norm,
                            ville_res=post_ville_res,
                            cusum_res=post_cusum_res,
                            active_sensors=fusion.active_sensors,
                        )

            residuals_cal: dict[str, float | None] = {
                "ab_cal": e_ab_cal if v_ab_cal else None,
                "vr_a_cal": e_vr_a_cal if v_vr_a_cal else None,
                "vr_b_cal": e_vr_b_cal if v_vr_b_cal else None,
            }

            # Multi-Modal Terminal Commit Gate
            cal_dist = float(np.linalg.norm(cal_vec))
            if cal_dist <= self.params.arrival_tolerance_m:
                # Never commit "STOP" on a step with active inter-sensor calibrated breach
                if (
                    fusion.normalized_calibrated_disagreement is not None
                    and fusion.normalized_calibrated_disagreement > self.params.tau_diff
                ):
                    zero_act = np.zeros(2, dtype=np.float64)
                    self._prev_action = zero_act
                    self._record_telemetry(
                        step=step,
                        decision="VERIFY",
                        active_sensors=fusion.active_sensors,
                        raw_dis=fusion.raw_disagreement_norm,
                        cal_dis=fusion.calibrated_disagreement_norm,
                        residuals=residuals_cal,
                        ville_res=post_ville_res,
                        cusum_res=post_cusum_res,
                    )
                    return zero_act, "VERIFY", cal_vec, False

                if is_range_biased:
                    # Range was explicitly proven biased via Decision 3: require fresh valid anchor
                    # confirmation <= tau_stop at arrival (or query anchor once if within budget)
                    if anc_valid and anchor_reading is not None:
                        anc_dist = float(np.linalg.norm(anchor_reading.estimate))
                        if anc_dist <= self.params.tau_stop:
                            self.terminal_reason = "CALIBRATED_ANCHOR_VERIFIED_ARRIVAL"
                            zero_act = np.zeros(2, dtype=np.float64)
                            self._prev_action = zero_act
                            self._record_telemetry(
                                step=step,
                                decision="STOP",
                                active_sensors=fusion.active_sensors,
                                raw_dis=fusion.raw_disagreement_norm,
                                cal_dis=fusion.calibrated_disagreement_norm,
                                residuals=residuals_cal,
                                ville_res=post_ville_res,
                                cusum_res=post_cusum_res,
                            )
                            return zero_act, "STOP", cal_vec, False
                        return self._abstain(
                            step=step,
                            reason="TERMINAL_ANCHOR_DISTANCE_EXCEEDED",
                            nav_vec=cal_vec,
                            active_sensors=fusion.active_sensors,
                        )

                    if self.use_anchor and self.total_anchor_queries < self.params.max_anchor_queries:
                        self.total_anchor_queries += 1
                        zero_act = np.zeros(2, dtype=np.float64)
                        self._prev_action = zero_act
                        self._record_telemetry(
                            step=step,
                            decision="VERIFY",
                            active_sensors=fusion.active_sensors,
                            raw_dis=fusion.raw_disagreement_norm,
                            cal_dis=fusion.calibrated_disagreement_norm,
                            residuals=residuals_cal,
                            ville_res=post_ville_res,
                            cusum_res=post_cusum_res,
                        )
                        return zero_act, "VERIFY", cal_vec, True

                    return self._abstain(
                        step=step,
                        reason="TERMINAL_VERIFICATION_INCOMPLETE_BIASED_RANGE",
                        nav_vec=cal_vec,
                        active_sensors=fusion.active_sensors,
                    )

                # Standard healthy-range terminal commit gate: range MUST be valid and <= tau_stop!
                if r_dist is None or r_dist <= 1e-4:
                    self._consecutive_invalid_range_at_arrival += 1
                    if self._consecutive_invalid_range_at_arrival > 5:
                        return self._abstain(
                            step=step,
                            reason="INVALID_OR_DROPPED_RANGE_AT_CALIBRATED_ARRIVAL",
                            nav_vec=cal_vec,
                            raw_dis=fusion.raw_disagreement_norm,
                            cal_dis=fusion.calibrated_disagreement_norm,
                            residuals=residuals_cal,
                            ville_res=post_ville_res,
                            cusum_res=post_cusum_res,
                            active_sensors=fusion.active_sensors,
                        )
                    zero_act = np.zeros(2, dtype=np.float64)
                    self._prev_action = zero_act
                    self._record_telemetry(
                        step=step,
                        decision="VERIFY",
                        active_sensors=fusion.active_sensors,
                        raw_dis=fusion.raw_disagreement_norm,
                        cal_dis=fusion.calibrated_disagreement_norm,
                        residuals=residuals_cal,
                        ville_res=post_ville_res,
                        cusum_res=post_cusum_res,
                    )
                    return zero_act, "VERIFY", cal_vec, False

                self._consecutive_invalid_range_at_arrival = 0
                if r_dist > self.params.tau_stop:
                    self._consecutive_arrival_mismatch += 1
                    if self._consecutive_arrival_mismatch >= 2:
                        return self._abstain(
                            step=step,
                            reason=f"TERMINAL_RANGE_GATE_REJECTED ({r_dist:.3f}m > {self.params.tau_stop:.2f}m)",
                            nav_vec=cal_vec,
                            raw_dis=fusion.raw_disagreement_norm,
                            cal_dis=fusion.calibrated_disagreement_norm,
                            residuals=residuals_cal,
                            ville_res=post_ville_res,
                            cusum_res=post_cusum_res,
                            active_sensors=fusion.active_sensors,
                        )
                    zero_act = np.zeros(2, dtype=np.float64)
                    self._prev_action = zero_act
                    self._record_telemetry(
                        step=step,
                        decision="VERIFY",
                        active_sensors=fusion.active_sensors,
                        raw_dis=fusion.raw_disagreement_norm,
                        cal_dis=fusion.calibrated_disagreement_norm,
                        residuals=residuals_cal,
                        ville_res=post_ville_res,
                        cusum_res=post_cusum_res,
                    )
                    return zero_act, "VERIFY", cal_vec, False

                self._consecutive_arrival_mismatch = 0
                self.terminal_reason = "CALIBRATED_VERIFIED_ARRIVAL"
                zero_act = np.zeros(2, dtype=np.float64)
                self._prev_action = zero_act
                self._record_telemetry(
                    step=step,
                    decision="STOP",
                    active_sensors=fusion.active_sensors,
                    raw_dis=fusion.raw_disagreement_norm,
                    cal_dis=fusion.calibrated_disagreement_norm,
                    residuals=residuals_cal,
                    ville_res=post_ville_res,
                    cusum_res=post_cusum_res,
                )
                return zero_act, "STOP", cal_vec, False

            action, _ = self.velocity_controller.plan_approach_action(cal_vec, self._est_velocity)
            self._prev_action = action
            self._record_telemetry(
                step=step,
                decision="ACT",
                active_sensors=fusion.active_sensors,
                raw_dis=fusion.raw_disagreement_norm,
                cal_dis=fusion.calibrated_disagreement_norm,
                residuals=residuals_cal,
                ville_res=post_ville_res,
                cusum_res=post_cusum_res,
            )
            return action, "ACT", cal_vec, False

        return self._abstain(
            step=step,
            reason="UNKNOWN_MODE_FAIL_CLOSED",
            nav_vec=self._last_nav_vector,
        )
