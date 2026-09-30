"""Sensor models for the simulated flight computer (ESP32).

Each sensor samples at its own configurable rate and adds realistic imperfections: white noise,
range clipping, thermal lag, GPS loss of lock under high acceleration, battery sag during pyro
firing, and ejection-charge pressure spikes on the barometer.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import atmosphere as atm
from .config import Config
from .physics import Truth


@dataclass
class _Clock:
    next_t: float = 0.0
    seq: int = 0

    def due(self, t: float, rate_hz: float) -> bool:
        if t + 1e-9 < self.next_t:
            return False
        period = 1.0 / rate_hz
        # schedule from the previous slot, but never fall behind by more than one period
        self.next_t = max(self.next_t + period, t)
        self.seq = (self.seq + 1) & 0xFF
        return True


@dataclass
class Readings:
    """Latest value from every sensor, as held in the flight computer's memory."""
    pressure_pa: float = 0.0
    baro_seq: int = 0
    temp_c: float = 0.0
    temp_seq: int = 0
    accel_axial_g: float = 1.0
    accel_lateral_g: float = 0.0
    roll_rate_dps: float = 0.0
    tilt_deg: float = 0.0
    imu_seq: int = 0
    gps_lat: float = 0.0
    gps_lon: float = 0.0
    gps_alt_msl: float = 0.0
    gps_sats: int = 0
    gps_fix: bool = False
    gps_seq: int = 0
    battery_v: float = 0.0
    battery_seq: int = 0
    enabled: dict[str, bool] = field(default_factory=dict)


class SensorSuite:
    def __init__(self, cfg: Config, rng: random.Random | None = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.clocks = {name: _Clock() for name in ("baro", "temp", "imu", "gps", "battery")}
        self.r = Readings()
        env = cfg.environment
        self._sensor_temp = env.ground_temp_c + 1.5  # electronics bay runs slightly warm
        self._gps_bias = [0.0, 0.0, 0.0]
        self._gps_sats = 11
        self._gps_lock_lost_until = -1.0
        self._start_t: float | None = None

    def update(self, truth: Truth, dt: float) -> Readings:
        cfg, s, r, g = self.cfg, self.cfg.sensors, self.r, self.rng
        env = cfg.environment
        t = truth.t
        if self._start_t is None:
            self._start_t = t
        alt_msl = env.site_elevation_m + truth.pos[2]
        ambient_c = atm.temperature_k(alt_msl, env.ground_temp_c, env.site_elevation_m) - 273.15
        # sensor die temperature follows ambient with a first-order lag
        tau = max(s.temp.time_constant_s, 1e-3)
        self._sensor_temp += (ambient_c + 1.5 - self._sensor_temp) * min(1.0, dt / tau)

        r.enabled = {"baro": s.baro.enabled, "temp": s.temp.enabled, "imu": s.imu.enabled,
                     "gps": s.gps.enabled, "battery": s.battery.enabled}

        if s.baro.enabled and self.clocks["baro"].due(t, s.baro.rate_hz):
            p = atm.pressure_pa(alt_msl, env.ground_pressure_pa, env.ground_temp_c,
                                env.site_elevation_m)
            r.pressure_pa = p + truth.ejection_spike_pa + g.gauss(0, s.baro.noise_pa)
            r.baro_seq = self.clocks["baro"].seq

        if s.temp.enabled and self.clocks["temp"].due(t, s.temp.rate_hz):
            r.temp_c = self._sensor_temp + g.gauss(0, s.temp.noise_c)
            r.temp_seq = self.clocks["temp"].seq

        if s.imu.enabled and self.clocks["imu"].due(t, s.imu.rate_hz):
            lim = s.imu.range_g
            ax = truth.axial_accel / atm.G0 + g.gauss(0, s.imu.noise_g)
            al = truth.lateral_accel / atm.G0 + g.gauss(0, s.imu.noise_g)
            r.accel_axial_g = max(-lim, min(lim, ax))
            r.accel_lateral_g = max(-lim, min(lim, al))
            r.roll_rate_dps = truth.roll_rate_dps + g.gauss(0, s.imu.gyro_noise_dps)
            r.tilt_deg = max(0.0, truth.tilt_deg + g.gauss(0, 0.3))
            r.imu_seq = self.clocks["imu"].seq

        if s.gps.enabled and self.clocks["gps"].due(t, s.gps.rate_hz):
            # u-blox receivers in default dynamic models lose lock above ~4 g
            if abs(truth.axial_accel) > 4 * atm.G0:
                self._gps_lock_lost_until = t + 2.5
            r.gps_fix = t >= self._gps_lock_lost_until
            self._gps_sats = max(4, min(16, self._gps_sats + g.choice((-1, 0, 0, 0, 0, 1))))
            r.gps_sats = self._gps_sats if r.gps_fix else max(0, self._gps_sats - 7)
            if r.gps_fix:
                for i in range(3):  # slowly wandering bias + white noise
                    self._gps_bias[i] = 0.98 * self._gps_bias[i] + g.gauss(0, 0.3)
                hn, vn = s.gps.horizontal_noise_m, s.gps.vertical_noise_m
                east = truth.pos[0] + self._gps_bias[0] + g.gauss(0, hn)
                north = truth.pos[1] + self._gps_bias[1] + g.gauss(0, hn)
                lat0 = env.launch_lat
                r.gps_lat = lat0 + north / 111_320.0
                r.gps_lon = env.launch_lon + east / (111_320.0 * math.cos(math.radians(lat0)))
                r.gps_alt_msl = alt_msl + self._gps_bias[2] + g.gauss(0, vn)
            r.gps_seq = self.clocks["gps"].seq

        if s.battery.enabled and self.clocks["battery"].due(t, s.battery.rate_hz):
            minutes = (t - self._start_t) / 60.0
            sag = 0.6 if truth.ejection_spike_pa > 0 else 0.0  # pyro channel current draw
            r.battery_v = s.battery.full_voltage - s.battery.drain_mv_per_min * minutes / 1000.0 \
                - sag + g.gauss(0, 0.01)
            r.battery_seq = self.clocks["battery"].seq

        return r
