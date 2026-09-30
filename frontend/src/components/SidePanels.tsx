import { useEffect, useRef } from "react";
import { clockTime, useStore } from "../lib/store";

const pct = (x: number) => `${Math.max(0, Math.min(100, x * 100))}%`;

export function LinkPanel() {
  const { st, lat, rate } = useStore((s) => ({ st: s.status, lat: s.latency, rate: s.msgRate }));
  const l = st?.link;
  const total = lat.radioMs + lat.groundMs;
  const util = l?.utilisation ?? 0;
  const rssi = l?.rssi ?? -130;
  const rssiNorm = (rssi + 130) / 100;
  return (
    <div className="panel">
      <div className="panel-title">
        <span>Downlink</span>
        <span className="hint">LoRa · {l?.frame_bytes ?? "—"} B frames</span>
      </div>
      <div className="latency-hero">
        <span className="big">{total.toFixed(1)}</span>
        <span className="tile-unit">ms end-to-end</span>
      </div>
      <dl className="kv">
        <dt>Radio (air + serial)</dt>
        <dd>{lat.radioMs.toFixed(1)} ms</dd>
        <dt>Ground → display</dt>
        <dd>{lat.groundMs.toFixed(1)} ms</dd>
        <dt>WebSocket RTT</dt>
        <dd>{lat.rttMs === null ? "—" : `${lat.rttMs.toFixed(1)} ms`}</dd>
        <dt>Frame rate (rx / ui)</dt>
        <dd>
          {l?.rx_rate ?? 0} / {rate} Hz
        </dd>
      </dl>
      <div style={{ height: 10 }} />
      <dl className="kv">
        <dt>Radio duty (airtime {l?.airtime_ms ?? "—"} ms)</dt>
        <dd>{Math.round(util * 100)}%</dd>
      </dl>
      <div className="meter">
        <span
          style={{
            width: pct(util),
            background: util > 0.9 ? "var(--critical)" : util > 0.7 ? "var(--warn)" : "var(--s3)",
          }}
        />
      </div>
      <dl className="kv">
        <dt>RSSI / SNR</dt>
        <dd>
          {l ? `${rssi.toFixed(0)} dBm / ${l.snr.toFixed(0)} dB` : "—"}
        </dd>
      </dl>
      <div className="meter">
        <span style={{ width: pct(rssiNorm), background: "var(--s1)" }} />
      </div>
      <dl className="kv">
        <dt>Packets received</dt>
        <dd>{l?.rx ?? 0}</dd>
        <dt>Lost (sequence gaps)</dt>
        <dd>
          {l?.seq_gaps ?? 0} ({l?.loss_pct ?? 0}%)
        </dd>
        <dt>CRC rejected</dt>
        <dd>{l?.crc_errors ?? 0}</dd>
        <dt>Dropped, radio busy</dt>
        <dd>{l?.skipped_busy ?? 0}</dd>
        <dt>Max rate at this SF/BW</dt>
        <dd>{l?.max_rate_hz ?? "—"} Hz</dd>
        <dt>Kalman outliers rejected</dt>
        <dd>{st?.kalman.rejected ?? 0}</dd>
      </dl>
    </div>
  );
}

export function AttitudePanel() {
  const m = useStore((s) => s.latest);
  const tilt = m?.tl ?? 0;
  const roll = m?.rr ?? 0;
  const rollAngle = useRef(0);
  rollAngle.current = (rollAngle.current + roll * 0.05) % 360;
  const stripe = Math.cos((rollAngle.current * Math.PI) / 180);
  return (
    <div className="panel">
      <div className="panel-title">
        <span>Attitude</span>
        <span className="hint">from IMU</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <svg viewBox="-60 -60 120 120" width="130" height="130" aria-label={`Tilt ${tilt.toFixed(1)} degrees`}>
          <circle r="54" fill="none" stroke="var(--border-strong)" />
          <circle r="36" fill="none" stroke="var(--border)" strokeDasharray="2 4" />
          <line x1="0" y1="-58" x2="0" y2="58" stroke="var(--border)" />
          <line x1="-58" y1="0" x2="58" y2="0" stroke="var(--border)" />
          <text x="0" y="-44" textAnchor="middle" fontSize="7" fill="var(--muted)">
            UP
          </text>
          <g transform={`rotate(${tilt})`} style={{ transition: "transform 0.1s linear" }}>
            <path d="M0 -40 C7 -30 8 -18 8 -8 L8 26 L-8 26 L-8 -8 C-8 -18 -7 -30 0 -40 Z" fill="#dfe7f1" />
            <rect x={-8} y={0} width={16} height={4} fill="var(--s1)" opacity={0.4 + 0.6 * Math.abs(stripe)} />
            <path d="M8 14 L16 30 L8 26 Z M-8 14 L-16 30 L-8 26 Z" fill="var(--s2)" />
            <path d="M-4 26 L0 36 L4 26 Z" fill="#fab219" opacity={m?.st === "BOOST" ? 1 : 0} />
          </g>
        </svg>
        <dl className="kv" style={{ flex: 1 }}>
          <dt>Tilt from vertical</dt>
          <dd>{tilt.toFixed(1)}°</dd>
          <dt>Roll rate</dt>
          <dd>{roll.toFixed(0)} °/s</dd>
          <dt>Axial accel</dt>
          <dd>{(m?.ax ?? 0).toFixed(2)} g</dd>
          <dt>Lateral accel</dt>
          <dd>{(m?.al ?? 0).toFixed(2)} g</dd>
        </dl>
      </div>
    </div>
  );
}

