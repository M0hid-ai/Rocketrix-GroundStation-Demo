import { useEffect, useRef, useState } from "react";
import uPlot from "uplot";
import { api } from "../lib/api";
import { dateTime, store } from "../lib/store";
import type { FlightDoc, FlightListItem, Phase } from "../lib/types";
import { axisStyle, phaseMarksPlugin, tooltipPlugin } from "./LiveChart";

const PHASE_COLOR: Record<Phase, string> = {
  IDLE: "#2a3647",
  ARMED: "#2a3647",
  BOOST: "#8a4a1c",
  COAST: "#1c4f8a",
  DROGUE: "#1e5c4b",
  MAIN: "#23704f",
  LANDED: "#39414d",
};

function FlightChart({
  doc,
  title,
  unit,
  series,
  decimals = 1,
}: {
  doc: FlightDoc;
  title: string;
  unit: string;
  series: { key: string; label: string; color: string; dash?: boolean }[];
  decimals?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = host.current!;
    const s = doc.series;
    const x = s.tp as number[];
    const marks: { t: number; phase: Phase }[] = [];
    s.st.forEach((p, i) => {
      if (i === 0 || s.st[i - 1] !== p) marks.push({ t: x[i], phase: p });
    });
    const fmt = (v: number) => `T+${v.toFixed(1)}s`;
    const u = new uPlot(
      {
        width: el.clientWidth,
        height: 240,
        legend: { show: false },
        cursor: { points: { size: 7 } },
        scales: { x: { time: false } },
        axes: [axisStyle((v) => `+${v.toFixed(0)}s`), { ...axisStyle(), size: 52 }],
        series: [
          {},
          ...series.map((d) => ({
            label: d.label,
            stroke: d.color,
            width: 2,
            dash: d.dash ? [6, 5] : undefined,
            spanGaps: true,
            points: { show: false },
          })),
        ],
        plugins: [phaseMarksPlugin(() => marks), tooltipPlugin(series, unit, decimals, fmt)],
      },
      [x, ...series.map((d) => s[d.key] ?? [])] as uPlot.AlignedData,
      el,
    );
    const ro = new ResizeObserver(() => u.setSize({ width: el.clientWidth, height: 240 }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      u.destroy();
    };
  }, [doc, series, unit, decimals]);

  return (
    <div className="panel">
      <div className="panel-title">
        <span>{title}</span>
        {series.length > 1 && (
          <div className="legend">
            {series.map((d) => (
              <span key={d.key} className="legend-item">
                <span className={`swatch ${d.dash ? "dashed" : ""}`} style={{ background: d.color, color: d.color }} />
                {d.label}
              </span>
            ))}
          </div>
        )}
      </div>
      <div ref={host} />
    </div>
  );
}

const ALT = [
  { key: "h", label: "Kalman", color: "var(--s1)" },
  { key: "ab", label: "Baro raw", color: "var(--s2)" },
  { key: "hg", label: "GPS", color: "var(--s3)" },
];
const VEL = [{ key: "v", label: "Vertical velocity", color: "var(--s1)" }];
const ACC = [{ key: "ax", label: "Axial accel (IMU)", color: "var(--s2)" }];
const TEMP = [{ key: "tc", label: "Temperature", color: "var(--s3)" }];

// uPlot draws on canvas, which does not resolve CSS variables
function cssVars<T extends { color: string }>(defs: T[]): T[] {
  const cs = getComputedStyle(document.documentElement);
  return defs.map((d) => ({
    ...d,
    color: d.color.startsWith("var(") ? cs.getPropertyValue(d.color.slice(4, -1)).trim() : d.color,
  }));
}

function Stat({ label, value, unit }: { label: string; value: number | null | undefined; unit: string }) {
  return (
    <div className="panel tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value" style={{ fontSize: 26 }}>
        {value === null || value === undefined ? "—" : value}
        <span className="tile-unit">{unit}</span>
      </div>
    </div>
  );
}

