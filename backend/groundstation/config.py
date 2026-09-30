"""Runtime-adjustable configuration.

Everything here can be changed while the ground station runs (PATCH /api/config). Rocket, motor,
recovery and environment changes take effect on the next launch; sensor, radio-link and Kalman
settings apply immediately.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .motors import MOTOR_PRESETS


class RocketConfig(BaseModel):
    name: str = "Level 1 Demo"
    dry_mass_kg: float = Field(1.15, ge=0.1, le=20, description="Airframe mass without motor")
    diameter_mm: float = Field(66.0, ge=20, le=200)
    drag_coefficient: float = Field(0.55, ge=0.1, le=2.0)
    rail_length_m: float = Field(1.8, ge=0.5, le=6)
    launch_angle_deg: float = Field(3.0, ge=0, le=20, description="Rail tilt from vertical")


class MotorConfig(BaseModel):
    preset: str = "H128W"
    total_impulse_ns: float = Field(176.0, ge=10, le=2560)
    burn_time_s: float = Field(1.4, ge=0.1, le=10)
    loaded_mass_kg: float = Field(0.207, ge=0.01, le=5)
    propellant_mass_kg: float = Field(0.094, ge=0.005, le=3)


class RecoveryConfig(BaseModel):
    mode: Literal["dual", "single"] = "dual"
    apogee_delay_s: float = Field(1.0, ge=0, le=10, description="Delay after apogee before drogue")
    drogue_descent_mps: float = Field(22.0, ge=5, le=50)
    main_descent_mps: float = Field(6.0, ge=2, le=15)
    main_deploy_alt_m: float = Field(150.0, ge=50, le=800)
    ejection_pressure_spike: bool = Field(True, description="Simulate charge pressure spikes on baro")


class EnvironmentConfig(BaseModel):
    site_elevation_m: float = Field(600.0, ge=-100, le=4000)
    ground_pressure_pa: float = Field(94_500.0, ge=60_000, le=108_000)
    ground_temp_c: float = Field(24.0, ge=-30, le=55)
    wind_speed_mps: float = Field(4.0, ge=0, le=15)
    wind_direction_deg: float = Field(270.0, ge=0, lt=360, description="Direction wind blows FROM")
    wind_gust_mps: float = Field(1.5, ge=0, le=10)
    launch_lat: float = 35.3472
    launch_lon: float = -117.8086


class BaroSensor(BaseModel):
    enabled: bool = True
    model: str = "BMP388"
    rate_hz: float = Field(50, ge=1, le=200)
    noise_pa: float = Field(4.0, ge=0, le=100)


class TempSensor(BaseModel):
    enabled: bool = True
    model: str = "BMP388 (die temp)"
    rate_hz: float = Field(5, ge=0.2, le=50)
    noise_c: float = Field(0.08, ge=0, le=5)
    time_constant_s: float = Field(12.0, ge=0.1, le=120, description="Thermal lag of the sensor")


class ImuSensor(BaseModel):
    enabled: bool = True
    model: str = "MPU6050"
    rate_hz: float = Field(100, ge=1, le=1000)
    noise_g: float = Field(0.03, ge=0, le=1)
    range_g: float = Field(16.0, ge=2, le=200)
    gyro_noise_dps: float = Field(0.5, ge=0, le=20)


class GpsSensor(BaseModel):
    enabled: bool = True
    model: str = "u-blox NEO-M8N"
    rate_hz: float = Field(5, ge=0.2, le=25)
    horizontal_noise_m: float = Field(2.5, ge=0, le=50)
    vertical_noise_m: float = Field(5.0, ge=0, le=100)


class BatterySensor(BaseModel):
    enabled: bool = True
    rate_hz: float = Field(1, ge=0.1, le=20)
    full_voltage: float = Field(8.3, ge=3, le=13)
    drain_mv_per_min: float = Field(15.0, ge=0, le=500)


class SensorsConfig(BaseModel):
    baro: BaroSensor = BaroSensor()
    temp: TempSensor = TempSensor()
    imu: ImuSensor = ImuSensor()
    gps: GpsSensor = GpsSensor()
    battery: BatterySensor = BatterySensor()


class LinkConfig(BaseModel):
    """ESP32 + LoRa downlink model."""
    tx_rate_hz: float = Field(20, ge=1, le=100, description="Telemetry frames per second")
    frequency_mhz: float = Field(433.0, ge=137, le=1020)
    tx_power_dbm: float = Field(17.0, ge=0, le=30)
    spreading_factor: int = Field(7, ge=6, le=12)
    bandwidth_khz: float = Field(500.0, ge=7.8, le=500)
    coding_rate: int = Field(5, ge=5, le=8, description="4/x")
    enforce_airtime: bool = Field(True, description="Drop frames the radio has no time to send")
    packet_loss_pct: float = Field(2.0, ge=0, le=90)
    corruption_pct: float = Field(0.5, ge=0, le=50)
    base_latency_ms: float = Field(4.0, ge=0, le=2000, description="Serial/USB/processing delay")
    jitter_ms: float = Field(3.0, ge=0, le=1000)


class KalmanConfig(BaseModel):
    enabled: bool = True
    process_jerk_noise: float = Field(40.0, ge=0.01, le=5000, description="Jerk PSD (m^2/s^5)")
    baro_noise_m: float = Field(0.6, ge=0.01, le=50)
    accel_noise_mps2: float = Field(0.8, ge=0.01, le=50)
    use_accelerometer: bool = True
    outlier_gate_sigma: float = Field(5.0, ge=0, le=50, description="0 disables innovation gating")


class SimConfig(BaseModel):
    time_scale: float = Field(1.0, ge=0.1, le=10)
    countdown_s: float = Field(5.0, ge=0, le=60)
    seed: int | None = None


class Config(BaseModel):
    rocket: RocketConfig = RocketConfig()
    motor: MotorConfig = MotorConfig()
    recovery: RecoveryConfig = RecoveryConfig()
    environment: EnvironmentConfig = EnvironmentConfig()
    sensors: SensorsConfig = SensorsConfig()
    link: LinkConfig = LinkConfig()
    kalman: KalmanConfig = KalmanConfig()
    sim: SimConfig = SimConfig()


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def apply_patch(cfg: Config, patch: dict[str, Any]) -> Config:
    """Validate and apply a partial update. Picking a motor preset fills in its numbers."""
    motor_patch = patch.get("motor") or {}
    preset = motor_patch.get("preset")
    if preset and preset in MOTOR_PRESETS and len(motor_patch) == 1:
        p = MOTOR_PRESETS[preset]
        patch = deep_merge(patch, {"motor": {
            k: p[k] for k in ("total_impulse_ns", "burn_time_s", "loaded_mass_kg",
                              "propellant_mass_kg")}})
    return Config.model_validate(deep_merge(cfg.model_dump(), patch))
