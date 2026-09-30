"""Motor thrust curves.

The presets are APPROXIMATE shapes scaled to published-ish total impulse and burn time. Replace them
with real data from thrustcurve.org (.eng files) once the team picks a motor.
"""

from __future__ import annotations

from bisect import bisect_right

# name -> (total impulse Ns, burn time s, loaded mass kg, propellant mass kg, normalised curve)
# Curve points are (fraction of burn time, relative thrust); they are rescaled so the integral
# matches the total impulse.
MOTOR_PRESETS: dict[str, dict] = {
    "H128W": {
        "total_impulse_ns": 176.0, "burn_time_s": 1.4, "loaded_mass_kg": 0.207,
        "propellant_mass_kg": 0.094,
        "curve": [(0.0, 0.0), (0.03, 1.35), (0.2, 1.25), (0.6, 1.0), (0.9, 0.65), (1.0, 0.0)],
    },
    "H238T": {
        "total_impulse_ns": 192.0, "burn_time_s": 0.8, "loaded_mass_kg": 0.213,
        "propellant_mass_kg": 0.103,
        "curve": [(0.0, 0.0), (0.04, 1.1), (0.5, 1.15), (0.85, 1.0), (1.0, 0.0)],
    },
    "H169W": {
        "total_impulse_ns": 220.0, "burn_time_s": 1.3, "loaded_mass_kg": 0.260,
        "propellant_mass_kg": 0.122,
        "curve": [(0.0, 0.0), (0.05, 1.3), (0.3, 1.15), (0.7, 0.95), (0.92, 0.6), (1.0, 0.0)],
    },
    "I200W": {
        "total_impulse_ns": 330.0, "burn_time_s": 1.65, "loaded_mass_kg": 0.365,
        "propellant_mass_kg": 0.180,
        "curve": [(0.0, 0.0), (0.04, 1.2), (0.4, 1.1), (0.8, 0.9), (0.95, 0.5), (1.0, 0.0)],
    },
}


class ThrustCurve:
    def __init__(self, total_impulse_ns: float, burn_time_s: float, curve: list[tuple[float, float]]):
        self.burn_time = max(burn_time_s, 1e-3)
        self._t = [p[0] * self.burn_time for p in curve]
        raw = [p[1] for p in curve]
        # trapezoidal integral of the unscaled curve
        area = sum((self._t[i + 1] - self._t[i]) * (raw[i] + raw[i + 1]) / 2
                   for i in range(len(raw) - 1))
        scale = total_impulse_ns / area if area > 0 else 0.0
        self._f = [r * scale for r in raw]
        self.total_impulse = total_impulse_ns

    def thrust(self, t: float) -> float:
        if t <= 0 or t >= self.burn_time:
            return 0.0
        i = bisect_right(self._t, t) - 1
        t0, t1 = self._t[i], self._t[i + 1]
        f0, f1 = self._f[i], self._f[i + 1]
        return f0 + (f1 - f0) * (t - t0) / (t1 - t0)

    def impulse_fraction(self, t: float) -> float:
        """Fraction of total impulse delivered by time t (used for propellant mass burn-off)."""
        if t <= 0:
            return 0.0
        if t >= self.burn_time:
            return 1.0
        total = 0.0
        for i in range(len(self._t) - 1):
            a, b = self._t[i], min(self._t[i + 1], t)
            if b <= a:
                break
            fa = self._f[i]
            fb = self.thrust(b) if b < self._t[i + 1] else self._f[i + 1]
            total += (b - a) * (fa + fb) / 2
        return min(total / self.total_impulse, 1.0) if self.total_impulse else 1.0
