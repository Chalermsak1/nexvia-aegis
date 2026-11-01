from collections import deque
import math
from typing import Deque, List, Tuple
import numpy as np
import pytest

from aegis.bridge.aegis_safety_box import (
    AegisSafetyBox,
    ObstacleEstimate,
    SafetyBoxStatus,
)
from aegis.bridge.pixhawk_mavlink_bridge import (
    MSG_ID_SET_ATTITUDE_TARGET,
    MSG_ID_SET_POSITION_TARGET_LOCAL_NED,
    PX4MavlinkBridge,
)


class MockUDPSocket:
    """Deterministic in-memory mock POSIX UDP socket for MAVLink SITL unit testing."""

    def __init__(self) -> None:
        self.rx_queue: Deque[Tuple[bytes, Tuple[str, int]]] = deque()
        self.tx_packets: List[Tuple[bytes, Tuple[str, int]]] = []
        self.closed: bool = False

    def push_rx(self, packet: bytes, addr: Tuple[str, int] = ("127.0.0.1", 14540)) -> None:
        self.rx_queue.append((packet, addr))

    def recvfrom(self, bufsize: int) -> Tuple[bytes, Tuple[str, int]]:
        if not self.rx_queue:
            raise BlockingIOError("No pending UDP datagrams")
        data, addr = self.rx_queue.popleft()
        return data[:bufsize], addr

    def sendto(self, data: bytes, addr: Tuple[str, int]) -> int:
        self.tx_packets.append((bytes(data), addr))
        return len(data)

    def close(self) -> None:
        self.closed = True


def test_px4_bridge_default_endpoints_and_heartbeat_local_pos_pipeline():
    """Verify HEARTBEAT + LOCAL_POSITION_NED -> AegisSafetyBox -> Flatness -> SET_ATTITUDE_TARGET."""
    mock_sock = MockUDPSocket()
    bridge = PX4MavlinkBridge(
        host="127.0.0.1",
        rx_port=14540,
        tx_port=14550,
        sock=mock_sock,
    )
    assert bridge.rx_port == 14540
    assert bridge.tx_port == 14550
    assert bridge.remote_endpoint == ("127.0.0.1", 14550)

    # Simulate incoming PX4 SITL frames: armed HEARTBEAT + LOCAL_POSITION_NED at z=-2.0m (2m altitude)
    fcu_encoder = PX4MavlinkBridge(sysid=1, compid=1, sock=MockUDPSocket())
    hb_pkt = fcu_encoder.encode_heartbeat(base_mode=0x80, custom_mode=6, system_status=4)
    pos_pkt = fcu_encoder.encode_local_position_ned(
        time_boot_ms=1000,
        x=0.0,
        y=0.0,
        z=-2.0,   # NED Down = -2.0 => +2.0 m Up in Aegis frame
        vx=1.5,
        vy=0.0,
        vz=0.0,
    )
    mock_sock.push_rx(hb_pkt)
    mock_sock.push_rx(pos_pkt)

    # Obstacle directly ahead at x = 1.0, z = +2.0
    obs = [ObstacleEstimate(center=np.array([1.0, 0.0, 2.0]), radius=0.45)]
    res = bridge.step(
        untrusted_accel=[3.0, 0.0, 0.0],
        obstacles=obs,
        psi_des=0.0,
        now_s=50.0,
    )

    assert res.messages_processed == 2
    assert bridge.connected is True
    assert bridge.fcu_armed is True
    assert res.failsafe_disconnect is False
    assert np.allclose(bridge.latest_telemetry.position, np.array([0.0, 0.0, 2.0]))
    assert res.safety_output.status == SafetyBoxStatus.BARRIER_INTERVENTION
    assert res.safety_output.safe_accel[0] < 0.0
    assert res.outbound_msg_id == MSG_ID_SET_ATTITUDE_TARGET

    # Verify outbound UDP frame is valid MAVLink v2 SET_ATTITUDE_TARGET sent to 127.0.0.1:14550
    assert len(mock_sock.tx_packets) == 1
    tx_raw, tx_addr = mock_sock.tx_packets[0]
    assert tx_addr == ("127.0.0.1", 14550)
    decoded_tx = bridge.decode_mavlink_packet(tx_raw)
    assert decoded_tx.msg_name == "SET_ATTITUDE_TARGET"
    q_tx = np.array(decoded_tx.fields["q"], dtype=np.float64)
    assert math.isclose(float(np.linalg.norm(q_tx)), 1.0, abs_tol=1e-5)
    assert 0.0 <= decoded_tx.fields["thrust"] <= 1.0


