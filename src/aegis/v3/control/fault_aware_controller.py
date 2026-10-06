from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.v3.control.temporal import (
    TemporalConsistencyMonitor,
)
from aegis.v3.control.windowed_temporal import (
    WindowedTemporalConsistencyMonitor,
)
from aegis.v3.sensors.cross_modal import (
    RangeReading,
)
from aegis.v3.sensors.fault_isolation import (
    FaultIsolationResult,
    FaultIsolator,
)
from aegis.v3.sensors.sensors import (
    SensorReading,
)


@dataclass(frozen=True)
class FaultAwareVerification:
    estimate: np.ndarray
    sigma: float
    confidence: float

    status: str
    temporal_status: str

    safe_to_act: bool
    degraded: bool

    temporal_consistent: bool

    trusted_sensor: int | None
    isolated_sensor: int | None

    range_discrepancies: tuple[float, ...]


class FaultAwareVerificationController:
    """
    Nexvia Aegis fault-aware verification layer.

    Evidence hierarchy:

        vector sensor agreement
              +
        independent range verification
              +
        temporal consistency
              +
        fault isolation

    A single faulty sensor can be quarantined.

    Multiple mutually inconsistent sensors are never
    guessed into a supposedly correct state.
    """

    def __init__(
        self,
        fault_isolator: FaultIsolator | None = None,
        temporal_monitor=None,
    ):
        self.fault_isolator = (
            fault_isolator
            or FaultIsolator()
        )

        self.temporal_monitor = (
            temporal_monitor
            or WindowedTemporalConsistencyMonitor()
        )

    def reset(self) -> None:
        self.temporal_monitor.reset()

    def verify(
        self,
        vector_readings: list[SensorReading],
        range_reading: RangeReading,
        previous_action: np.ndarray,
    ) -> FaultAwareVerification:

        fault: FaultIsolationResult = (
            self.fault_isolator.isolate(
                readings=vector_readings,
                range_reading=range_reading,
            )
        )

        # No trustworthy vector estimate.
        if fault.status in {
            "NO_VECTOR_SIGNAL",
            "RANGE_UNAVAILABLE",
            "SINGLE_SENSOR_MISMATCH",
            "MULTI_SENSOR_FAULT",
        }:
            temporal = self.temporal_monitor.update(
                fault.estimate,
                previous_action,
            )

            return FaultAwareVerification(
                estimate=fault.estimate.copy(),
                sigma=float(fault.sigma),
                confidence=float(
                    min(
                        fault.confidence,
                        temporal.confidence,
                    )
                ),
                status=fault.status,
                temporal_status=temporal.status,
                safe_to_act=False,
                degraded=fault.degraded,
                temporal_consistent=(
                    temporal.consistent
                ),
                trusted_sensor=fault.trusted_sensor,
                isolated_sensor=fault.isolated_sensor,
                range_discrepancies=(
                    fault.range_discrepancies
                ),
            )

        temporal = self.temporal_monitor.update(
            estimate=fault.estimate,
            action=previous_action,
        )

        confidence = float(
            min(
                fault.confidence,
                temporal.confidence,
            )
        )

        status = fault.status

        safe_to_act = bool(
            fault.safe_to_act
        )

        # Temporal contradiction overrides a
        # previously trusted estimate.
        if not temporal.consistent:
            if "MISMATCH" in fault.status:
                status = "MULTI_MODAL_MISMATCH"
            else:
                status = "TEMPORAL_CONTRADICTION"

            safe_to_act = False

        # Window warmup does not penalize an otherwise
        # verified measurement.
        elif temporal.status == "WARMUP":
            confidence = float(
                fault.confidence
            )

        return FaultAwareVerification(
            estimate=fault.estimate.copy(),
            sigma=max(
                float(fault.sigma),
                float(
                    temporal.jump_magnitude
                ),
            ),
            confidence=float(
                np.clip(
                    confidence,
                    0.0,
                    1.0,
                )
            ),
            status=status,
            temporal_status=temporal.status,
            safe_to_act=(
                safe_to_act
                and temporal.consistent
            ),
            degraded=fault.degraded,
            temporal_consistent=(
                temporal.consistent
            ),
            trusted_sensor=fault.trusted_sensor,
            isolated_sensor=fault.isolated_sensor,
            range_discrepancies=(
                fault.range_discrepancies
            ),
        )
