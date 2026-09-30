"""International Standard Atmosphere (troposphere) helpers."""

from __future__ import annotations

import math

G0 = 9.80665  # m/s^2
R_AIR = 287.05  # J/(kg*K)
LAPSE = 0.0065  # K/m
EXP = G0 / (R_AIR * LAPSE)  # ~5.2559


def temperature_k(alt_msl_m: float, ground_temp_c: float, site_elev_m: float) -> float:
    """Air temperature at an MSL altitude, anchored to the measured ground temperature."""
    return ground_temp_c + 273.15 - LAPSE * (alt_msl_m - site_elev_m)


def pressure_pa(alt_msl_m: float, ground_pressure_pa: float, ground_temp_c: float,
                site_elev_m: float) -> float:
    """Pressure at an MSL altitude, anchored to the pressure/temperature measured at the pad."""
    t0 = ground_temp_c + 273.15
    t = temperature_k(alt_msl_m, ground_temp_c, site_elev_m)
    return ground_pressure_pa * (t / t0) ** EXP


def density(pressure: float, temp_k: float) -> float:
    return pressure / (R_AIR * temp_k)


def pressure_to_altitude(pressure: float, ref_pressure: float, ref_temp_c: float = 15.0) -> float:
    """Height above the reference-pressure level (hypsometric / barometric formula)."""
    if pressure <= 0 or ref_pressure <= 0:
        return 0.0
    t0 = ref_temp_c + 273.15
    return (t0 / LAPSE) * (1.0 - (pressure / ref_pressure) ** (1.0 / EXP))


def speed_of_sound(temp_k: float) -> float:
    return math.sqrt(1.4 * R_AIR * temp_k)
