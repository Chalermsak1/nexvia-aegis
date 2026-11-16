"""
NEXVIA-AEGIS: Lightweight POSIX UDP MAVLink v2 SITL / Pixhawk 6X Offboard Bridge.

Provides zero-external-dependency MAVLink v2 framing, X.25 CRC-16/MCRF4XX validation,
telemetry decoding (`HEARTBEAT`, `LOCAL_POSITION_NED`, `ODOMETRY`), inline safety
filtering through `AegisSafetyBox`, differential flatness attitude allocation through
`QuadrotorFlatnessConverter`, outbound `SET_ATTITUDE_TARGET` and
`SET_POSITION_TARGET_LOCAL_NED` serialization, and an autonomous > 100 ms heartbeat
disconnect failsafe detector.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import socket
import struct
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from .aegis_safety_box import (
    AegisSafetyBox,
    ObstacleEstimate,
    SafetyBoxOutput,
    SafetyBoxStatus,
    VehicleTelemetry,
)
from .quadrotor_flatness import FlatnessSetpoint, QuadrotorFlatnessConverter


# MAVLink Framing Constants
MAVLINK_STX_V2 = 0xFD
MAVLINK_STX_V1 = 0xFE

MSG_ID_HEARTBEAT = 0
MSG_ID_LOCAL_POSITION_NED = 32
MSG_ID_SET_ATTITUDE_TARGET = 82
MSG_ID_SET_POSITION_TARGET_LOCAL_NED = 84
MSG_ID_ODOMETRY = 331

# Official MAVLink common.xml CRC_EXTRA seeds
CRC_EXTRA_MAP: Dict[int, int] = {
    MSG_ID_HEARTBEAT: 50,
    MSG_ID_LOCAL_POSITION_NED: 185,
    MSG_ID_SET_ATTITUDE_TARGET: 49,
    MSG_ID_SET_POSITION_TARGET_LOCAL_NED: 143,
    MSG_ID_ODOMETRY: 91,
}

# MAVLink Coordinate Frames & Type Masks
MAV_FRAME_LOCAL_NED = 1
ATTITUDE_MASK_IGNORE_RATES = 0b00000111  # Use quaternion + thrust, ignore body rates
POS_TARGET_MASK_ACCEL_ONLY = 0b0000110000111111  # Ignore pos (1|2|4), vel (8|16|32), yaw_rate (2048); use afx,afy,afz + yaw


def mavlink_crc_accumulate(byte_val: int, crc: int) -> int:
    """Accumulates one byte into an X.25 CRC-16/MCRF4XX checksum."""
    tmp = (byte_val ^ (crc & 0xFF)) & 0xFF
    tmp = (tmp ^ ((tmp << 4) & 0xFF)) & 0xFF
    return (((crc >> 8) & 0xFF) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF


def mavlink_compute_crc(header_and_payload: bytes, crc_extra: int) -> int:
    """Computes 16-bit MAVLink X.25 checksum including message CRC_EXTRA."""
    crc = 0xFFFF
    for b in header_and_payload:
        crc = mavlink_crc_accumulate(b, crc)
    crc = mavlink_crc_accumulate(crc_extra & 0xFF, crc)
    return crc


def ned_to_aegis_vec(vec_ned: Sequence[float]) -> np.ndarray:
    """Transforms NED (North, East, Down) vector to Aegis NWU/FLU (+X North, +Y West, +Z Up)."""
    return np.array([float(vec_ned[0]), -float(vec_ned[1]), -float(vec_ned[2])], dtype=np.float64)


def aegis_to_ned_vec(vec_aegis: Sequence[float]) -> np.ndarray:
    """Transforms Aegis NWU/FLU (+X North, +Y West, +Z Up) vector to PX4 NED."""
    return np.array([float(vec_aegis[0]), -float(vec_aegis[1]), -float(vec_aegis[2])], dtype=np.float64)


def quat_flu_to_frd_ned(q_wxyz: Sequence[float]) -> np.ndarray:
    """Transforms attitude quaternion [w, x, y, z] from NWU/FLU to PX4 NED/FRD via diag(1, -1, -1)."""
    q = np.array(
        [float(q_wxyz[0]), float(q_wxyz[1]), -float(q_wxyz[2]), -float(q_wxyz[3])],
        dtype=np.float64,
    )
    norm = float(np.linalg.norm(q))
    return q / norm if norm > 1e-12 else np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)


@dataclass
class DecodedMavlinkMessage:
    msg_id: int
    msg_name: str
    seq: int
    sysid: int
    compid: int
    fields: Dict[str, Any]


@dataclass
class BridgeStepResult:
    safety_output: SafetyBoxOutput
    flatness_setpoint: FlatnessSetpoint
    outbound_frame: bytes
    outbound_msg_id: int
    failsafe_disconnect: bool
    messages_processed: int


class PX4MavlinkBridge:
    """
    Lightweight POSIX UDP MAVLink v2 Bridge for PX4 SITL / QGroundControl / Pixhawk 6X.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        rx_port: int = 14540,
        tx_port: int = 14550,
        tx_host: Optional[str] = None,
        safety_box: Optional[AegisSafetyBox] = None,
        flatness_converter: Optional[QuadrotorFlatnessConverter] = None,
        heartbeat_timeout_ms: float = 100.0,
        output_mode: str = "SET_ATTITUDE_TARGET",
        sysid: int = 255,
        compid: int = 191,
        target_system: int = 1,
        target_component: int = 1,
        sock: Optional[socket.socket] = None,
        bind_socket: bool = False,
    ) -> None:
        if output_mode not in ("SET_ATTITUDE_TARGET", "SET_POSITION_TARGET_LOCAL_NED"):
            raise ValueError(
                f"output_mode must be 'SET_ATTITUDE_TARGET' or 'SET_POSITION_TARGET_LOCAL_NED', got {output_mode!r}"
            )

        self.host = host
        self.rx_port = int(rx_port)
        self.tx_port = int(tx_port)
        self.tx_host = tx_host if tx_host is not None else host
        self.heartbeat_timeout_ms = float(heartbeat_timeout_ms)
        self.output_mode = output_mode
        self.sysid = int(sysid) & 0xFF
        self.compid = int(compid) & 0xFF
        self.target_system = int(target_system) & 0xFF
        self.target_component = int(target_component) & 0xFF

        self.safety_box = safety_box if safety_box is not None else AegisSafetyBox()
        self.flatness = (
            flatness_converter
            if flatness_converter is not None
            else QuadrotorFlatnessConverter()
        )

        self._owns_socket = sock is None
        if sock is not None:
            self.sock = sock
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
            if bind_socket:
                self.sock.bind((self.host, self.rx_port))

        self._tx_seq: int = 0
        self._boot_epoch_s: float = time.monotonic()

        # FCU state & latest telemetry
        self.last_heartbeat_s: Optional[float] = None
        self.connected: bool = False
        self.failsafe_active: bool = False
        self.fcu_armed: bool = False
        self.fcu_custom_mode: int = 0
        self.fcu_system_status: int = 0
        self.latest_telemetry: VehicleTelemetry = VehicleTelemetry(
            timestamp_s=0.0,
            position=np.zeros(3, dtype=np.float64),
            velocity=np.zeros(3, dtype=np.float64),
            sigma_p=0.05,
            sigma_v=0.08,
            beta_min=1.0,
        )

    @property
    def remote_endpoint(self) -> Tuple[str, int]:
        return (self.tx_host, self.tx_port)

    def close(self) -> None:
        if self._owns_socket and self.sock is not None:
            self.sock.close()

    # ------------------------------------------------------------------
    # MAVLink v2 Packet Framing & Serialization
    # ------------------------------------------------------------------
    def _next_seq(self) -> int:
        seq = self._tx_seq & 0xFF
        self._tx_seq = (self._tx_seq + 1) & 0xFF
        return seq

    def pack_mavlink_v2_frame(self, msg_id: int, payload: bytes) -> bytes:
        """Wraps a serialized payload into a standard MAVLink v2 packet with CRC-16."""
        crc_extra = CRC_EXTRA_MAP.get(msg_id)
        if crc_extra is None:
            raise ValueError(f"Unsupported MAVLink msg_id={msg_id}")

        seq = self._next_seq()
        header_no_stx = struct.pack(
            "<BBBBBBBB",
            len(payload),
            0,  # incompat_flags
            0,  # compat_flags
            seq,
            self.sysid,
            self.compid,
            msg_id & 0xFF,
            (msg_id >> 8) & 0xFF,
        ) + bytes([(msg_id >> 16) & 0xFF])

        crc = mavlink_compute_crc(header_no_stx + payload, crc_extra)
        return bytes([MAVLINK_STX_V2]) + header_no_stx + payload + struct.pack("<H", crc)

    def encode_heartbeat(
        self,
        mav_type: int = 18,
        autopilot: int = 8,
        base_mode: int = 0,
        custom_mode: int = 0,
        system_status: int = 4,
    ) -> bytes:
        payload = struct.pack(
            "<IBBBBB",
            int(custom_mode) & 0xFFFFFFFF,
            int(mav_type) & 0xFF,
            int(autopilot) & 0xFF,
            int(base_mode) & 0xFF,
            int(system_status) & 0xFF,
            3,  # mavlink_version = 3
        )
        return self.pack_mavlink_v2_frame(MSG_ID_HEARTBEAT, payload)

    def encode_local_position_ned(
        self,
        time_boot_ms: int,
        x: float,
        y: float,
        z: float,
        vx: float,
        vy: float,
        vz: float,
    ) -> bytes:
        payload = struct.pack(
            "<Iffffff",
            int(time_boot_ms) & 0xFFFFFFFF,
            float(x),
            float(y),
            float(z),
            float(vx),
            float(vy),
            float(vz),
        )
        return self.pack_mavlink_v2_frame(MSG_ID_LOCAL_POSITION_NED, payload)

    def encode_odometry(
        self,
        time_usec: int,
        pos_ned: Sequence[float],
        quat_wxyz: Sequence[float],
        vel_ned: Sequence[float],
        ang_vel_frd: Sequence[float] = (0.0, 0.0, 0.0),
        sigma_p: float = 0.05,
        sigma_v: float = 0.08,
        frame_id: int = MAV_FRAME_LOCAL_NED,
        child_frame_id: int = 1,
    ) -> bytes:
        pose_cov = [0.0] * 21
        vel_cov = [0.0] * 21
        var_p = float(sigma_p) ** 2
        var_v = float(sigma_v) ** 2
        # Upper-triangle diagonal indices of 6x6 matrix: (0,0)->0, (1,1)->6, (2,2)->11
        pose_cov[0] = pose_cov[6] = pose_cov[11] = var_p
        vel_cov[0] = vel_cov[6] = vel_cov[11] = var_v

        payload = struct.pack(
            "<Qffffffffff21ffff21fBB",
            int(time_usec) & 0xFFFFFFFFFFFFFFFF,
            float(pos_ned[0]),
            float(pos_ned[1]),
            float(pos_ned[2]),
            float(quat_wxyz[0]),
            float(quat_wxyz[1]),
            float(quat_wxyz[2]),
            float(quat_wxyz[3]),
            float(vel_ned[0]),
            float(vel_ned[1]),
            float(vel_ned[2]),
            *pose_cov,
            float(ang_vel_frd[0]),
            float(ang_vel_frd[1]),
            float(ang_vel_frd[2]),
            *vel_cov,
            int(frame_id) & 0xFF,
            int(child_frame_id) & 0xFF,
        )
        return self.pack_mavlink_v2_frame(MSG_ID_ODOMETRY, payload)

    def encode_set_attitude_target(
        self,
        flatness_sp: FlatnessSetpoint,
        body_rates_rad_s: Sequence[float] = (0.0, 0.0, 0.0),
        type_mask: int = ATTITUDE_MASK_IGNORE_RATES,
        time_boot_ms: Optional[int] = None,
    ) -> bytes:
        """Formats outbound MAVLink `SET_ATTITUDE_TARGET` (#82) packet in PX4 NED/FRD."""
        t_ms = (
            int(time_boot_ms)
            if time_boot_ms is not None
            else int((time.monotonic() - self._boot_epoch_s) * 1000.0) & 0xFFFFFFFF
        )
        q_ned = quat_flu_to_frd_ned(flatness_sp.q_des)
        payload = struct.pack(
            "<IffffffffBBB",
            t_ms & 0xFFFFFFFF,
            float(q_ned[0]),
            float(q_ned[1]),
            float(q_ned[2]),
            float(q_ned[3]),
            float(body_rates_rad_s[0]),
            float(body_rates_rad_s[1]),
            float(body_rates_rad_s[2]),
            float(np.clip(flatness_sp.thrust_normalized, 0.0, 1.0)),
            self.target_system,
            self.target_component,
            int(type_mask) & 0xFF,
        )
        return self.pack_mavlink_v2_frame(MSG_ID_SET_ATTITUDE_TARGET, payload)

    def encode_set_position_target_local_ned(
        self,
        safe_accel_aegis: Sequence[float],
        yaw_aegis_rad: float = 0.0,
        pos_ned: Sequence[float] = (0.0, 0.0, 0.0),
        vel_ned: Sequence[float] = (0.0, 0.0, 0.0),
        yaw_rate_ned: float = 0.0,
        type_mask: int = POS_TARGET_MASK_ACCEL_ONLY,
        time_boot_ms: Optional[int] = None,
    ) -> bytes:
        """Formats outbound MAVLink `SET_POSITION_TARGET_LOCAL_NED` (#84) packet."""
        t_ms = (
            int(time_boot_ms)
            if time_boot_ms is not None
            else int((time.monotonic() - self._boot_epoch_s) * 1000.0) & 0xFFFFFFFF
        )
        acc_ned = aegis_to_ned_vec(safe_accel_aegis)
        yaw_ned = -float(yaw_aegis_rad)

        payload = struct.pack(
            "<IfffffffffffHBB",
            t_ms & 0xFFFFFFFF,
            float(pos_ned[0]),
            float(pos_ned[1]),
            float(pos_ned[2]),
            float(vel_ned[0]),
            float(vel_ned[1]),
            float(vel_ned[2]),
            float(acc_ned[0]),
            float(acc_ned[1]),
            float(acc_ned[2]),
            yaw_ned,
            float(yaw_rate_ned),
            int(type_mask) & 0xFFFF,
            self.target_system,
            self.target_component,
        ) + bytes([MAV_FRAME_LOCAL_NED])
        return self.pack_mavlink_v2_frame(MSG_ID_SET_POSITION_TARGET_LOCAL_NED, payload)

    # ------------------------------------------------------------------
    # MAVLink Packet Decoding & Telemetry Ingestion
    # ------------------------------------------------------------------
    @staticmethod
    def decode_mavlink_packet(raw: bytes) -> DecodedMavlinkMessage:
        """Decodes and CRC-validates a MAVLink v2 (or v1) packet."""
        if len(raw) < 8:
            raise ValueError(f"Packet too short ({len(raw)} bytes)")

        stx = raw[0]
        if stx == MAVLINK_STX_V2:
            if len(raw) < 12:
                raise ValueError("MAVLink v2 frame shorter than 12-byte minimum")
            payload_len = raw[1]
            incompat_flags = raw[2]
            sig_len = 13 if (incompat_flags & 0x01) else 0
            expected_total = 12 + payload_len + sig_len
            if len(raw) < expected_total:
                raise ValueError(
                    f"Truncated MAVLink v2 frame: got {len(raw)}, expected {expected_total}"
                )
            seq = raw[4]
            sysid = raw[5]
            compid = raw[6]
            msg_id = raw[7] | (raw[8] << 8) | (raw[9] << 16)
            header_body = raw[1:10]
            payload = raw[10 : 10 + payload_len]
            rx_crc = struct.unpack("<H", raw[10 + payload_len : 12 + payload_len])[0]
        elif stx == MAVLINK_STX_V1:
            payload_len = raw[1]
            expected_total = 8 + payload_len
            if len(raw) < expected_total:
                raise ValueError("Truncated MAVLink v1 frame")
            seq = raw[2]
            sysid = raw[3]
            compid = raw[4]
            msg_id = raw[5]
            header_body = raw[1:6]
            payload = raw[6 : 6 + payload_len]
            rx_crc = struct.unpack("<H", raw[6 + payload_len : 8 + payload_len])[0]
        else:
            raise ValueError(f"Unknown MAVLink STX byte: 0x{stx:02X}")

        crc_extra = CRC_EXTRA_MAP.get(msg_id)
        if crc_extra is None:
            raise ValueError(f"Unsupported MAVLink msg_id={msg_id}")

        calc_crc = mavlink_compute_crc(header_body + payload, crc_extra)
        if rx_crc != calc_crc:
            raise ValueError(
                f"MAVLink CRC mismatch for msg_id={msg_id}: rx=0x{rx_crc:04X}, calc=0x{calc_crc:04X}"
            )

        if msg_id == MSG_ID_HEARTBEAT:
            padded = payload.ljust(9, b"\x00")[:9]
            custom_mode, mav_type, autopilot, base_mode, system_status, mav_ver = (
                struct.unpack("<IBBBBB", padded)
            )
            return DecodedMavlinkMessage(
                msg_id=msg_id,
                msg_name="HEARTBEAT",
                seq=seq,
                sysid=sysid,
                compid=compid,
                fields={
                    "custom_mode": custom_mode,
                    "type": mav_type,
                    "autopilot": autopilot,
                    "base_mode": base_mode,
                    "system_status": system_status,
                    "mavlink_version": mav_ver,
                },
            )

        if msg_id == MSG_ID_LOCAL_POSITION_NED:
            padded = payload.ljust(28, b"\x00")[:28]
            time_boot_ms, x, y, z, vx, vy, vz = struct.unpack("<Iffffff", padded)
            return DecodedMavlinkMessage(
                msg_id=msg_id,
                msg_name="LOCAL_POSITION_NED",
                seq=seq,
                sysid=sysid,
                compid=compid,
                fields={
                    "time_boot_ms": time_boot_ms,
                    "x": x,
                    "y": y,
                    "z": z,
                    "vx": vx,
                    "vy": vy,
                    "vz": vz,
                },
            )

        if msg_id == MSG_ID_ODOMETRY:
            padded = payload.ljust(230, b"\x00")[:230]
            unpacked = struct.unpack("<Qffffffffff21ffff21fBB", padded)
            time_usec = unpacked[0]
            x, y, z = unpacked[1:4]
            q = unpacked[4:8]
            vx, vy, vz = unpacked[8:11]
            pose_cov = unpacked[11:32]
            rollspeed, pitchspeed, yawspeed = unpacked[32:35]
            vel_cov = unpacked[35:56]
            frame_id = unpacked[56]
            child_frame_id = unpacked[57]
            return DecodedMavlinkMessage(
                msg_id=msg_id,
                msg_name="ODOMETRY",
                seq=seq,
                sysid=sysid,
                compid=compid,
                fields={
                    "time_usec": time_usec,
                    "x": x,
                    "y": y,
                    "z": z,
                    "q": q,
                    "vx": vx,
                    "vy": vy,
                    "vz": vz,
                    "rollspeed": rollspeed,
                    "pitchspeed": pitchspeed,
                    "yawspeed": yawspeed,
                    "pose_covariance": pose_cov,
                    "velocity_covariance": vel_cov,
                    "frame_id": frame_id,
                    "child_frame_id": child_frame_id,
                },
            )

        if msg_id == MSG_ID_SET_ATTITUDE_TARGET:
            padded = payload.ljust(39, b"\x00")[:39]
            unpacked = struct.unpack("<IffffffffBBB", padded)
            return DecodedMavlinkMessage(
                msg_id=msg_id,
                msg_name="SET_ATTITUDE_TARGET",
                seq=seq,
                sysid=sysid,
                compid=compid,
                fields={
                    "time_boot_ms": unpacked[0],
                    "q": unpacked[1:5],
                    "body_roll_rate": unpacked[5],
                    "body_pitch_rate": unpacked[6],
                    "body_yaw_rate": unpacked[7],
                    "thrust": unpacked[8],
                    "target_system": unpacked[9],
                    "target_component": unpacked[10],
                    "type_mask": unpacked[11],
                },
            )

        if msg_id == MSG_ID_SET_POSITION_TARGET_LOCAL_NED:
            padded = payload.ljust(53, b"\x00")[:53]
            unpacked = struct.unpack("<IfffffffffffHBBB", padded)
            return DecodedMavlinkMessage(
                msg_id=msg_id,
                msg_name="SET_POSITION_TARGET_LOCAL_NED",
                seq=seq,
                sysid=sysid,
                compid=compid,
                fields={
                    "time_boot_ms": unpacked[0],
                    "x": unpacked[1],
                    "y": unpacked[2],
                    "z": unpacked[3],
                    "vx": unpacked[4],
                    "vy": unpacked[5],
                    "vz": unpacked[6],
                    "afx": unpacked[7],
                    "afy": unpacked[8],
                    "afz": unpacked[9],
                    "yaw": unpacked[10],
                    "yaw_rate": unpacked[11],
                    "type_mask": unpacked[12],
                    "target_system": unpacked[13],
                    "target_component": unpacked[14],
                    "coordinate_frame": unpacked[15],
                },
            )

        raise ValueError(f"Unhandled MAVLink msg_id={msg_id}")

    def ingest_packet(self, raw: bytes, now_s: Optional[float] = None) -> DecodedMavlinkMessage:
        """Decodes a single MAVLink packet and updates FCU connection / telemetry state."""
        t_now = now_s if now_s is not None else time.time()
        msg = self.decode_mavlink_packet(raw)

        if msg.msg_id == MSG_ID_HEARTBEAT:
            self.last_heartbeat_s = t_now
            self.connected = True
            self.failsafe_active = False
            self.fcu_custom_mode = int(msg.fields["custom_mode"])
            self.fcu_system_status = int(msg.fields["system_status"])
            self.fcu_armed = bool(int(msg.fields["base_mode"]) & 0x80)
        elif msg.msg_id == MSG_ID_LOCAL_POSITION_NED:
            pos_aegis = ned_to_aegis_vec(
                (msg.fields["x"], msg.fields["y"], msg.fields["z"])
            )
            vel_aegis = ned_to_aegis_vec(
                (msg.fields["vx"], msg.fields["vy"], msg.fields["vz"])
            )
            self.latest_telemetry = VehicleTelemetry(
                timestamp_s=t_now,
                position=pos_aegis,
                velocity=vel_aegis,
                sigma_p=self.latest_telemetry.sigma_p,
                sigma_v=self.latest_telemetry.sigma_v,
                beta_min=self.latest_telemetry.beta_min,
            )
        elif msg.msg_id == MSG_ID_ODOMETRY:
            pos_aegis = ned_to_aegis_vec(
                (msg.fields["x"], msg.fields["y"], msg.fields["z"])
            )
            vel_aegis = ned_to_aegis_vec(
                (msg.fields["vx"], msg.fields["vy"], msg.fields["vz"])
            )
            pose_cov = msg.fields["pose_covariance"]
            vel_cov = msg.fields["velocity_covariance"]

            sigma_p = self.latest_telemetry.sigma_p
            pose_vars = [pose_cov[0], pose_cov[6], pose_cov[11]]
            if all(math.isfinite(v) and v > 0.0 for v in pose_vars):
                sigma_p = math.sqrt(max(pose_vars))

            sigma_v = self.latest_telemetry.sigma_v
            vel_vars = [vel_cov[0], vel_cov[6], vel_cov[11]]
            if all(math.isfinite(v) and v > 0.0 for v in vel_vars):
                sigma_v = math.sqrt(max(vel_vars))

            self.latest_telemetry = VehicleTelemetry(
                timestamp_s=t_now,
                position=pos_aegis,
                velocity=vel_aegis,
                sigma_p=sigma_p,
                sigma_v=sigma_v,
                beta_min=self.latest_telemetry.beta_min,
            )

        return msg

    def poll_incoming(self, now_s: Optional[float] = None, max_packets: int = 32) -> int:
        """Drains pending UDP datagrams from the non-blocking socket."""
        t_now = now_s if now_s is not None else time.time()
        count = 0
        for _ in range(max_packets):
            try:
                data, _addr = self.sock.recvfrom(512)
            except (BlockingIOError, InterruptedError):
                break
            if not data:
                break
            self.ingest_packet(data, now_s=t_now)
            count += 1
        return count

    def is_heartbeat_timed_out(self, now_s: Optional[float] = None) -> bool:
        """Returns True if no HEARTBEAT has arrived or > heartbeat_timeout_ms has elapsed."""
        if self.last_heartbeat_s is None:
            return True
        t_now = now_s if now_s is not None else time.time()
        elapsed_ms = (t_now - self.last_heartbeat_s) * 1000.0
        return elapsed_ms > self.heartbeat_timeout_ms

    # ------------------------------------------------------------------
    # End-to-End Closed-Loop Offboard Safety Step
    # ------------------------------------------------------------------
    def step(
        self,
        untrusted_accel: Sequence[float],
        obstacles: Optional[List[ObstacleEstimate]] = None,
        psi_des: float = 0.0,
        now_s: Optional[float] = None,
        output_mode: Optional[str] = None,
        use_nmpc: bool = False,
        corridor_planes: Optional[Sequence[Tuple[Sequence[float], float]]] = None,
        target_pos: Optional[Sequence[float]] = None,
    ) -> BridgeStepResult:
        """
        1. Polls incoming MAVLink telemetry (`HEARTBEAT`, `LOCAL_POSITION_NED`, `ODOMETRY`).
        2. Evaluates > 100 ms heartbeat disconnect detector.
        3. Filters command via `AegisSafetyBox` (or engages deadbeat braking on disconnect).
           Supports both single-step CLBF-QP and receding horizon NMPC-HOCBF with corridor polytopes.
        4. Maps safe acceleration through `QuadrotorFlatnessConverter`.
        5. Transmits `SET_ATTITUDE_TARGET` or `SET_POSITION_TARGET_LOCAL_NED` over UDP.
        """
        t_now = now_s if now_s is not None else time.time()
        obs_list = obstacles if obstacles is not None else []
        mode = output_mode if output_mode is not None else self.output_mode

        n_rx = self.poll_incoming(now_s=t_now)

        if self.is_heartbeat_timed_out(now_s=t_now):
            self.connected = False
            self.failsafe_active = True
            t0 = time.perf_counter()
            safe_a = self.safety_box.compute_deadbeat_braking(self.latest_telemetry.velocity)
            safety_out = SafetyBoxOutput(
                safe_accel=safe_a,
                status=SafetyBoxStatus.WATCHDOG_TIMEOUT_FAILSAFE,
                intervened=True,
                min_margin=-1.0,
                latency_us=(time.perf_counter() - t0) * 1e6,
                dwell_active=True,
            )
            failsafe_disconnect = True
        else:
            self.failsafe_active = False
            if use_nmpc:
                safety_out = self.safety_box.process_command_nmpc(
                    untrusted_accel=np.asarray(untrusted_accel, dtype=np.float64),
                    telemetry=self.latest_telemetry,
                    obstacles=obs_list,
                    corridor_planes=corridor_planes,
                    target_pos=target_pos,
                    current_time_s=t_now,
                )
            else:
                safety_out = self.safety_box.process_command(
                    untrusted_accel=np.asarray(untrusted_accel, dtype=np.float64),
                    telemetry=self.latest_telemetry,
                    obstacles=obs_list,
                    current_time_s=t_now,
                )
            failsafe_disconnect = False

        flatness_sp = self.flatness.convert(safety_out.safe_accel, psi_des=psi_des)

        if mode == "SET_ATTITUDE_TARGET":
            frame = self.encode_set_attitude_target(flatness_sp)
            out_msg_id = MSG_ID_SET_ATTITUDE_TARGET
        elif mode == "SET_POSITION_TARGET_LOCAL_NED":
            frame = self.encode_set_position_target_local_ned(
                safety_out.safe_accel, yaw_aegis_rad=psi_des
            )
            out_msg_id = MSG_ID_SET_POSITION_TARGET_LOCAL_NED
        else:
            raise ValueError(f"Invalid output_mode: {mode!r}")

        self.sock.sendto(frame, self.remote_endpoint)

        return BridgeStepResult(
            safety_output=safety_out,
            flatness_setpoint=flatness_sp,
            outbound_frame=frame,
            outbound_msg_id=out_msg_id,
            failsafe_disconnect=failsafe_disconnect,
            messages_processed=n_rx,
        )
