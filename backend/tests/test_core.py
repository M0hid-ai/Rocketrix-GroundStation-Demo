import random

from groundstation.config import Config, apply_patch
from groundstation.estimator import Estimator
from groundstation.kalman import AltitudeKalman
from groundstation.link import lora_airtime_s
from groundstation.physics import FlightSim
from groundstation.protocol import FRAME_SIZE, FrameParser, encode
from groundstation.sensors import Readings, SensorSuite


def _readings() -> Readings:
    return Readings(pressure_pa=94_321.5, temp_c=21.37, accel_axial_g=-3.456, accel_lateral_g=0.2,
                    roll_rate_dps=123.4, tilt_deg=4.2, gps_lat=35.3472123, gps_lon=-117.8086456,
                    gps_alt_msl=812.34, gps_sats=11, gps_fix=True, battery_v=7.912, baro_seq=7,
                    imu_seq=9, gps_seq=3, temp_seq=1,
                    enabled={"baro": True, "temp": True, "imu": True, "gps": True,
                             "battery": False})


def test_frame_roundtrip():
    data = encode(1234, 56_789, "COAST", 0, _readings())
    assert len(data) == FRAME_SIZE
    (f,) = FrameParser().feed(data)
    assert f.seq == 1234 and f.t_ms == 56_789 and f.state == "COAST"
    assert abs(f.pressure_pa - 94_321.5) < 0.01
    assert abs(f.accel_axial_g + 3.456) < 1e-3
    assert abs(f.gps_lat - 35.3472123) < 1e-7
    assert f.gps_fix and f.sensor_on("baro") and not f.sensor_on("battery")


def test_parser_resyncs_after_garbage_and_rejects_bad_crc():
    good = encode(1, 10, "BOOST", 0, _readings())
    bad = bytearray(encode(2, 20, "BOOST", 0, _readings()))
    bad[10] ^= 0xFF
    parser = FrameParser()
    stream = b"\x00\xAAjunk" + good + bytes(bad) + good
    frames = []
    for i in range(0, len(stream), 7):  # arrive in arbitrary chunks, like a serial port
        frames += parser.feed(stream[i:i + 7])
    assert [f.seq for f in frames] == [1, 1]
    assert parser.crc_errors == 1


def test_kalman_tracks_constant_acceleration():
    kf = AltitudeKalman(jerk_psd=0.5, baro_sigma=1.0, gate_sigma=0)
    rng = random.Random(1)
    for i in range(1, 501):
        t = i * 0.02
        kf.predict_to(t)
        kf.update_altitude(0.5 * 3.0 * t * t + rng.gauss(0, 1.0))
    t = 500 * 0.02
    assert abs(kf.velocity - 3.0 * t) < 1.0
    assert abs(kf.acceleration - 3.0) < 1.0  # baro-only accel is noisy


def test_kalman_gates_outliers():
    kf = AltitudeKalman(jerk_psd=1.0, baro_sigma=0.5, gate_sigma=5)
    for i in range(1, 200):
        kf.predict_to(i * 0.02)
        kf.update_altitude(100.0)
    kf.predict_to(200 * 0.02)
    assert kf.update_altitude(60.0) is False  # ejection-charge spike
    assert abs(kf.altitude - 100.0) < 0.5


def test_full_pipeline_estimates_apogee():
    cfg = Config()
    rng = random.Random(42)
    sim, sensors, est = FlightSim(cfg, rng), SensorSuite(cfg, rng), Estimator(cfg.kalman)
    parser = FrameParser()
    dt, seq, next_tx, max_alt = 0.001, 0, 0.0, 0.0
    sim.arm()
    while sim.truth.phase != "LANDED" and sim.truth.t < 300:
        if sim.truth.t > 3 and sim.events.ignition is None:
            sim.ignite()
        truth = sim.step(dt)
        r = sensors.update(truth, dt)
        if truth.t >= next_tx:
            next_tx += 1 / cfg.link.tx_rate_hz
            seq += 1
            for f in parser.feed(encode(seq, int(truth.t * 1000), truth.phase, 0, r)):
                max_alt = max(max_alt, est.process(f).alt)
    true_apogee = sim.events.apogee_alt
    assert true_apogee and 300 < true_apogee < 1500
    assert abs(max_alt - true_apogee) / true_apogee < 0.03


def test_lora_airtime_reasonable():
    # 48 byte frame at SF7 / 250 kHz is roughly 40 ms on air
    assert 0.03 < lora_airtime_s(FRAME_SIZE, 7, 250, 5) < 0.06


def test_motor_preset_patch_fills_values():
    cfg = apply_patch(Config(), {"motor": {"preset": "I200W"}})
    assert cfg.motor.total_impulse_ns == 330.0
    cfg = apply_patch(cfg, {"sensors": {"baro": {"rate_hz": 25}}})
    assert cfg.sensors.baro.rate_hz == 25 and cfg.motor.preset == "I200W"