export function GroundTrack() {
  const { track, m } = useStore((s) => ({ track: s.track, m: s.latest }));
  const maxR = Math.max(50, ...track.map((p) => Math.hypot(p.e, p.n)));
  const ring = [50, 100, 200, 500, 1000, 2000, 5000, 10000].find((r) => r >= maxR) ?? 20000;
  const scale = 52 / (ring * 1.05);
  const pts = track.map((p) => `${(p.e * scale).toFixed(1)},${(-p.n * scale).toFixed(1)}`).join(" ");
  const last = track[track.length - 1];
  const bearing = last ? ((Math.atan2(last.e, last.n) * 180) / Math.PI + 360) % 360 : null;
  return (
    <div className="panel">
      <div className="panel-title">
        <span>Ground track</span>
        <span className="hint">GPS, relative to pad</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <svg viewBox="-60 -60 120 120" width="130" height="130" aria-label="Ground track">
          {[1, 0.5].map((k) => (
            <circle key={k} r={52 * k / 1.05} fill="none" stroke="var(--border)" strokeDasharray={k === 1 ? "" : "2 3"} />
          ))}
          <line x1="0" y1="-56" x2="0" y2="56" stroke="var(--border)" />
          <line x1="-56" y1="0" x2="56" y2="0" stroke="var(--border)" />
          <text x="0" y="-52" textAnchor="middle" fontSize="7" fill="var(--muted)">
            N
          </text>
          <text x="54" y="-2" textAnchor="end" fontSize="6" fill="var(--muted)">
            {ring} m
          </text>
          <polyline points={pts} fill="none" stroke="var(--s1)" strokeWidth="1.5" strokeLinejoin="round" />
          <circle r="2.5" fill="var(--text-2)" />
          {last && <circle cx={last.e * scale} cy={-last.n * scale} r="4" fill="var(--s2)" stroke="var(--panel)" strokeWidth="1.5" />}
        </svg>
        <dl className="kv" style={{ flex: 1 }}>
          <dt>Distance from pad</dt>
          <dd>{last ? `${Math.hypot(last.e, last.n).toFixed(0)} m` : "—"}</dd>
          <dt>Bearing</dt>
          <dd>{bearing === null ? "—" : `${bearing.toFixed(0)}°`}</dd>
          <dt>Latitude</dt>
          <dd>{m ? m.lat.toFixed(6) : "—"}</dd>
          <dt>Longitude</dt>
          <dd>{m ? m.lon.toFixed(6) : "—"}</dd>
        </dl>
      </div>
    </div>
  );
}

export function EventLog() {
  const events = useStore((s) => s.events);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [events.length]);
  const color = { info: "var(--muted)", warn: "var(--warn)", error: "var(--critical)", success: "var(--good)" };
  return (
    <div className="panel">
      <div className="panel-title">
        <span>Event log</span>
        <span className="hint">{events.length} events</span>
      </div>
      <div className="events" ref={box}>
        {events.length === 0 && <div className="empty">No events yet - press LAUNCH.</div>}
        {events.map((e, i) => (
          <div className="event" key={i}>
            <span className="when">
              {e.tp !== null ? `T${e.tp < 0 ? "−" : "+"}${Math.abs(e.tp).toFixed(1)}` : clockTime(e.ts)}
            </span>
            <span className="dot" style={{ background: color[e.level] }} />
            <span>
              {e.text}
              {e.source === "sim" && <span className="src">SIM</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