def test_px4_bridge_odometry_and_set_position_target_local_ned():
    """Verify ODOMETRY covariance decoding and outbound SET_POSITION_TARGET_LOCAL_NED framing."""
    mock_sock = MockUDPSocket()
    bridge = PX4MavlinkBridge(
        output_mode="SET_POSITION_TARGET_LOCAL_NED",
        sock=mock_sock,
    )
    fcu_encoder = PX4MavlinkBridge(sysid=1, compid=1, sock=MockUDPSocket())

    mock_sock.push_rx(fcu_encoder.encode_heartbeat(base_mode=0x80))
    mock_sock.push_rx(
        fcu_encoder.encode_odometry(
            time_usec=2_000_000,
            pos_ned=(1.0, -2.0, -3.0),
            quat_wxyz=(1.0, 0.0, 0.0, 0.0),
            vel_ned=(0.5, 0.2, -0.1),
            sigma_p=0.04,
            sigma_v=0.06,
        )
    )

    res = bridge.step(
        untrusted_accel=[1.2, -0.5, 0.4],
        obstacles=[],
        psi_des=0.25,
        now_s=10.0,
    )

    assert res.messages_processed == 2
    assert res.safety_output.status == SafetyBoxStatus.NOMINAL_PASSTHROUGH
    assert math.isclose(bridge.latest_telemetry.sigma_p, 0.04, abs_tol=1e-5)
    assert math.isclose(bridge.latest_telemetry.sigma_v, 0.06, abs_tol=1e-5)
    assert res.outbound_msg_id == MSG_ID_SET_POSITION_TARGET_LOCAL_NED

    tx_raw, _ = mock_sock.tx_packets[-1]
    decoded_tx = bridge.decode_mavlink_packet(tx_raw)
    assert decoded_tx.msg_name == "SET_POSITION_TARGET_LOCAL_NED"
    # Aegis (+X North, +Y West, +Z Up) = [1.2, -0.5, 0.4] => NED = [1.2, +0.5, -0.4]
    assert math.isclose(decoded_tx.fields["afx"], 1.2, abs_tol=1e-5)
    assert math.isclose(decoded_tx.fields["afy"], 0.5, abs_tol=1e-5)
    assert math.isclose(decoded_tx.fields["afz"], -0.4, abs_tol=1e-5)


def test_px4_bridge_odometry_high_covariance_triggers_observability_abstain():
    """Verify degraded EKF2 ODOMETRY covariance (sigma_p > 0.25 m) triggers deadbeat braking."""
    mock_sock = MockUDPSocket()
    bridge = PX4MavlinkBridge(sock=mock_sock)
    fcu_encoder = PX4MavlinkBridge(sysid=1, compid=1, sock=MockUDPSocket())

    mock_sock.push_rx(fcu_encoder.encode_heartbeat(base_mode=0x80))
    mock_sock.push_rx(
        fcu_encoder.encode_odometry(
            time_usec=3_000_000,
            pos_ned=(0.0, 0.0, -1.5),
            quat_wxyz=(1.0, 0.0, 0.0, 0.0),
            vel_ned=(1.2, 0.0, 0.0),
            sigma_p=0.35,  # > 0.25 m observability limit
            sigma_v=0.10,
        )
    )

    res = bridge.step(untrusted_accel=[2.0, 0.0, 0.0], now_s=20.0)
    assert res.safety_output.status == SafetyBoxStatus.OBSERVABILITY_ABSTAIN
    assert res.safety_output.safe_accel[0] < -0.5


def test_px4_bridge_autonomous_heartbeat_disconnect_failsafe():
    """Verify > 100 ms heartbeat silence triggers autonomous disconnect failsafe braking."""
    mock_sock = MockUDPSocket()
    bridge = PX4MavlinkBridge(heartbeat_timeout_ms=100.0, sock=mock_sock)
    fcu_encoder = PX4MavlinkBridge(sysid=1, compid=1, sock=MockUDPSocket())

    # t = 100.000s: nominal heartbeat + forward motion
    mock_sock.push_rx(fcu_encoder.encode_heartbeat(base_mode=0x80))
    mock_sock.push_rx(
        fcu_encoder.encode_local_position_ned(
            time_boot_ms=5000, x=0.0, y=0.0, z=-1.5, vx=1.0, vy=0.0, vz=0.0
        )
    )
    res_ok = bridge.step(untrusted_accel=[1.0, 0.0, 0.0], now_s=100.000)
    assert res_ok.failsafe_disconnect is False
    assert bridge.connected is True
    assert bridge.failsafe_active is False

    # t = 100.150s (150 ms > 100 ms timeout with no new HEARTBEAT): must trigger failsafe!
    res_timeout = bridge.step(untrusted_accel=[2.0, 0.0, 0.0], now_s=100.150)
    assert res_timeout.failsafe_disconnect is True
    assert bridge.connected is False
    assert bridge.failsafe_active is True
    assert res_timeout.safety_output.status == SafetyBoxStatus.WATCHDOG_TIMEOUT_FAILSAFE
    assert res_timeout.safety_output.safe_accel[0] < -0.5

    # Outbound failsafe frame must still be transmitted to command safe braking on FCU
    assert len(mock_sock.tx_packets) == 2
    decoded_fs = bridge.decode_mavlink_packet(mock_sock.tx_packets[-1][0])
    assert decoded_fs.msg_name == "SET_ATTITUDE_TARGET"


def test_px4_bridge_corrupted_crc_rejected():
    """Verify corrupted MAVLink packets fail CRC-16 validation cleanly."""
    fcu_encoder = PX4MavlinkBridge(sysid=1, compid=1, sock=MockUDPSocket())
    pkt = bytearray(fcu_encoder.encode_heartbeat())
    pkt[-1] ^= 0xFF  # Flip bits in CRC-16 byte

    with pytest.raises(ValueError, match="CRC mismatch"):
        PX4MavlinkBridge.decode_mavlink_packet(bytes(pkt))
