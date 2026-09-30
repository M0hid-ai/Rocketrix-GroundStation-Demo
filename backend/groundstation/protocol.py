"""Binary telemetry frame shared by the flight computer (ESP32) and the ground station.

Wire format (little-endian)::

    0xAA 0x55 | LEN (u8) | PAYLOAD (LEN bytes) | CRC16-CCITT (u16, over LEN + PAYLOAD)

The same layout is meant to be implemented on the ESP32 as a packed C struct, so the simulator
exercises the exact decoding path used with real hardware. ``FrameParser`` works on an arbitrary
byte stream (e.g. from a USB serial LoRa receiver) and resynchronises after garbage or bad CRCs.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .physics import PHASES
from .sensors import Readings

SYNC = b"\xAA\x55"
MSG_TELEMETRY = 0x01

# type, seq, t_ms, state, flags, pressure, temp, ax, al, roll, tilt, lat, lon, gps_alt,
# sats, battery_mv, sensor_mask, baro_seq, imu_seq, gps_seq, temp_seq
PAYLOAD = struct.Struct("<BHIBBfhhhhHiiiBHBBBBB")
PAYLOAD_SIZE = PAYLOAD.size
FRAME_SIZE = len(SYNC) + 1 + PAYLOAD_SIZE + 2

FLAG_GPS_FIX = 1 << 0
FLAG_DROGUE_CONT = 1 << 1
FLAG_MAIN_CONT = 1 << 2
FLAG_DROGUE_FIRED = 1 << 3
FLAG_MAIN_FIRED = 1 << 4

SENSOR_BITS = {"baro": 1 << 0, "temp": 1 << 1, "imu": 1 << 2, "gps": 1 << 3, "battery": 1 << 4}


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _clamp(v: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(v))))


@dataclass
class Telemetry:
    seq: int
    t_ms: int
    state: str
    flags: int
    pressure_pa: float
    temp_c: float
    accel_axial_g: float
    accel_lateral_g: float
    roll_rate_dps: float
    tilt_deg: float
    gps_lat: float
    gps_lon: float
    gps_alt_msl: float
    gps_sats: int
    battery_v: float
    sensor_mask: int
    baro_seq: int
    imu_seq: int
    gps_seq: int
    temp_seq: int

    @property
    def gps_fix(self) -> bool:
        return bool(self.flags & FLAG_GPS_FIX)

    def sensor_on(self, name: str) -> bool:
        return bool(self.sensor_mask & SENSOR_BITS[name])


def encode(seq: int, t_ms: int, state: str, flags: int, r: Readings) -> bytes:
    mask = 0
    for name, bit in SENSOR_BITS.items():
        if r.enabled.get(name, True):
            mask |= bit
    if r.gps_fix:
        flags |= FLAG_GPS_FIX
    payload = PAYLOAD.pack(
        MSG_TELEMETRY, seq & 0xFFFF, t_ms & 0xFFFFFFFF, PHASES.index(state), flags & 0xFF,
        float(r.pressure_pa),
        _clamp(r.temp_c * 100, -32768, 32767),
        _clamp(r.accel_axial_g * 1000, -32768, 32767),
        _clamp(r.accel_lateral_g * 1000, -32768, 32767),
        _clamp(r.roll_rate_dps * 10, -32768, 32767),
        _clamp(r.tilt_deg * 100, 0, 65535),
        _clamp(r.gps_lat * 1e7, -2**31, 2**31 - 1),
        _clamp(r.gps_lon * 1e7, -2**31, 2**31 - 1),
        _clamp(r.gps_alt_msl * 100, -2**31, 2**31 - 1),
        _clamp(r.gps_sats, 0, 255),
        _clamp(r.battery_v * 1000, 0, 65535),
        mask, r.baro_seq & 0xFF, r.imu_seq & 0xFF, r.gps_seq & 0xFF, r.temp_seq & 0xFF,
    )
    body = bytes([len(payload)]) + payload
    return SYNC + body + struct.pack("<H", crc16_ccitt(body))


def decode_payload(payload: bytes) -> Telemetry | None:
    if len(payload) != PAYLOAD_SIZE or payload[0] != MSG_TELEMETRY:
        return None
    (_, seq, t_ms, state, flags, p, temp, ax, al, roll, tilt, lat, lon, galt, sats, bat, mask,
     bseq, iseq, gseq, tseq) = PAYLOAD.unpack(payload)
    return Telemetry(
        seq=seq, t_ms=t_ms, state=PHASES[state] if state < len(PHASES) else "IDLE", flags=flags,
        pressure_pa=p, temp_c=temp / 100, accel_axial_g=ax / 1000, accel_lateral_g=al / 1000,
        roll_rate_dps=roll / 10, tilt_deg=tilt / 100, gps_lat=lat / 1e7, gps_lon=lon / 1e7,
        gps_alt_msl=galt / 100, gps_sats=sats, battery_v=bat / 1000, sensor_mask=mask,
        baro_seq=bseq, imu_seq=iseq, gps_seq=gseq, temp_seq=tseq,
    )


class FrameParser:
    """Incremental parser for a byte stream containing framed telemetry."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.crc_errors = 0
        self.bytes_discarded = 0

    def feed(self, data: bytes) -> list[Telemetry]:
        self._buf.extend(data)
        out: list[Telemetry] = []
        while True:
            start = self._buf.find(SYNC)
            if start < 0:
                keep = 1 if self._buf.endswith(SYNC[:1]) else 0
                self.bytes_discarded += len(self._buf) - keep
                del self._buf[:len(self._buf) - keep]
                return out
            if start:
                self.bytes_discarded += start
                del self._buf[:start]
            if len(self._buf) < 3:
                return out
            length = self._buf[2]
            total = 3 + length + 2
            if len(self._buf) < total:
                return out
            body = bytes(self._buf[2:3 + length])
            (crc,) = struct.unpack_from("<H", self._buf, 3 + length)
            if crc != crc16_ccitt(body):
                self.crc_errors += 1
                del self._buf[:2]  # skip this sync and hunt for the next one
                continue
            del self._buf[:total]
            frame = decode_payload(body[1:])
            if frame is not None:
                out.append(frame)
