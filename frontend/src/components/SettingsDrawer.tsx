/**
 * Settings are generated from the backend's JSON schema, so every new config field added in
 * Python shows up here automatically with the right range, type and description.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import type { JsonSchema } from "../lib/types";

const SECTIONS: { key: string; title: string; note: string; open?: boolean }[] = [
  { key: "sensors", title: "Sensors", note: "Sample rates and noise. Applied live.", open: true },
  { key: "link", title: "Radio link (ESP32 + LoRa)", note: "Downlink rate, LoRa modem settings, loss and latency. Applied live." },
  { key: "kalman", title: "Kalman filter", note: "Ground-side fusion of barometer + accelerometer. Applied live." },
  { key: "sim", title: "Simulation", note: "Speed, countdown and random seed." },
  { key: "rocket", title: "Rocket", note: "Airframe. Applies to the next flight (after reset)." },
  { key: "motor", title: "Motor", note: "Pick a preset or edit the numbers. Applies to the next flight." },
  { key: "recovery", title: "Recovery", note: "Parachute deployment. Applies to the next flight." },
  { key: "environment", title: "Launch site", note: "Weather and location. Applies to the next flight." },
];

const UNITS: [RegExp, string][] = [
  [/_kg$/, "kg"], [/_mm$/, "mm"], [/_mps$/, "m/s"], [/_mps2$/, "m/s²"], [/_m$/, "m"], [/_s$/, "s"],
  [/_hz$/, "Hz"], [/_pa$/, "Pa"], [/_c$/, "°C"], [/_g$/, "g"], [/_dps$/, "°/s"], [/_pct$/, "%"],
  [/_ms$/, "ms"], [/_dbm$/, "dBm"], [/_khz$/, "kHz"], [/_mhz$/, "MHz"], [/_deg$/, "°"], [/_ns$/, "N·s"],
  [/_sigma$/, "σ"], [/_mv_per_min$/, "mV/min"], [/_voltage$/, "V"],
];

function humanize(key: string): { label: string; unit: string } {
  let unit = "";
  let base = key;
  for (const [re, u] of UNITS) {
    if (re.test(key)) {
      unit = u;
      base = key.replace(re, "");
      break;
    }
  }
  const label = base.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  return { label: label.replace(/\bhz\b/i, "").trim(), unit };
}

function resolve(schema: JsonSchema, root: JsonSchema): JsonSchema {
  if (schema.$ref) {
    const name = schema.$ref.split("/").pop()!;
    return resolve(root.$defs![name], root);
  }
  if (schema.allOf?.length === 1) return resolve(schema.allOf[0], root);
  return schema;
}

function niceStep(min: number, max: number, integer: boolean) {
  if (integer) return 1;
  const raw = (max - min) / 200;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  return [1, 2, 5, 10].map((k) => k * p).find((s) => s >= raw) ?? p;
}

type Patch = Record<string, unknown>;

function setIn(obj: Patch, path: string[], value: unknown): Patch {
  const [head, ...rest] = path;
  if (!rest.length) return { ...obj, [head]: value };
  return { ...obj, [head]: setIn((obj[head] as Patch) ?? {}, rest, value) };
}

function getIn(obj: unknown, path: string[]): unknown {
  return path.reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Patch)[k] : undefined), obj);
}

function Field({
  path,
  schema,
  value,
  onChange,
  presets,
}: {
  path: string[];
  schema: JsonSchema;
  value: unknown;
  onChange: (path: string[], v: unknown) => void;
  presets: string[];
}) {
  const key = path[path.length - 1];
  const { label, unit } = humanize(key);
  const desc = schema.description;
  const id = path.join(".");

  if (key === "preset") {
    return (
      <div className="field">
        <label htmlFor={id}>Motor preset</label>
        <select id={id} value={String(value)} onChange={(e) => onChange(path, e.target.value)}>
          {presets.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        <div className="desc">Approximate curves - swap in thrustcurve.org data for real flights.</div>
      </div>
    );
  }
  if (schema.type === "boolean") {
    return (
      <div className="field">
        <label>{label}</label>
        <button
          className={`toggle ${value ? "on" : ""}`}
          onClick={() => onChange(path, !value)}
          aria-pressed={Boolean(value)}
          aria-label={label}
        />
        {desc && <div className="desc">{desc}</div>}
      </div>
    );
  }
  if (schema.enum) {
    return (
      <div className="field">
        <label htmlFor={id}>{label}</label>
        <select id={id} value={String(value)} onChange={(e) => onChange(path, e.target.value)}>
          {schema.enum.map((o) => (
            <option key={o}>{o}</option>
          ))}
        </select>
        {desc && <div className="desc">{desc}</div>}
      </div>
    );
  }
  const numeric = schema.type === "number" || schema.type === "integer";
  if (numeric) {
    const integer = schema.type === "integer";
    const min = schema.minimum ?? 0;
    const max = schema.maximum ?? (schema.exclusiveMaximum !== undefined ? schema.exclusiveMaximum - 1 : 100);
    const step = niceStep(min, max, integer);
    const num = Number(value);
    return (
      <div className="field">
        <label htmlFor={id}>
          {label} {unit && <span style={{ color: "var(--muted)" }}>({unit})</span>}
        </label>
        <input
          id={id}
          type="number"
          value={Number.isFinite(num) ? num : ""}
          min={min}
          max={max}
          step={step}
          onChange={(e) => e.target.value !== "" && onChange(path, integer ? parseInt(e.target.value) : parseFloat(e.target.value))}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={num}
          aria-label={label}
          onChange={(e) => onChange(path, integer ? parseInt(e.target.value) : parseFloat(e.target.value))}
        />
        {desc && <div className="desc">{desc}</div>}
      </div>
    );
  }
  // strings and nullable ints (seed)
  const nullableInt = schema.anyOf?.some((s) => s.type === "integer");
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type={nullableInt ? "number" : "text"}
        value={value === null || value === undefined ? "" : String(value)}
        placeholder={nullableInt ? "random" : ""}
        onChange={(e) => {
          const v = e.target.value;
          onChange(path, nullableInt ? (v === "" ? null : parseInt(v)) : v);
        }}
      />
      {desc && <div className="desc">{desc}</div>}
    </div>
  );
}

export default function SettingsDrawer({ onClose }: { onClose: () => void }) {
  const config = useStore((s) => s.config);
  const [draft, setDraft] = useState<Patch>({});
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<Patch>({});
  const timer = useRef<number>();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const values = useMemo(() => {
    if (!config) return {};
    let merged: Patch = config.values as Patch;
    const walk = (p: Patch, path: string[]) => {
      for (const [k, v] of Object.entries(p)) {
        if (v && typeof v === "object") walk(v as Patch, [...path, k]);
        else merged = setIn(merged, [...path, k], v);
      }
    };
    walk(draft, []);
    return merged;
  }, [config, draft]);

  if (!config) return null;
  const root = config.schema;

  const onChange = (path: string[], v: unknown) => {
    setDraft((d) => setIn(d, path, v));
    pending.current = setIn(pending.current, path, v);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      const patch = pending.current;
      pending.current = {};
      try {
        await api.patchConfig(patch);
        setError(null);
        setDraft({});
      } catch (e) {
        setError((e as Error).message);
      }
    }, 200);
  };

  const renderGroup = (schema: JsonSchema, path: string[]): JSX.Element[] => {
    const props = resolve(schema, root).properties ?? {};
    return Object.entries(props).map(([k, s]) => {
      const rs = resolve(s, root);
      const p = [...path, k];
      if (rs.properties) {
        return (
          <div key={p.join(".")}>
            <div className="sub-title">
              {k} {typeof getIn(values, [...p, "model"]) === "string" ? `· ${getIn(values, [...p, "model"])}` : ""}
            </div>
            {renderGroup(rs, p)}
          </div>
        );
      }
      if (k === "model") return <span key={p.join(".")} />;
      return (
        <Field
          key={p.join(".")}
          path={p}
          schema={rs}
          value={getIn(values, p)}
          onChange={onChange}
          presets={config.motor_presets}
        />
      );
    });
  };

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Settings">
        <div className="drawer-head">
          <h2>Simulation settings</h2>
          <div className="controls">
            <button
              className="btn sm ghost"
              onClick={() => api.resetConfig().then(() => setDraft({})).catch((e) => setError(e.message))}
            >
              Defaults
            </button>
            <button className="btn sm" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="drawer-body">
          {error && <div className="banner error">{error}</div>}
          {config.pending && (
            <div className="banner">Rocket/motor/recovery changes are queued - press RESET after landing to use them.</div>
          )}
          {SECTIONS.map((sec) => {
            const s = root.properties?.[sec.key];
            if (!s) return null;
            return (
              <details key={sec.key} className="section" open={sec.open}>
                <summary>{sec.title}</summary>
                <div className="section-note">{sec.note}</div>
                {renderGroup(s, [sec.key])}
              </details>
            );
          })}
        </div>
      </aside>
    </>
  );
}
