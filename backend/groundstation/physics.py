"""3-DOF point-mass flight simulation of a single-stage rocket with dual-deploy recovery.

Frame: x = east, y = north, z = up (metres above the pad). The rocket's body axis follows the
air-relative velocity once it leaves the rail (weathercocking), so wind produces realistic tilt and
drift. Parachutes are modelled as a drag area that inflates over a short time.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import atmosphere as atm
from .config import Config
from .motors import MOTOR_PRESETS, ThrustCurve

G = atm.G0

IDLE, ARMED, BOOST, COAST, DROGUE, MAIN, LANDED = (
    "IDLE", "ARMED", "BOOST", "COAST", "DROGUE", "MAIN", "LANDED")
PHASES = [IDLE, ARMED, BOOST, COAST, DROGUE, MAIN, LANDED]

Vec = tuple[float, float, float]


def _norm(v: Vec) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _scale(v: Vec, k: float) -> Vec:
    return (v[0] * k, v[1] * k, v[2] * k)


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


@dataclass
class Truth:
    """Ground-truth state exposed to the sensor models."""
    t: float = 0.0
    pos: Vec = (0.0, 0.0, 0.0)
    vel: Vec = (0.0, 0.0, 0.0)
    acc: Vec = (0.0, 0.0, 0.0)
    specific_force: Vec = (0.0, 0.0, G)
    heading: Vec = (0.0, 0.0, 1.0)
    axial_accel: float = G  # m/s^2 along the body axis, as an accelerometer would read it
    lateral_accel: float = 0.0
    tilt_deg: float = 0.0
    roll_rate_dps: float = 0.0
    mass: float = 0.0
    thrust: float = 0.0
    mach: float = 0.0
    phase: str = IDLE
    flight_time: float | None = None
    ejection_spike_pa: float = 0.0


@dataclass
class FlightEvents:
    ignition: float | None = None
    liftoff: float | None = None
    rail_exit: float | None = None
    rail_exit_speed: float | None = None
    burnout: float | None = None
    apogee: float | None = None
    apogee_alt: float | None = None
    drogue: float | None = None
    main: float | None = None
    landed: float | None = None
    max_speed: float = 0.0
    max_accel: float = 0.0
    max_mach: float = 0.0
    log: list[tuple[float, str]] = field(default_factory=list)


class FlightSim:
    def __init__(self, cfg: Config, rng: random.Random | None = None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        m = cfg.motor
        curve = MOTOR_PRESETS.get(m.preset, MOTOR_PRESETS["H128W"])["curve"]
        self.motor = ThrustCurve(m.total_impulse_ns, m.burn_time_s, curve)
        r = cfg.rocket
        self.body_cda = r.drag_coefficient * math.pi * (r.diameter_mm / 2000.0) ** 2
        self.empty_mass = r.dry_mass_kg + m.loaded_mass_kg - m.propellant_mass_kg

        env = cfg.environment
        rho0 = atm.density(env.ground_pressure_pa, env.ground_temp_c + 273.15)
        weight = self.empty_mass * G
        self.drogue_cda = 2 * weight / (rho0 * cfg.recovery.drogue_descent_mps ** 2)
        self.main_cda = 2 * weight / (rho0 * cfg.recovery.main_descent_mps ** 2)

        # rail tilted slightly into the wind, as is common practice
        into_wind = math.radians(env.wind_direction_deg)
        a = math.radians(r.launch_angle_deg)
        self.rail_dir: Vec = (math.sin(a) * math.sin(into_wind),
                              math.sin(a) * math.cos(into_wind), math.cos(a))
        self.truth = Truth(mass=r.dry_mass_kg + m.loaded_mass_kg, heading=self.rail_dir,
                           tilt_deg=r.launch_angle_deg)
        self.truth.axial_accel = G * self.rail_dir[2]
        self.events = FlightEvents()
        self._rail_s = 0.0
        self._rail_v = 0.0
        self._on_rail = True
        self._chute_cda = 0.0
        self._chute_target = 0.0
        self._chute_from = 0.0
        self._chute_t0 = 0.0
        self._chute_dur = 1.0
        self._gust = 0.0
        self._spike_until = -1.0

    # ------------------------------------------------------------------ commands
    def arm(self) -> None:
        if self.truth.phase == IDLE:
            self.truth.phase = ARMED
            self._log("Flight computer armed")

    def disarm(self) -> None:
        if self.truth.phase == ARMED:
            self.truth.phase = IDLE
            self._log("Disarmed")

    def ignite(self) -> None:
        if self.truth.phase in (IDLE, ARMED):
            self.truth.phase = BOOST
            self.events.ignition = self.truth.t
            self._log("Ignition")

    # ------------------------------------------------------------------ helpers
    def _log(self, msg: str) -> None:
        self.events.log.append((self.truth.t, msg))

    def _wind(self, z: float, dt: float) -> Vec:
        env = self.cfg.environment
        theta = 0.5  # Ornstein-Uhlenbeck gust model
        self._gust += -theta * self._gust * dt + \
            env.wind_gust_mps * math.sqrt(2 * theta * dt) * self.rng.gauss(0, 1)
        speed = max(0.0, env.wind_speed_mps * (max(z, 2.0) / 10.0) ** (1 / 7) + self._gust)
        frm = math.radians(env.wind_direction_deg)
        return (-math.sin(frm) * speed, -math.cos(frm) * speed, 0.0)

    def _deploy(self, target_cda: float, duration: float, name: str) -> None:
        self._chute_from = self._chute_cda
        self._chute_target = target_cda
        self._chute_t0 = self.truth.t
        self._chute_dur = duration
        if self.cfg.recovery.ejection_pressure_spike:
            self._spike_until = self.truth.t + 0.12
        self._log(f"{name} deployed at {self.truth.pos[2]:.0f} m")

    # ------------------------------------------------------------------ integration
    def step(self, dt: float) -> Truth:
        tr = self.truth
        ev = self.events
        tr.t += dt
        tr.ejection_spike_pa = 350.0 if tr.t < self._spike_until else 0.0

        if tr.phase in (IDLE, ARMED, LANDED):
            tr.vel = (0.0, 0.0, 0.0)
            tr.acc = (0.0, 0.0, 0.0)
            tr.specific_force = (0.0, 0.0, G)
            tr.axial_accel = _dot(tr.specific_force, tr.heading)
            tr.lateral_accel = 0.0
            tr.roll_rate_dps = 0.0
            return tr

        m = self.cfg.motor
        tb = tr.t - (ev.ignition if ev.ignition is not None else tr.t)
        thrust = self.motor.thrust(tb)
        mass = self.cfg.rocket.dry_mass_kg + m.loaded_mass_kg - \
            m.propellant_mass_kg * self.motor.impulse_fraction(tb)
        tr.thrust, tr.mass = thrust, mass

        env = self.cfg.environment
        alt_msl = env.site_elevation_m + tr.pos[2]
        temp_k = atm.temperature_k(alt_msl, env.ground_temp_c, env.site_elevation_m)
        p = atm.pressure_pa(alt_msl, env.ground_pressure_pa, env.ground_temp_c,
                            env.site_elevation_m)
        rho = atm.density(p, temp_k)
        wind = self._wind(tr.pos[2], dt)
        v_rel = _sub(tr.vel, wind)
        speed_rel = _norm(v_rel)
        tr.mach = speed_rel / atm.speed_of_sound(temp_k)

        if self._chute_target > 0:  # parachute inflation
            k = min(1.0, (tr.t - self._chute_t0) / self._chute_dur)
            self._chute_cda = self._chute_from + (self._chute_target - self._chute_from) * k

        # body orientation
        if self._on_rail:
            heading = self.rail_dir
        elif tr.phase in (DROGUE, MAIN):
            sway = math.radians(125 + 20 * math.sin(1.4 * tr.t))
            az = 0.6 * tr.t
            heading = (math.sin(sway) * math.cos(az), math.sin(sway) * math.sin(az),
                       math.cos(sway))
        elif speed_rel > 1.0:
            heading = _scale(v_rel, 1.0 / speed_rel)
        else:
            heading = tr.heading
        tr.heading = heading

        cda = self.body_cda + self._chute_cda
        drag_mag = 0.5 * rho * speed_rel * speed_rel * cda
        drag = _scale(v_rel, -drag_mag / speed_rel) if speed_rel > 1e-6 else (0.0, 0.0, 0.0)
        force = _add(_scale(heading, thrust), drag)

        if self._on_rail:
            a_along = _dot(force, self.rail_dir) / mass - G * self.rail_dir[2]
            if a_along <= 0 and self._rail_v <= 0:
                a_along, self._rail_v = 0.0, 0.0  # thrust not yet above weight
            self._rail_v += a_along * dt
            self._rail_s += self._rail_v * dt
            tr.vel = _scale(self.rail_dir, self._rail_v)
            tr.pos = _scale(self.rail_dir, self._rail_s)
            acc = _scale(self.rail_dir, a_along)
            if ev.liftoff is None and self._rail_s > 0.01:
                ev.liftoff = tr.t
                self._log("Liftoff")
            if self._rail_s >= self.cfg.rocket.rail_length_m:
                self._on_rail = False
                ev.rail_exit, ev.rail_exit_speed = tr.t, self._rail_v
                self._log(f"Rail exit at {self._rail_v:.1f} m/s")
        else:
            acc = _add(_scale(force, 1.0 / mass), (0.0, 0.0, -G))
            tr.vel = _add(tr.vel, _scale(acc, dt))
            tr.pos = _add(tr.pos, _scale(tr.vel, dt))

        tr.acc = acc
        tr.specific_force = _sub(acc, (0.0, 0.0, -G))
        tr.axial_accel = _dot(tr.specific_force, heading)
        tr.lateral_accel = _norm(_sub(tr.specific_force, _scale(heading, tr.axial_accel)))
        tr.tilt_deg = math.degrees(math.acos(max(-1.0, min(1.0, heading[2]))))
        spd = _norm(tr.vel)
        if tr.phase in (BOOST, COAST):
            tr.roll_rate_dps = min(720.0, 2.5 * spd)
        else:
            tr.roll_rate_dps = 25 * math.sin(0.3 * tr.t)
        if ev.liftoff is not None:
            tr.flight_time = tr.t - ev.liftoff
        ev.max_speed = max(ev.max_speed, spd)
        ev.max_accel = max(ev.max_accel, abs(tr.axial_accel))
        ev.max_mach = max(ev.max_mach, tr.mach)

        self._events(tb)
        return tr

    def _events(self, tb: float) -> None:
        tr, ev, rec = self.truth, self.events, self.cfg.recovery
        if tr.phase == BOOST and tb >= self.motor.burn_time:
            tr.phase = COAST
            ev.burnout = tr.t
            self._log(f"Burnout at {tr.pos[2]:.0f} m, {tr.vel[2]:.0f} m/s")
        if ev.apogee is None and ev.liftoff is not None and not self._on_rail \
                and tr.phase in (BOOST, COAST) and tr.vel[2] < 0:
            ev.apogee, ev.apogee_alt = tr.t, tr.pos[2]
            self._log(f"Apogee {tr.pos[2]:.1f} m")
        if ev.apogee is not None and tr.phase == COAST and \
                tr.t >= ev.apogee + self.cfg.recovery.apogee_delay_s:
            if rec.mode == "dual":
                tr.phase = DROGUE
                ev.drogue = tr.t
                self._deploy(self.drogue_cda, 0.6, "Drogue")
            else:
                tr.phase = MAIN
                ev.main = tr.t
                self._deploy(self.main_cda, 1.2, "Main")
        if tr.phase == DROGUE and tr.pos[2] <= rec.main_deploy_alt_m:
            tr.phase = MAIN
            ev.main = tr.t
            self._deploy(self.main_cda, 1.2, "Main")
        if ev.liftoff is not None and not self._on_rail and tr.pos[2] <= 0 and tr.vel[2] < 0:
            impact = tr.vel[2]
            tr.pos = (tr.pos[0], tr.pos[1], 0.0)
            tr.phase = LANDED
            ev.landed = tr.t
            tr.flight_time = ev.landed - ev.liftoff
            self._log(f"Landed at {abs(impact):.1f} m/s, "
                      f"{math.hypot(tr.pos[0], tr.pos[1]):.0f} m from pad")
