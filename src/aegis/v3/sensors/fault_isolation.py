from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading


@dataclass(frozen=True)
class FaultIsolationResult:
    status: str

    estimate: np.ndarray
    sigma: float
    confidence: float

    safe_to_act: bool
    degraded: bool

    trusted_sensor: int | None
    isolated_sensor: int | None

    range_discrepancies: tuple[float, ...]

    valid_sensors: int
    total_sensors: int


class FaultIsolator:
    """
    Isolates a single faulty vector sensor by comparing
    each vector estimate independently against an
    independent range measurement.

    Important:
    - One vector sensor agreeing with range is not treated
      as absolute truth.
    - Both vector sensors must fail the range consistency
      check before declaring a multi-sensor fault.
    """

    def __init__(
        self,
        distance_threshold: float = 0.25,
    ):
        self.distance_threshold = float(
            distance_threshold
        )

    def _fuse(
        self,
        readings: list[SensorReading],
    ) -> tuple[np.ndarray, float]:
        estimates = np.asarray(
            [
                reading.estimate
                for reading in readings
            ],
            dtype=np.float64,
        )

        sigmas = np.asarray(
            [
                max(
                    float(reading.sigma),
                    1e-8,
                )
                for reading in readings
            ],
            dtype=np.float64,
        )

        weights = 1.0 / np.maximum(
            sigmas**2,
            1e-8,
        )

        estimate = (
            np.sum(
                estimates * weights[:, None],
                axis=0,
            )
            / np.sum(weights)
        )

        sigma = float(
            np.sqrt(
                1.0 / np.sum(weights)
            )
        )

        return estimate, sigma

    def isolate(
        self,
        readings: list[SensorReading],
        range_reading: RangeReading,
    ) -> FaultIsolationResult:

        total_sensors = len(readings)

        valid_indices = [
            i
            for i, reading in enumerate(readings)
            if reading.valid
        ]

        valid_sensors = len(valid_indices)

        if not range_reading.valid:
            return FaultIsolationResult(
                status="RANGE_UNAVAILABLE",
                estimate=np.zeros(
                    2,
                    dtype=np.float64,
                ),
                sigma=10.0,
                confidence=0.0,
                safe_to_act=False,
                degraded=True,
                trusted_sensor=None,
                isolated_sensor=None,
                range_discrepancies=(),
                valid_sensors=valid_sensors,
                total_sensors=total_sensors,
            )

        if valid_sensors == 0:
            return FaultIsolationResult(
                status="NO_VECTOR_SIGNAL",
                estimate=np.zeros(
                    2,
                    dtype=np.float64,
                ),
                sigma=10.0,
                confidence=0.0,
                safe_to_act=False,
                degraded=True,
                trusted_sensor=None,
                isolated_sensor=None,
                range_discrepancies=(),
                valid_sensors=0,
                total_sensors=total_sensors,
            )

        discrepancies = []

        for reading in readings:
            if not reading.valid:
                discrepancies.append(
                    float("inf")
                )
                continue

            estimated_distance = float(
                np.linalg.norm(
                    reading.estimate
                )
            )

            discrepancies.append(
                abs(
                    estimated_distance
                    - range_reading.distance
                )
            )

        discrepancies_tuple = tuple(
            discrepancies
        )

        # --------------------------------------------------
        # Single surviving vector sensor.
        # --------------------------------------------------

        if valid_sensors == 1:
            index = valid_indices[0]

            reading = readings[index]

            discrepancy = discrepancies[index]

            if discrepancy > self.distance_threshold:
                return FaultIsolationResult(
                    status="SINGLE_SENSOR_MISMATCH",
                    estimate=reading.estimate.copy(),
                    sigma=float(
                        reading.sigma * 2.5
                    ),
                    confidence=0.10,
                    safe_to_act=False,
                    degraded=True,
                    trusted_sensor=None,
                    isolated_sensor=index,
                    range_discrepancies=(
                        discrepancies_tuple
                    ),
                    valid_sensors=1,
                    total_sensors=total_sensors,
                )

            consistency_factor = float(
                np.exp(
                    -(
                        discrepancy
                        / max(
                            self.distance_threshold,
                            1e-8,
                        )
                    ) ** 2
                )
            )

            confidence = float(
                np.clip(
                    0.75
                    * consistency_factor,
                    0.0,
                    1.0,
                )
            )

            return FaultIsolationResult(
                status="DEGRADED_VERIFIED",
                estimate=reading.estimate.copy(),
                sigma=max(
                    float(reading.sigma * 2.0),
                    0.10,
                ),
                confidence=confidence,
                safe_to_act=(
                    confidence >= 0.60
                ),
                degraded=True,
                trusted_sensor=index,
                isolated_sensor=None,
                range_discrepancies=(
                    discrepancies_tuple
                ),
                valid_sensors=1,
                total_sensors=total_sensors,
            )

        # --------------------------------------------------
        # Two or more valid sensors.
        # --------------------------------------------------

        valid_discrepancies = [
            (
                index,
                discrepancies[index],
            )
            for index in valid_indices
        ]

        consistent = [
            (
                index,
                discrepancy,
            )
            for index, discrepancy
            in valid_discrepancies
            if discrepancy
            <= self.distance_threshold
        ]

        inconsistent = [
            (
                index,
                discrepancy,
            )
            for index, discrepancy
            in valid_discrepancies
            if discrepancy
            > self.distance_threshold
        ]

        # --------------------------------------------------
        # All valid vector sensors agree with range.
        # --------------------------------------------------

        if not inconsistent:
            valid_readings = [
                readings[index]
                for index in valid_indices
            ]

            estimate, sigma = self._fuse(
                valid_readings
            )

            max_discrepancy = max(
                discrepancy
                for _, discrepancy
                in valid_discrepancies
            )

            confidence = float(
                np.exp(
                    -0.5
                    * (
                        max_discrepancy
                        / max(
                            self.distance_threshold,
                            1e-8,
                        )
                    ) ** 2
                )
            )

            return FaultIsolationResult(
                status="VERIFIED",
                estimate=estimate,
                sigma=sigma,
                confidence=confidence,
                safe_to_act=(
                    confidence >= 0.75
                ),
                degraded=False,
                trusted_sensor=None,
                isolated_sensor=None,
                range_discrepancies=(
                    discrepancies_tuple
                ),
                valid_sensors=valid_sensors,
                total_sensors=total_sensors,
            )

        # --------------------------------------------------
        # Exactly one vector sensor agrees with range.
        #
        # Before isolating one sensor, require the vector
        # sensors themselves to disagree sufficiently.
        # This prevents common-mode faults from being
        # mistaken for a single-sensor fault.
        # --------------------------------------------------

        if (
            len(consistent) == 1
            and len(inconsistent) >= 1
        ):
            pairwise_separation = []

            for i in range(len(readings)):
                if not readings[i].valid:
                    continue

                for j in range(i + 1, len(readings)):
                    if not readings[j].valid:
                        continue

                    pairwise_separation.append(
                        float(
                            np.linalg.norm(
                                readings[i].estimate
                                - readings[j].estimate
                            )
                        )
                    )

            max_pairwise_separation = (
                max(pairwise_separation)
                if pairwise_separation
                else 0.0
            )

            # If vector sensors agree with each other while
            # disagreeing with the independent range modality,
            # the fault may be common-mode. Do not guess.
            if max_pairwise_separation <= max(
                0.25,
                self.distance_threshold,
            ):
                return FaultIsolationResult(
                    status="MULTI_SENSOR_FAULT",
                    estimate=np.zeros(
                        2,
                        dtype=np.float64,
                    ),
                    sigma=10.0,
                    confidence=0.0,
                    safe_to_act=False,
                    degraded=False,
                    trusted_sensor=None,
                    isolated_sensor=None,
                    range_discrepancies=(
                        discrepancies_tuple
                    ),
                    valid_sensors=valid_sensors,
                    total_sensors=total_sensors,
                )
            trusted_index = consistent[0][0]

            isolated_index = inconsistent[0][0]

            trusted_reading = readings[
                trusted_index
            ]

            discrepancy = consistent[0][1]

            confidence = float(
                np.exp(
                    -0.5
                    * (
                        discrepancy
                        / max(
                            self.distance_threshold,
                            1e-8,
                        )
                    ) ** 2
                )
            )

            confidence *= 0.90

            return FaultIsolationResult(
                status="ISOLATED_SENSOR_FAULT",
                estimate=trusted_reading.estimate.copy(),
                sigma=max(
                    float(
                        trusted_reading.sigma * 1.5
                    ),
                    0.075,
                ),
                confidence=float(
                    np.clip(
                        confidence,
                        0.0,
                        1.0,
                    )
                ),
                safe_to_act=(
                    confidence >= 0.60
                ),
                degraded=True,
                trusted_sensor=trusted_index,
                isolated_sensor=isolated_index,
                range_discrepancies=(
                    discrepancies_tuple
                ),
                valid_sensors=valid_sensors,
                total_sensors=total_sensors,
            )

        # --------------------------------------------------
        # More than one vector sensor disagrees with range.
        #
        # Do not guess which one is correct.
        # --------------------------------------------------

        return FaultIsolationResult(
            status="MULTI_SENSOR_FAULT",
            estimate=np.zeros(
                2,
                dtype=np.float64,
            ),
            sigma=10.0,
            confidence=0.0,
            safe_to_act=False,
            degraded=False,
            trusted_sensor=None,
            isolated_sensor=None,
            range_discrepancies=(
                discrepancies_tuple
            ),
            valid_sensors=valid_sensors,
            total_sensors=total_sensors,
        )
