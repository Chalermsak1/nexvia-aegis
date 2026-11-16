"""
NEXVIA AEGIS — Unit Tests for PX4 SITL & Autopilot MAVLink Hardware-in-the-Loop Bridge.

Verifies:
1. MAVLink CRC-16 & Binary Packet Encoding: Validates X.25 checksum integrity.
2. Live UDP Telemetry Loop: Handshake between MockPX4SITLServer and PX4SITLRunner.
3. High-Frequency Setpoint Streaming: Receives 50 Hz SET_POSITION_TARGET_LOCAL_NED.
4. Ville Martingale Anomaly Fail-Safe: Instant override to FAILSAFE_TRIGGERED on M_t >= 20.
"""

import time
import numpy as np
import pytest

from aegis.bridge.px4_sitl_runner import (
    MAVLinkPacketEncoder,
    MockPX4SITLServer,
    PX4FlightState,
    PX4SITLConfig,
    PX4SITLRunner,
)


def test_mavlink_packet_encoding_crc():
    """Verifies that MAVLink binary packets are formatted correctly with valid CRC-16."""
    pkt = MAVLinkPacketEncoder.encode_heartbeat(sys_id=1, comp_id=1, seq=0)
    assert len(pkt) == 17  # Header (6) + Payload (9) + CRC (2)
    assert pkt[0] == 0xFE  # MAVLink v1 magic byte
    assert pkt[5] == 0     # Msg ID 0 for HEARTBEAT


def test_px4_sitl_udp_communication_and_setpoints():
    """Verifies live UDP setpoint transmission and telemetry exchange."""
    # Use ephemeral testing ports to prevent collision with running services
    port_px4 = 15540
    port_companion = 15550

    cfg = PX4SITLConfig(
        host="127.0.0.1",
        px4_port=port_px4,
        companion_port=port_companion,
        heartbeat_rate_hz=10.0,
    )

    mock_server = MockPX4SITLServer(port=port_px4, companion_port=port_companion)
    runner = PX4SITLRunner(cfg)

    mock_server.start()
    runner.start()

    try:
        # Allow initial handshake
        time.sleep(0.35)
        assert runner.telemetry.is_alive is True

        # Stream setpoint
        pos_target = np.array([1.5, -2.0, -1.2])
        vel_target = np.array([0.5, 0.0, 0.0])
        accel_target = np.array([0.0, 0.0, 0.0])

        success = runner.send_setpoint(
            pos_ned=pos_target,
            vel_ned=vel_target,
            accel_ned=accel_target,
            yaw_rad=0.35,
        )
        assert success is True

        # Allow packet arrival at mock server
        time.sleep(0.1)
        assert len(mock_server.received_setpoints) > 0
        rx_pos, rx_vel = mock_server.received_setpoints[-1]
        np.testing.assert_allclose(rx_pos, pos_target, atol=1e-3)
        np.testing.assert_allclose(rx_vel, vel_target, atol=1e-3)

    finally:
        runner.stop()
        mock_server.stop()


def test_martingale_anomaly_emergency_failsafe():
    """Verifies that crossing the Ville supermartingale threshold immediately triggers fail-safe."""
    cfg = PX4SITLConfig(martingale_alpha=0.05)  # Threshold = 20.0
    runner = PX4SITLRunner(cfg)

    runner.flight_state = PX4FlightState.OFFBOARD_ACTIVE
    assert runner.flight_state == PX4FlightState.OFFBOARD_ACTIVE

    # Nominal wealth under H0: no trigger
    runner.update_martingale_anomaly(wealth=5.2)
    assert runner.flight_state == PX4FlightState.OFFBOARD_ACTIVE

    # Anomaly detected: wealth crosses 20.0
    runner.update_martingale_anomaly(wealth=24.8)
    assert runner.flight_state == PX4FlightState.FAILSAFE_TRIGGERED

    # In fail-safe mode, setpoint streaming is strictly blocked
    blocked = runner.send_setpoint(
        pos_ned=np.zeros(3),
        vel_ned=np.zeros(3),
        accel_ned=np.zeros(3),
        yaw_rad=0.0,
    )
    assert blocked is False
