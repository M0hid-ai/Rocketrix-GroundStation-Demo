# Rocket Ground Station

Ground station software for our Level 1 high-power rocket: real-time telemetry, flight-state
tracking, a Kalman-filtered altitude estimate and automatic post-flight reports.

This first milestone is a **full simulation mode**. A physics-based virtual rocket produces the
same binary radio packets our ESP32 flight computer will send, so the entire pipeline (decoding,
filtering, dashboard, recording, reports) can be built and tested before the hardware exists.

## Quick start

Requirements: Python 3.10+ and Node.js 18+.

```bash
./run.sh          # Linux / macOS / Raspberry Pi   ->  http://localhost:8000
run.bat           # Windows
./run.sh --dev    # hot-reload dev mode            ->  http://localhost:5173
```

Open the dashboard, press **LAUNCH**, and watch the flight. When it lands, a report is saved
automatically under **Flight reports**. Other devices on the same network (phones, laptops) can
open `http://<ground-station-ip>:8000` to watch live.

## What the demo shows

| Area | Details |
|---|---|
| Live dashboard | Altitude (Kalman vs raw baro vs GPS vs sim truth), vertical velocity, acceleration, pressure, temperature, signal strength; 30 s / 1 min / 3 min / whole-flight windows |
| Flight phases | PAD → BOOST → COAST → APOGEE → DROGUE → MAIN → LANDED pipeline with timestamps, marked on every chart |
| Mission control | ARM / LAUNCH (with countdown) / ABORT / RESET, 1× 2× 5× simulation speed, mission clock |
| Link health | End-to-end latency split into radio and ground → screen, packet rate, loss, CRC errors, RSSI/SNR, LoRa radio duty |
| Alerts | Telemetry lost, GPS no fix, low battery, radio overloaded, heavy packet loss |
| Post-flight report | Apogee, max velocity/acceleration, burn time, time to apogee, drogue/main descent rates, landing speed, drift, timeline, charts, CSV export, print to PDF |
| Live tuning | Every sensor rate and noise level, radio settings, Kalman tuning, rocket, motor, recovery and weather can be changed from the ⚙ Settings drawer |

## Architecture

```
 ┌──────────────── simulated rocket (ESP32 in the real system) ───────────────┐
 │ physics.py  3-DOF flight: thrust curve, drag, wind, rail, drogue + main   │
 │ sensors.py  BMP388 baro · temp · MPU6050 IMU · NEO-M8N GPS · battery      │
 │ protocol.py 48-byte binary frame, sync word + CRC16                       │
 └──────────────────────────────────┬─────────────────────────────────────────┘
                                    │  link.py  LoRa: airtime, path loss,
                                    │  packet loss, corruption, latency
 ┌──────────────────────────────────▼──────── ground station (Raspberry Pi) ──┐
 │ FrameParser   byte-stream decoder (works the same on a USB serial port)   │
 │ estimator.py  pad calibration + Kalman filter [altitude, velocity, accel] │
 │ engine.py     2 ms real-time loop, pushes every frame immediately         │
 │ recorder.py   CSV + JSON per flight · summary.py  post-flight analysis    │
 │ main.py       FastAPI: REST + WebSocket /ws                               │
 └──────────────────────────────────┬─────────────────────────────────────────┘
                                    │  WebSocket (JSON per frame)
                          React + uPlot dashboard (frontend/)
```

### Why this is low-latency

* No batching: each decoded frame goes to every connected browser the moment it arrives.
  The loop wakes every 2 ms, and a slow viewer only drops its own oldest frames.
* The browser writes frames straight into column buffers. Charts pull them on
  `requestAnimationFrame`, and React widgets re-render at most about 20 times a second, so a
  100 Hz stream never floods the UI.
* uPlot draws tens of thousands of points at 60 fps on canvas.
* The **radio** is the real bottleneck. The link panel shows the LoRa time-on-air: at SF7 /
  500 kHz a 48-byte frame takes about 24 ms, so the downlink tops out around 40 Hz. At SF9 it's
  only about 13 Hz. Try it in Settings → Radio link.

### Kalman filter

`backend/groundstation/kalman.py` is a 3-state constant-acceleration filter (altitude, vertical
velocity, vertical acceleration) with scalar updates, so it's cheap enough to port to the ESP32
as-is. It fuses:

* the **barometric altitude** (relative to the pressure averaged on the pad), and
* the **IMU axial acceleration**, projected onto vertical, while the motor burns and during coast.

Process noise is raised during boost so the filter can follow the thrust step. Innovation
gating rejects outliers such as the pressure spike from an ejection charge; the dashboard shows
how many were rejected. In simulation mode the "Sim truth" series shows the estimator error
directly. It's typically within 1% of true apogee.

## Project layout

```
backend/
  groundstation/   Python package (simulator, protocol, estimator, server)
  tests/           pytest: protocol round-trip, parser resync, Kalman, full pipeline
  data/flights/    saved flights (git-ignored)
frontend/
  src/lib/         WebSocket store, API client, types
  src/components/  charts, mission bar, tiles, side panels, settings, reports
run.sh / run.bat   one-command start
```

## Development

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                      # backend tests
cd ../frontend && npm install && npm run typecheck
```

API: `GET /api/config`, `PATCH /api/config` (partial JSON, validated), `POST /api/command/{arm|disarm|launch|abort|reset}`,
`GET /api/flights`, `GET /api/flights/{id}`, `GET /api/flights/{id}/csv`, WebSocket `/ws`. Interactive docs are at `/docs`.

## Moving to real hardware

1. Implement the frame in `protocol.py` as a packed C struct on the ESP32 (same field order,
   little-endian, CRC16-CCITT over `LEN + payload`).
2. Plug the LoRa receiver into the Raspberry Pi over USB serial and feed its bytes into
   `FrameParser.feed()`. Everything downstream (estimator, recorder, dashboard) stays unchanged.
3. Replace the approximate motor curves with real `.eng` data from thrustcurve.org.

## Open questions for the team

* Which motor (H128W, H238T, …), and the airframe diameter and mass?
* Which exact sensors, and the sample rate for each? (The defaults assume BMP388, MPU6050 and NEO-M8N.)
* Which radio module and frequency band (433 / 868 / 915 MHz), and which is legal where we launch?
* Single deploy (motor ejection) or dual deploy, and at what main deploy altitude?
* Should the Kalman filter also run on the ESP32 to trigger deployment, or only on the ground?
* Do we need offline map tiles for the recovery GPS, or is bearing + distance enough?
