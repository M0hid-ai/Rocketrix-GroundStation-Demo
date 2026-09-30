"""Real-time engine: runs the simulated rocket + radio link, decodes frames, fuses and broadcasts.

Latency matters, so each decoded frame is pushed to every WebSocket client the moment it arrives
(no batching). The loop wakes every ~2 ms; slow clients get their oldest messages dropped instead
of delaying everyone else.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from collections import deque
from pathlib import Path
from typing import Any

from .config import Config, apply_patch
from .estimator import Estimator
from .link import LoRaLink
from .motors import MOTOR_PRESETS
from .physics import ARMED, BOOST, IDLE, LANDED, FlightSim
from .protocol import FRAME_SIZE, FrameParser, Telemetry, encode
from .recorder import FlightRecorder
from .sensors import SensorSuite

PHYSICS_DT = 0.001
LOOP_SLEEP = 0.002
STATUS_PERIOD = 0.25
HISTORY_SECONDS = 90
GROUND_STATION_OFFSET = (60.0, -40.0)  # where the ground station sits relative to the pad (m)


def _r(v: float | None, nd: int = 2) -> float | None:
    return None if v is None else round(v, nd)


class GroundStation:
    def __init__(self, data_dir: Path):
        self.cfg = Config()
        self.recorder = FlightRecorder(data_dir)
        self.clients: set[asyncio.Queue[str]] = set()
        self.history: deque[str] = deque()
        self.pending_config = False
        self.last_flight: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None
        self.new_session()

    # ------------------------------------------------------------------ session lifecycle
    def new_session(self) -> None:
        seed = self.cfg.sim.seed
        self.rng = random.Random(seed)
        self.sim = FlightSim(self.cfg, self.rng)
        self.sensors = SensorSuite(self.cfg, self.rng)
        self.link = LoRaLink(self.cfg.link, self.rng)
        self.parser = FrameParser()
        self.estimator = Estimator(self.cfg.kalman)
        self.recorder.cancel()
        self.history.clear()
        self.tx_seq = 0
        self.next_tx = 0.0
        self.countdown_end: float | None = None
        self.last_rx_seq: int | None = None
        self.seq_gaps = 0
        self.rx_count = 0
        self.rx_times: deque[float] = deque()
        self.last_rx_wall: float | None = None
        self.t_zero: float | None = None  # frame time of first BOOST frame
        self.ground_state = IDLE
        self.landed_at: float | None = None
        self._sim_log_sent = 0
        self._accum = 0.0
        self.pending_config = False

    # ------------------------------------------------------------------ clients
    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1024)
        self.clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self.clients.discard(q)

    def broadcast(self, msg: dict[str, Any], keep: bool = False) -> None:
        text = json.dumps(msg, separators=(",", ":"))
        if keep:
            self.history.append(text)
        for q in self.clients:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(text)

    def event(self, text: str, level: str = "info", source: str = "ground") -> None:
        tp = None
        if self.t_zero is not None and self.estimator.kf.t is not None:
            tp = round(self.estimator.kf.t - self.t_zero, 2)
        self.broadcast({"type": "event", "text": text, "level": level, "source": source,
                        "tp": tp, "ts": time.time() * 1000}, keep=True)

    # ------------------------------------------------------------------ commands
    def command(self, action: str) -> dict[str, Any]:
        phase = self.sim.truth.phase
        if action == "arm":
            if phase != IDLE:
                return {"ok": False, "error": f"cannot arm in {phase}"}
            self.sim.arm()
            self.recorder.start()
            self.event("Flight computer ARMED", "warn")
        elif action == "disarm":
            if phase != ARMED or self.countdown_end is not None:
                return {"ok": False, "error": "not armed or countdown running"}
            self.sim.disarm()
            self.recorder.cancel()
            self.event("Disarmed")
        elif action == "launch":
            if phase not in (IDLE, ARMED) or self.countdown_end is not None:
                return {"ok": False, "error": f"cannot launch in {phase}"}
            if phase == IDLE:
                self.command("arm")
            self.countdown_end = self.sim.truth.t + self.cfg.sim.countdown_s
            self.event(f"Launch sequence started: T-{self.cfg.sim.countdown_s:.0f} s", "warn")
        elif action == "abort":
            if self.countdown_end is None:
                return {"ok": False, "error": "no countdown to abort"}
            self.countdown_end = None
            self.event("Countdown ABORTED", "error")
        elif action == "reset":
            if phase not in (IDLE, ARMED, LANDED):
                return {"ok": False, "error": "rocket is in flight"}
            self.new_session()
            self.broadcast({"type": "reset"})
            self.event("New session - simulator reset")
        else:
            return {"ok": False, "error": f"unknown action {action!r}"}
        self.broadcast(self.status())
        return {"ok": True}

    def update_config(self, patch: dict[str, Any]) -> Config:
        self.cfg = apply_patch(self.cfg, patch)
        # live-applied parts
        self.sensors.cfg = self.cfg
        self.link.cfg = self.cfg.link
        self.estimator.tune(self.cfg.kalman)
        if self.sim.truth.phase == IDLE and self.countdown_end is None:
            t = self.sim.truth.t  # keep the flight computer clock running
            self.sim = FlightSim(self.cfg, self.rng)
            self.sim.truth.t = t
            self._sim_log_sent = 0
            self.pending_config = False
        elif self.sim.truth.phase != IDLE:
            self.pending_config = True  # rocket/motor/recovery apply after reset
        self.broadcast({"type": "config", "config": self.config_payload()})
        return self.cfg

    def config_payload(self) -> dict[str, Any]:
        return {"values": self.cfg.model_dump(), "motor_presets": list(MOTOR_PRESETS),
                "schema": Config.model_json_schema(), "pending": self.pending_config}

    # ------------------------------------------------------------------ main loop
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        last = time.perf_counter()
        next_status = last
        while True:
            now = time.perf_counter()
            real_dt = min(now - last, 0.1)
            last = now
            self._advance(real_dt * self.cfg.sim.time_scale, now)
            for d in self.link.poll(now):
                for frame in self.parser.feed(d.data):
                    self._on_frame(frame, d.rssi_dbm, d.snr_db, d.latency_ms, now)
            self._emit_sim_log()
            if now >= next_status:
                next_status = now + STATUS_PERIOD
                self._check_landing(now)
                self.broadcast(self.status())
            await asyncio.sleep(LOOP_SLEEP)

    def _advance(self, sim_dt: float, now: float) -> None:
        self._accum += sim_dt
        while self._accum >= PHYSICS_DT:
            self._accum -= PHYSICS_DT
            truth = self.sim.step(PHYSICS_DT)
            readings = self.sensors.update(truth, PHYSICS_DT)
            if self.countdown_end is not None and truth.t >= self.countdown_end:
                self.countdown_end = None
                self.sim.ignite()
            if truth.t >= self.next_tx:
                period = 1.0 / self.cfg.link.tx_rate_hz
                self.next_tx = max(self.next_tx + period, truth.t)
                self.tx_seq = (self.tx_seq + 1) & 0xFFFF
                frame = encode(self.tx_seq, int(truth.t * 1000), truth.phase, 0, readings)
                gx, gy = GROUND_STATION_OFFSET
                dist = math.dist((truth.pos[0], truth.pos[1], truth.pos[2]), (gx, gy, 0.0))
                self.link.transmit(frame, truth.t, now, dist)

    def _on_frame(self, f: Telemetry, rssi: float, snr: float, latency_ms: float,
                  now: float) -> None:
        if self.last_rx_seq is not None:
            gap = (f.seq - self.last_rx_seq - 1) & 0xFFFF
            if gap < 1000:
                self.seq_gaps += gap
        self.last_rx_seq = f.seq
        self.rx_count += 1
        self.rx_times.append(now)
        self.last_rx_wall = now

        est = self.estimator.process(f)
        if f.state != self.ground_state:
            self._on_state_change(self.ground_state, f.state, est.t, est.alt)
        tp = None if self.t_zero is None else round(est.t - self.t_zero, 3)
        truth = self.sim.truth
        msg = {
            "type": "tm", "seq": f.seq, "t": round(est.t, 3), "tp": tp, "st": f.state,
            "p": _r(f.pressure_pa, 1), "tc": _r(f.temp_c), "ab": _r(est.alt_baro),
            "h": _r(est.alt), "v": _r(est.vel), "a": _r(est.acc),
            "ax": _r(f.accel_axial_g, 3), "al": _r(f.accel_lateral_g, 3),
            "rr": _r(f.roll_rate_dps, 1), "tl": _r(f.tilt_deg, 1), "gf": f.gps_fix,
            "lat": _r(f.gps_lat, 7), "lon": _r(f.gps_lon, 7), "hg": _r(est.alt_gps),
            "e": _r(est.east, 1), "n": _r(est.north, 1), "rng": _r(est.range_m, 1),
            "sat": f.gps_sats, "bat": _r(f.battery_v, 3), "rssi": _r(rssi, 1),
            "snr": _r(snr, 1), "lk": _r(latency_ms, 1), "ts": round(time.time() * 1000, 1),
            # simulator ground truth, only so the UI can show estimator error in SIM mode
            "th": _r(truth.pos[2]), "tv": _r(truth.vel[2]),
        }
        self.broadcast(msg, keep=True)
        self._trim_history()
        self.recorder.add(msg)

    def _on_state_change(self, old: str, new: str, t: float, alt: float) -> None:
        self.ground_state = new
        if new == BOOST and self.t_zero is None:
            self.t_zero = t
        if new == LANDED:
            self.landed_at = time.perf_counter()
        level = {"BOOST": "warn", "DROGUE": "success", "MAIN": "success",
                 "LANDED": "success"}.get(new, "info")
        self.event(f"{old} → {new} at {alt:.0f} m", level)

    def _check_landing(self, now: float) -> None:
        if self.landed_at is not None and now - self.landed_at > 2.0 and self.recorder.active:
            ev = self.sim.events
            truth = {"apogee_m": _r(ev.apogee_alt), "max_speed_mps": _r(ev.max_speed),
                     "max_accel_g": _r(ev.max_accel / 9.80665), "max_mach": _r(ev.max_mach, 3),
                     "rail_exit_mps": _r(ev.rail_exit_speed)}
            meta = {"rocket": self.cfg.rocket.name, "motor": self.cfg.motor.preset,
                    "config": self.cfg.model_dump(), "source": "simulator"}
            doc = self.recorder.finish(meta, self.link_stats(), truth)
            if doc:
                self.last_flight = doc
                self.broadcast({"type": "flight_complete", "flight": doc})
                self.event(f"Flight saved: apogee {doc['summary'].get('apogee_m')} m", "success")

    def _emit_sim_log(self) -> None:
        log = self.sim.events.log
        while self._sim_log_sent < len(log):
            _, text = log[self._sim_log_sent]
            self._sim_log_sent += 1
            self.event(text, "info", source="sim")

    def _trim_history(self) -> None:
        limit = int(HISTORY_SECONDS * self.cfg.link.tx_rate_hz) + 200
        while len(self.history) > limit:
            self.history.popleft()

    # ------------------------------------------------------------------ status
    def link_stats(self) -> dict[str, Any]:
        s = self.link.stats
        attempted = s.sent + s.skipped_busy
        missing = self.seq_gaps
        total = self.rx_count + missing
        return {
            "rx": self.rx_count, "sent": s.sent, "lost_radio": s.lost,
            "skipped_busy": s.skipped_busy, "corrupted": s.corrupted,
            "crc_errors": self.parser.crc_errors, "seq_gaps": missing,
            "loss_pct": round(100 * missing / total, 2) if total else 0.0,
            "attempted": attempted,
        }

    def status(self) -> dict[str, Any]:
        now = time.perf_counter()
        while self.rx_times and now - self.rx_times[0] > 1.0:
            self.rx_times.popleft()
        tr = self.sim.truth
        countdown = None
        if self.countdown_end is not None:
            countdown = round(self.countdown_end - tr.t, 2)
        airtime = self.link.airtime_s(FRAME_SIZE)
        return {
            "type": "status",
            "sim": {"phase": tr.phase, "t": round(tr.t, 2), "countdown": countdown,
                    "time_scale": self.cfg.sim.time_scale, "recording": self.recorder.active,
                    "pending_config": self.pending_config},
            "link": {
                **self.link_stats(),
                "rx_rate": len(self.rx_times),
                "rssi": _r(self.link.last_rssi, 1), "snr": _r(self.link.last_snr, 1),
                "airtime_ms": round(airtime * 1000, 2),
                "utilisation": round(airtime * self.cfg.link.tx_rate_hz, 3),
                "max_rate_hz": round(1 / airtime, 1) if airtime else None,
                "frame_bytes": FRAME_SIZE,
                "last_rx_age_ms": None if self.last_rx_wall is None
                else round((now - self.last_rx_wall) * 1000, 1),
            },
            "kalman": {"rejected": self.estimator.kf.rejected,
                       "enabled": self.cfg.kalman.enabled},
            "clients": len(self.clients),
            "ts": round(time.time() * 1000, 1),
        }
