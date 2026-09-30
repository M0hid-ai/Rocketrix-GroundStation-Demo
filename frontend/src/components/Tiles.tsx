import { useStore } from "../lib/store";

function Tile({
  label,
  value,
  unit,
  sub,
  hero,
  bar,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  hero?: boolean;
  bar?: number;
}) {
  return (
    <div className={`panel tile ${hero ? "hero" : ""}`}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">
        {value}
        {unit && <span className="tile-unit">{unit}</span>}
      </div>
      {sub && <div className="tile-sub">{sub}</div>}
      {bar !== undefined && <div className="tile-bar" style={{ width: `${Math.max(0, Math.min(1, bar)) * 100}%` }} />}
    </div>
  );
}

const f = (v: number | null | undefined, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(d));

export default function Tiles() {
  const { m, peaks } = useStore((s) => ({ m: s.latest, peaks: s.peaks }));
  const truthErr = m && m.th !== null ? m.h - m.th : null;
  return (
    <div className="tiles">
      <Tile
        hero
        label="Altitude AGL"
        value={f(m?.h)}
        unit="m"
        sub={`baro ${f(m?.ab)} · gps ${f(m?.hg)}${truthErr !== null ? ` · err ${truthErr >= 0 ? "+" : ""}${truthErr.toFixed(1)}` : ""}`}
        bar={peaks.maxAlt > 0 && m ? m.h / peaks.maxAlt : 0}
      />
      <Tile
        label="Vertical speed"
        value={f(m?.v)}
        unit="m/s"
        sub={`max ${f(peaks.maxVel)} m/s · Mach ${f(m ? Math.abs(m.v) / 340 : null, 2)}`}
      />
      <Tile
        label="Acceleration"
        value={f(m?.ax, 2)}
        unit="g"
        sub={`max ${f(peaks.maxAccelG, 1)} g · lat ${f(m?.al, 2)} g`}
      />
      <Tile
        label="Max altitude"
        value={f(peaks.maxAlt)}
        unit="m"
        sub={peaks.apogeeTp !== null ? `at T+${peaks.apogeeTp.toFixed(1)} s` : "awaiting flight"}
      />
      <Tile label="Pressure" value={f(m ? m.p / 100 : null, 2)} unit="hPa" sub={`${f(m?.p, 0)} Pa`} />
      <Tile label="Temperature" value={f(m?.tc, 2)} unit="°C" sub="avionics bay sensor" />
      <Tile
        label="Attitude"
        value={f(m?.tl, 1)}
        unit="° tilt"
        sub={`roll ${f(m?.rr, 0)} °/s`}
      />
      <Tile
        label="Battery"
        value={f(m?.bat, 2)}
        unit="V"
        sub={m ? (m.bat < 7.0 ? "LOW - check LiPo" : "2S LiPo nominal") : "—"}
      />
      <Tile
        label="GPS"
        value={m ? String(m.sat) : "—"}
        unit="sats"
        sub={m ? `${m.gf ? "3D fix" : "NO FIX"} · range ${f(m.rng, 0)} m` : "—"}
      />
    </div>
  );
}

export function Alerts() {
  const { m, st, connected } = useStore((s) => ({ m: s.latest, st: s.status, connected: s.connected }));
  const age = st?.link.last_rx_age_ms ?? null;
  const chips: { level: "good" | "warn" | "critical"; text: string }[] = [];
  if (!connected) chips.push({ level: "critical", text: "Ground station offline" });
  else if (age === null) chips.push({ level: "warn", text: "Waiting for telemetry" });
  else if (age > 1000) chips.push({ level: "critical", text: `Telemetry lost ${(age / 1000).toFixed(1)} s` });
  else chips.push({ level: "good", text: "Telemetry link OK" });
  if (m && !m.gf) chips.push({ level: "warn", text: "GPS no fix" });
  if (m && m.bat < 7.0) chips.push({ level: "critical", text: "Battery low" });
  if (st && st.link.utilisation > 0.9)
    chips.push({ level: "warn", text: `Radio ${Math.round(st.link.utilisation * 100)}% busy` });
  if (st && st.link.loss_pct > 10) chips.push({ level: "warn", text: `Packet loss ${st.link.loss_pct}%` });
  if (st?.sim.recording) chips.push({ level: "good", text: "● Recording" });
  if (st?.sim.pending_config) chips.push({ level: "warn", text: "Config changes apply after reset" });
  const icon = { good: "✓", warn: "!", critical: "✕" };
  return (
    <div className="alerts">
      {chips.map((c) => (
        <span key={c.text} className={`chip ${c.level}`}>
          <span className={`dot ${c.level === "good" ? "good" : c.level === "warn" ? "warn" : "bad"}`} />
          <span aria-hidden>{icon[c.level]}</span> {c.text}
        </span>
      ))}
    </div>
  );
}
