"""
3-Sensor Simulation & GitHub-Aligned Fault Injection Suite.

Simulates 3 independent localization sensors observing the same robot inside
the 3D subterranean maze arena:
  - S1_VIO   : Visual-Inertial Odometry (nominal sigma = 0.030 m)
  - S2_LIDAR : LiDAR Scan-Matching Odometry (nominal sigma = 0.035 m)
  - S3_UWB   : UWB Beacon + IMU Odometry (nominal sigma = 0.045 m)

Supported fault modes (mapped directly from NEXVIA AEGIS GitHub experiments):
  1. NONE                 : Nominal Gaussian sensor noise
  2. GRADUAL_DRIFT        : Slow linear drift ramp (e.g., 0.030 m/step)
  3. HEAVY_DRIFT          : Rapid accelerating drift (severe drift scenario)
  4. SUDDEN_BIAS          : Abrupt static bias jump (like V7 PRIMARY_BIAS)
  5. OUTLIER_BURSTS       : Intermittent heavy-tail spikes (like V7 OUTLIER_BURSTS)
  6. RETIMESTAMPED_FREEZE : Frozen physical reading with fresh timestamp/metadata
                            (directly reproduces LIVE01 #1 unresolved gap)
  7. SENSOR_BLACKOUT      : Feed loss / NaN dropout (like V9-M16 Sensor Blackout)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class FaultType(str, Enum):
    NONE = "NONE"
    GRADUAL_DRIFT = "GRADUAL_DRIFT"
    HEAVY_DRIFT = "HEAVY_DRIFT"
    SUDDEN_BIAS = "SUDDEN_BIAS"
    OUTLIER_BURSTS = "OUTLIER_BURSTS"
    RETIMESTAMPED_FREEZE = "RETIMESTAMPED_FREEZE"
    SENSOR_BLACKOUT = "SENSOR_BLACKOUT"


@dataclass(frozen=True)
class SensorSpec:
    """Nominal physical specification of one independent sensor channel."""
    sensor_id: str
    modality: str
    nominal_sigma: float  # Standard deviation per axis (m)


@dataclass(frozen=True)
class FaultInjectionSpec:
    """Fault schedule applied to a specific sensor during an experiment."""
    sensor_id: str
    fault_type: FaultType = FaultType.NONE
    start_step: int = 12
    end_step: Optional[int] = None  # None = persists until end of episode
    drift_rate_per_step: Tuple[float, float, float] = (0.030, -0.020, 0.005)
    drift_accel_per_step2: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bias_vector: Tuple[float, float, float] = (1.10, -0.85, 0.15)
    outlier_prob: float = 0.30
    outlier_magnitude: float = 2.40


@dataclass
class SensorReading:
    """Single timestamped reading emitted by one sensor channel."""
    sensor_id: str
    step: int
    timestamp_s: float
    position: np.ndarray          # (3,) measured [x, y, z] (may contain NaN on blackout)
    nominal_sigma: float
    metadata_fresh: bool = True   # True even during RETIMESTAMPED_FREEZE!
    # Ground-truth audit fields (STRICTLY FOR POST-HOC EVALUATION — never read by verifier!)
    gt_fault_active: bool = False
    gt_fault_type: str = "NONE"
    gt_error_norm: float = 0.0


DEFAULT_TRI_SENSORS: Tuple[SensorSpec, ...] = (
    SensorSpec(sensor_id="S1_VIO", modality="Visual-Inertial Odometry", nominal_sigma=0.030),
    SensorSpec(sensor_id="S2_LIDAR", modality="LiDAR Scan-Matching", nominal_sigma=0.035),
    SensorSpec(sensor_id="S3_UWB", modality="UWB + IMU Fusion", nominal_sigma=0.045),
)


class TriSensorSimulator:
    """Generates synchronized 3-sensor observations with deterministic fault injection."""

    def __init__(
        self,
        sensors: Tuple[SensorSpec, ...] = DEFAULT_TRI_SENSORS,
        faults: Optional[List[FaultInjectionSpec]] = None,
        seed: int = 2026,
        dt: float = 0.20,
    ) -> None:
        self.sensors = sensors
        self.fault_map: Dict[str, FaultInjectionSpec] = {
            f.sensor_id: f for f in (faults or [])
        }
        self.rng = np.random.default_rng(seed)
        self.dt = dt
        self._frozen_values: Dict[str, np.ndarray] = {}

    def sample(self, step: int, true_pos: np.ndarray) -> Dict[str, SensorReading]:
        """Produce one observation tick for all 3 sensors at the given true 3D pose."""
        true_p = np.asarray(true_pos, dtype=np.float64).reshape(3)
        ts = round(step * self.dt, 4)
        readings: Dict[str, SensorReading] = {}

        for spec in self.sensors:
            noise = self.rng.normal(0.0, spec.nominal_sigma, size=3)
            measured = true_p + noise
            fault = self.fault_map.get(spec.sensor_id)

            fault_active = False
            fault_label = FaultType.NONE.value

            if fault is not None and fault.fault_type != FaultType.NONE:
                in_window = step >= fault.start_step and (
                    fault.end_step is None or step <= fault.end_step
                )
                if in_window:
                    elapsed = step - fault.start_step + 1
                    ftype = fault.fault_type

                    if ftype == FaultType.GRADUAL_DRIFT:
                        rate = np.asarray(fault.drift_rate_per_step, dtype=np.float64)
                        measured = measured + rate * elapsed
                        fault_active = True
                        fault_label = ftype.value

                    elif ftype == FaultType.HEAVY_DRIFT:
                        rate = np.asarray(fault.drift_rate_per_step, dtype=np.float64)
                        accel = np.asarray(fault.drift_accel_per_step2, dtype=np.float64)
                        measured = measured + rate * elapsed + 0.5 * accel * (elapsed ** 2)
                        fault_active = True
                        fault_label = ftype.value

                    elif ftype == FaultType.SUDDEN_BIAS:
                        bias = np.asarray(fault.bias_vector, dtype=np.float64)
                        measured = measured + bias
                        fault_active = True
                        fault_label = ftype.value

                    elif ftype == FaultType.OUTLIER_BURSTS:
                        if self.rng.random() < fault.outlier_prob:
                            direction = self.rng.normal(0.0, 1.0, size=3)
                            direction[2] *= 0.25  # Mostly horizontal spike
                            norm = float(np.linalg.norm(direction))
                            if norm > 1e-6:
                                direction = direction / norm
                            measured = measured + direction * fault.outlier_magnitude
                            fault_active = True
                            fault_label = ftype.value

                    elif ftype == FaultType.RETIMESTAMPED_FREEZE:
                        if spec.sensor_id not in self._frozen_values:
                            # Freeze at the last reading right when freeze begins
                            self._frozen_values[spec.sensor_id] = measured.copy()
                        # Tiny sub-millimeter quantization jitter or exact constant;
                        # timestamp and metadata_fresh remain completely normal!
                        measured = self._frozen_values[spec.sensor_id].copy()
                        fault_active = True
                        fault_label = ftype.value

                    elif ftype == FaultType.SENSOR_BLACKOUT:
                        measured = np.array([np.nan, np.nan, np.nan], dtype=np.float64)
                        fault_active = True
                        fault_label = ftype.value

            err_norm = (
                float(np.linalg.norm(measured - true_p))
                if np.all(np.isfinite(measured))
                else float("nan")
            )
            readings[spec.sensor_id] = SensorReading(
                sensor_id=spec.sensor_id,
                step=step,
                timestamp_s=ts,
                position=measured,
                nominal_sigma=spec.nominal_sigma,
                metadata_fresh=True,
                gt_fault_active=fault_active,
                gt_fault_type=fault_label,
                gt_error_norm=err_norm,
            )

        return readings
