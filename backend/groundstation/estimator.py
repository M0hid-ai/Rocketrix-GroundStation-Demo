"""Ground-side processing of decoded frames: pad calibration, Kalman fusion, derived values.

This is what runs on the Raspberry Pi for both the simulator and real hardware - it only ever sees
decoded ``Telemetry`` frames, never simulator truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import atmosphere as atm
from .config import KalmanConfig
from .kalman import AltitudeKalman
from .protocol import Telemetry

PAD_STATES = ("IDLE", "ARMED")
POWERED = ("BOOST", "COAST")


@dataclass
class Estimate:
    t: float
    alt_baro: float | None
    alt: float
    vel: float
    acc: float
    alt_gps: float | None
    east: float | None
    north: float | None
    range_m: float | None


class Estimator:
    def __init__(self, cfg: KalmanConfig):
        self.cfg = cfg
        self.kf = AltitudeKalman()
        self.tune(cfg)
        self.reset()

    def tune(self, cfg: KalmanConfig) -> None:
        self.cfg = cfg
        self.kf.tune(cfg.process_jerk_noise, cfg.baro_noise_m, cfg.accel_noise_mps2,
                     cfg.outlier_gate_sigma)

    def reset(self) -> None:
        self.kf.reset()
        self.ref_pressure: float | None = None
        self.ref_temp: float | None = None
        self.ref_gps: tuple[float, float, float] | None = None
        self._last_baro_seq: int | None = None
        self._last_imu_seq: int | None = None
        self._last_gps_seq: int | None = None
        self._prev_alt: float | None = None
        self._prev_t: float | None = None
        self._raw_vel = 0.0
        self.alt_baro: float | None = None
        self.alt_gps: float | None = None
        self.east: float | None = None
        self.north: float | None = None

    def process(self, f: Telemetry) -> Estimate:
        t = f.t_ms / 1000.0
        on_pad = f.state in PAD_STATES
        new_baro = f.sensor_on("baro") and f.baro_seq != self._last_baro_seq
        new_imu = f.sensor_on("imu") and f.imu_seq != self._last_imu_seq
        new_gps = f.sensor_on("gps") and f.gps_seq != self._last_gps_seq and f.gps_fix
        self._last_baro_seq, self._last_imu_seq = f.baro_seq, f.imu_seq

        # --- pad calibration: slow average of pressure/temperature/GPS while sitting on the pad
        if on_pad:
            if new_baro and f.pressure_pa > 0:
                self.ref_pressure = f.pressure_pa if self.ref_pressure is None else \
                    0.98 * self.ref_pressure + 0.02 * f.pressure_pa
            if f.sensor_on("temp"):
                self.ref_temp = f.temp_c if self.ref_temp is None else \
                    0.95 * self.ref_temp + 0.05 * f.temp_c
            if new_gps:
                cur = (f.gps_lat, f.gps_lon, f.gps_alt_msl)
                self.ref_gps = cur if self.ref_gps is None else tuple(
                    0.9 * a + 0.1 * b for a, b in zip(self.ref_gps, cur))

        if new_baro and self.ref_pressure:
            self.alt_baro = atm.pressure_to_altitude(f.pressure_pa, self.ref_pressure,
                                                     self.ref_temp if self.ref_temp else 15.0)

        # --- Kalman fusion
        # thrust changes abruptly: let the model adapt much faster while the motor burns
        self.kf.predict_to(t, q_scale=200.0 if f.state == "BOOST" else 1.0)
        if self.cfg.enabled:
            if new_baro and self.alt_baro is not None:
                self.kf.update_altitude(self.alt_baro)
            if new_imu and self.cfg.use_accelerometer and f.state in POWERED:
                # only trust axial accel as vertical while the rocket is near-vertical
                a_vert = f.accel_axial_g * math.cos(math.radians(f.tilt_deg)) * atm.G0 - atm.G0
                self.kf.update_acceleration(a_vert)
            if on_pad:  # rocket is known to be stationary
                self.kf.x[1] *= 0.5
                self.kf.x[2] *= 0.5
            alt, vel, acc = self.kf.altitude, self.kf.velocity, self.kf.acceleration
        else:
            alt = self.alt_baro or 0.0
            if new_baro and self._prev_t is not None and t > self._prev_t:
                raw = (alt - (self._prev_alt or 0.0)) / (t - self._prev_t)
                self._raw_vel = raw
            if new_baro:
                self._prev_alt, self._prev_t = alt, t
            vel = self._raw_vel
            acc = (f.accel_axial_g - 1.0) * atm.G0 if f.state in POWERED else 0.0

        # --- GPS relative position
        if new_gps:
            self._last_gps_seq = f.gps_seq
            if self.ref_gps:
                lat0, lon0, alt0 = self.ref_gps
                self.north = (f.gps_lat - lat0) * 111_320.0
                self.east = (f.gps_lon - lon0) * 111_320.0 * math.cos(math.radians(lat0))
                self.alt_gps = f.gps_alt_msl - alt0

        rng = None
        if self.east is not None and self.north is not None:
            rng = math.sqrt(self.east ** 2 + self.north ** 2 + max(alt, 0) ** 2)
        return Estimate(t=t, alt_baro=self.alt_baro, alt=alt, vel=vel, acc=acc,
                        alt_gps=self.alt_gps, east=self.east, north=self.north, range_m=rng)
