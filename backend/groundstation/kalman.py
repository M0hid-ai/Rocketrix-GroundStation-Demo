"""Constant-acceleration Kalman filter for altitude, vertical velocity and vertical acceleration.

State x = [h, v, a]. The process model assumes white jerk; measurements are scalar (barometric
altitude and/or vertical acceleration from the IMU), so every update is a cheap scalar update with
no matrix inversion - small enough to port straight to the ESP32 or Raspberry Pi.
"""

from __future__ import annotations

import math

Mat = list[list[float]]


def _matmul(a: Mat, b: Mat) -> Mat:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _transpose(a: Mat) -> Mat:
    return [[a[j][i] for j in range(3)] for i in range(3)]


class AltitudeKalman:
    def __init__(self, jerk_psd: float = 40.0, baro_sigma: float = 0.6, accel_sigma: float = 0.8,
                 gate_sigma: float = 5.0):
        self.q = jerk_psd
        self.r_baro = baro_sigma ** 2
        self.r_accel = accel_sigma ** 2
        self.gate = gate_sigma
        self.reset()

    def reset(self, h: float = 0.0) -> None:
        self.x = [h, 0.0, 0.0]
        self.P: Mat = [[10.0, 0, 0], [0, 10.0, 0], [0, 0, 10.0]]
        self.t: float | None = None
        self.rejected = 0
        self._consecutive_rejects = [0, 0, 0]  # per measured state component
        self.last_innovation = 0.0

    def tune(self, jerk_psd: float, baro_sigma: float, accel_sigma: float, gate: float) -> None:
        self.q, self.r_baro, self.r_accel, self.gate = jerk_psd, baro_sigma ** 2, \
            accel_sigma ** 2, gate

    def predict_to(self, t: float, q_scale: float = 1.0) -> None:
        if self.t is None:
            self.t = t
            return
        dt = t - self.t
        if dt <= 0:
            return
        self.t = t
        h, v, a = self.x
        self.x = [h + v * dt + 0.5 * a * dt * dt, v + a * dt, a]
        F = [[1, dt, 0.5 * dt * dt], [0, 1, dt], [0, 0, 1]]
        q = self.q * q_scale
        d2, d3, d4, d5 = dt ** 2, dt ** 3, dt ** 4, dt ** 5
        Q = [[q * d5 / 20, q * d4 / 8, q * d3 / 6],
             [q * d4 / 8, q * d3 / 3, q * d2 / 2],
             [q * d3 / 6, q * d2 / 2, q * dt]]
        FP = _matmul(F, self.P)
        FPFt = _matmul(FP, _transpose(F))
        self.P = [[FPFt[i][j] + Q[i][j] for j in range(3)] for i in range(3)]

    def _update(self, idx: int, z: float, r: float) -> bool:
        """Scalar update of state component ``idx``. Returns False if gated out as an outlier."""
        y = z - self.x[idx]
        s = self.P[idx][idx] + r
        self.last_innovation = y
        if self.gate > 0 and abs(y) > self.gate * math.sqrt(s):
            self.rejected += 1
            self._consecutive_rejects[idx] += 1
            if self._consecutive_rejects[idx] < 5:
                return False
            # persistent disagreement means the filter, not the sensor, is wrong: accept
        self._consecutive_rejects[idx] = 0
        k = [self.P[i][idx] / s for i in range(3)]
        self.x = [self.x[i] + k[i] * y for i in range(3)]
        row = self.P[idx][:]
        self.P = [[self.P[i][j] - k[i] * row[j] for j in range(3)] for i in range(3)]
        return True

    def update_altitude(self, h: float) -> bool:
        return self._update(0, h, self.r_baro)

    def update_acceleration(self, a: float) -> bool:
        return self._update(2, a, self.r_accel)

    @property
    def altitude(self) -> float:
        return self.x[0]

    @property
    def velocity(self) -> float:
        return self.x[1]

    @property
    def acceleration(self) -> float:
        return self.x[2]
