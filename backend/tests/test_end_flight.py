import tempfile
from pathlib import Path

from groundstation.engine import GroundStation


def run(station: GroundStation, seconds: float, clock: list[float], dt: float = 0.01) -> None:
    """Drive the real-time loop with a fake clock, as fast as the CPU allows."""
    for _ in range(int(seconds / dt)):
        clock[0] += dt
        now = clock[0]
        station._advance(dt, now)
        for d in station.link.poll(now):
            for frame in station.parser.feed(d.data):
                station._on_frame(frame, d.rssi_dbm, d.snr_db, d.latency_ms, now)


def launched_station() -> tuple[GroundStation, list[float]]:
    station = GroundStation(Path(tempfile.mkdtemp()))
    station.cfg.sim.countdown_s = 1.0
    clock = [1000.0]
    assert station.command("launch")["ok"]
    return station, clock


def test_end_is_rejected_before_liftoff():
    station = GroundStation(Path(tempfile.mkdtemp()))
    assert not station.command("end")["ok"]
    station.command("arm")
    assert station.command("end") == {"ok": False, "error": "no flight in progress"}
    assert station.recorder.active  # still armed, nothing lost


def test_end_during_coast_saves_report_and_resets():
    station, clock = launched_station()
    run(station, 4.0, clock)  # ~3 s after ignition: motor burnt out, still climbing
    assert station.ground_state == "COAST"
    sent = []
    station.broadcast = lambda msg, keep=False: sent.append(msg)

    assert station.command("end", user="flightops")["ok"]

    doc = station.last_flight
    s = doc["summary"]
    assert s["valid"] and s["ended_early"] and s["ended_in"] == "COAST"
    assert s["ended_by"] == "flightops"
    assert s["apogee_m"] > 50
    assert "apogee_error_m" not in s  # no real apogee yet, so no error to report
    assert station.recorder.load(doc["id"]) is not None
    assert station.recorder.csv_path(doc["id"]) is not None
    # everyone gets the report, then a fresh pad
    types = [m.get("type") for m in sent]
    assert types.index("flight_complete") < types.index("reset")
    assert station.sim.truth.phase == "IDLE" and not station.recorder.active
    assert station.command("launch")["ok"]  # can fly again straight away


def test_end_after_apogee_keeps_apogee_error():
    station, clock = launched_station()
    for _ in range(60):
        run(station, 1.0, clock)
        if station.ground_state in ("DROGUE", "MAIN"):
            break
    assert station.command("end")["ok"]
    s = station.last_flight["summary"]
    assert s["ended_in"] in ("DROGUE", "MAIN") and "apogee_error_m" in s