function Report({ doc, onDelete }: { doc: FlightDoc; onDelete: () => void }) {
  const s = doc.summary;
  const phases = (s.phases ?? []).filter((p) => p.tp !== null);
  const total = s.flight_time_s ?? 1;
  const [series] = useState(() => ({ alt: cssVars(ALT), vel: cssVars(VEL), acc: cssVars(ACC), temp: cssVars(TEMP) }));
  const truth = s.truth ?? {};
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="panel report-head">
        <div>
          <h1>Flight report · {doc.meta.rocket}</h1>
          <div className="meta">
            {dateTime(doc.started_at)} · motor {doc.meta.motor} · source {doc.meta.source} · id {doc.id}
          </div>
        </div>
        <div className="controls no-print">
          <a className="btn sm" href={api.csvUrl(doc.id)} download>
            ⤓ CSV
          </a>
          <button className="btn sm" onClick={() => window.print()}>
            ⎙ Print / PDF
          </button>
          <button className="btn sm ghost" onClick={onDelete}>
            Delete
          </button>
        </div>
      </div>

      <div className="tiles">
        <Stat label="Apogee" value={s.apogee_m} unit="m" />
        <Stat label="Max velocity" value={s.max_velocity_mps} unit="m/s" />
        <Stat label="Max acceleration" value={s.max_accel_g} unit="g" />
        <Stat label="Time to apogee" value={s.time_to_apogee_s} unit="s" />
        <Stat label="Flight time" value={s.flight_time_s} unit="s" />
        <Stat label="Drogue descent" value={s.drogue_descent_mps} unit="m/s" />
        <Stat label="Main descent" value={s.main_descent_mps} unit="m/s" />
        <Stat label="Landing speed" value={s.landing_velocity_mps} unit="m/s" />
        <Stat label="Drift from pad" value={s.drift_m} unit="m" />
      </div>

      <div className="panel">
        <div className="panel-title">Flight timeline</div>
        <div className="timeline">
          {phases.map((p, i) => {
            const end = i + 1 < phases.length ? phases[i + 1].tp! : total;
            const w = Math.max(0, end - p.tp!);
            if (p.state === "LANDED") return null;
            return (
              <div
                key={i}
                style={{ flex: `${Math.max(w, total * 0.04)} 0 0`, background: PHASE_COLOR[p.state] }}
                title={`${p.state} T+${p.tp!.toFixed(1)}s → ${end.toFixed(1)}s`}
              >
                {p.state} {w.toFixed(1)}s
              </div>
            );
          })}
        </div>
      </div>

      <div className="charts">
        <FlightChart doc={doc} title="Altitude" unit="m" series={series.alt} />
        <FlightChart doc={doc} title="Vertical velocity (Kalman)" unit="m/s" series={series.vel} />
        <FlightChart doc={doc} title="Axial acceleration" unit="g" series={series.acc} decimals={2} />
        <FlightChart doc={doc} title="Temperature" unit="°C" series={series.temp} decimals={2} />
      </div>

      <div className="charts">
        <div className="panel">
          <div className="panel-title">Events</div>
          <table className="table">
            <thead>
              <tr>
                <th>Phase</th>
                <th>Time</th>
                <th style={{ textAlign: "right" }}>Altitude</th>
              </tr>
            </thead>
            <tbody>
              {phases.map((p, i) => (
                <tr key={i}>
                  <td>{p.state}</td>
                  <td className="mono">T+{p.tp!.toFixed(2)} s</td>
                  <td className="num">{p.alt.toFixed(1)} m</td>
                </tr>
              ))}
              <tr>
                <td>Burnout</td>
                <td className="mono">{s.burn_time_s !== null ? `T+${s.burn_time_s} s` : "—"}</td>
                <td className="num" />
              </tr>
            </tbody>
          </table>
        </div>
        <div className="panel">
          <div className="panel-title">Data quality</div>
          <table className="table">
            <tbody>
              <tr>
                <td>Apogee · Kalman / baro / GPS</td>
                <td className="num">
                  {s.apogee_m} / {s.apogee_baro_m} / {s.apogee_gps_m} m
                </td>
              </tr>
              {truth.apogee_m !== undefined && (
                <tr>
                  <td>Simulator true apogee (estimator error)</td>
                  <td className="num">
                    {truth.apogee_m} m ({s.apogee_error_m !== undefined && s.apogee_error_m >= 0 ? "+" : ""}
                    {s.apogee_error_m} m)
                  </td>
                </tr>
              )}
              <tr>
                <td>Packets received / lost</td>
                <td className="num">
                  {s.link?.rx} / {s.link?.seq_gaps} ({s.link?.loss_pct}%)
                </td>
              </tr>
              <tr>
                <td>CRC rejected / radio busy drops</td>
                <td className="num">
                  {s.link?.crc_errors} / {s.link?.skipped_busy}
                </td>
              </tr>
              <tr>
                <td>Temperature range</td>
                <td className="num">
                  {s.min_temp_c} – {s.max_temp_c} °C
                </td>
              </tr>
              <tr>
                <td>Minimum battery voltage</td>
                <td className="num">{s.min_battery_v} V</td>
              </tr>
              {truth.max_mach !== undefined && (
                <tr>
                  <td>Max Mach (sim) / rail exit speed</td>
                  <td className="num">
                    {truth.max_mach} / {truth.rail_exit_mps} m/s
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function FlightsView({ focusId }: { focusId: string | null }) {
  const [list, setList] = useState<FlightListItem[]>([]);
  const [selected, setSelected] = useState<string | null>(focusId);
  const [doc, setDoc] = useState<FlightDoc | null>(null);

  const refresh = () =>
    api.flights().then((l) => {
      setList(l);
      setSelected((cur) => cur ?? l[0]?.id ?? null);
    });

  useEffect(() => {
    refresh();
    return store.onFlightComplete(() => refresh());
  }, []);
  useEffect(() => {
    if (focusId) setSelected(focusId);
  }, [focusId]);
  useEffect(() => {
    if (selected) api.flight(selected).then(setDoc).catch(() => setDoc(null));
    else setDoc(null);
  }, [selected]);

  return (
    <div className="flights-layout">
      <div className="panel flight-list-panel">
        <div className="panel-title">
          <span>Recorded flights</span>
          <span className="hint">{list.length}</span>
        </div>
        <div className="flight-list">
          {list.length === 0 && <div className="empty">No flights yet. Launch one from the Live tab.</div>}
          {list.map((f) => (
            <button
              key={f.id}
              className={`flight-item ${f.id === selected ? "active" : ""}`}
              onClick={() => setSelected(f.id)}
            >
              <div className="fi-top">
                <span>{f.apogee_m ?? "—"} m</span>
                <span className="mono" style={{ color: "var(--text-2)" }}>
                  {f.motor}
                </span>
              </div>
              <div className="fi-sub">
                {dateTime(f.started_at)} · {f.flight_time_s ?? "—"} s
              </div>
            </button>
          ))}
        </div>
      </div>
      <div>
        {doc ? (
          <Report
            key={doc.id}
            doc={doc}
            onDelete={async () => {
              if (!confirm("Delete this flight recording?")) return;
              await api.deleteFlight(doc.id);
              setSelected(null);
              refresh();
            }}
          />
        ) : (
          <div className="panel empty">Select a flight to see its summary.</div>
        )}
      </div>
    </div>
  );
}
