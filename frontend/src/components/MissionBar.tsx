import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { store, useStore } from "../lib/store";
import type { Phase } from "../lib/types";

const STAGES: { key: string; label: string; phases: Phase[] }[] = [
  { key: "PAD", label: "PAD", phases: ["IDLE", "ARMED"] },
  { key: "BOOST", label: "BOOST", phases: ["BOOST"] },
  { key: "COAST", label: "COAST", phases: ["COAST"] },
  { key: "APOGEE", label: "APOGEE", phases: [] },
  { key: "DROGUE", label: "DROGUE", phases: ["DROGUE"] },
  { key: "MAIN", label: "MAIN", phases: ["MAIN"] },
  { key: "LANDED", label: "LANDED", phases: ["LANDED"] },
];

const ORDER: Record<Phase, number> = { IDLE: 0, ARMED: 0, BOOST: 1, COAST: 2, DROGUE: 4, MAIN: 5, LANDED: 6 };

export function PhasePipeline() {
  const { phase, marks, tZero, apogeeTp, dual } = useStore((s) => ({
    phase: (s.latest?.st ?? s.status?.sim.phase ?? "IDLE") as Phase,
    marks: s.phaseMarks,
    tZero: s.tZero,
    apogeeTp: s.peaks.apogeeTp,
    dual: s.config?.values.recovery?.mode !== "single",
  }));
  const cur = ORDER[phase];
  const firstTime = (p: Phase) => {
    const m = marks.find((x) => x.phase === p);
    return m && tZero !== null ? `+${(m.t - tZero).toFixed(1)}s` : "";
  };
  return (
    <div className="pipeline">
      {STAGES.filter((s) => dual || s.key !== "DROGUE").map((s, i) => {
        const idx = STAGES.indexOf(s);
        const done = s.key === "APOGEE" ? cur >= 4 : idx < cur;
        const current = idx === cur;
        let time = "";
        if (s.key === "APOGEE") time = cur >= 4 && apogeeTp !== null ? `+${apogeeTp.toFixed(1)}s` : "";
        else if (s.key !== "PAD") time = firstTime(s.phases[0]);
        else time = phase === "ARMED" ? "armed" : "";
        return (
          <div key={s.key} className={`stage ${done ? "done" : ""} ${current ? "current" : ""}`} data-i={i}>
            <div className="stage-node" />
            <div className="stage-label">{s.label}</div>
            <div className="stage-time">{time}</div>
          </div>
        );
      })}
    </div>
  );
}

export function Controls({ onSettings }: { onSettings: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const { phase, countdown, scale, recording } = useStore((s) => ({
    phase: (s.status?.sim.phase ?? "IDLE") as Phase,
    countdown: s.status?.sim.countdown ?? null,
    scale: s.status?.sim.time_scale ?? 1,
    recording: s.status?.sim.recording ?? false,
  }));

  // Ending a flight can't be undone, so the first click only arms the button for a few seconds.
  useEffect(() => {
    if (!confirmEnd) return;
    const t = setTimeout(() => setConfirmEnd(false), 4000);
    return () => clearTimeout(t);
  }, [confirmEnd]);

  const run = async (action: string) => {
    setError(null);
    try {
      await api.command(action);
    } catch (e) {
      setError((e as Error).message);
      setTimeout(() => setError(null), 3000);
    }
  };
  const setScale = (v: number) => api.patchConfig({ sim: { time_scale: v } }).catch(() => {});

  const onPad = phase === "IDLE" || phase === "ARMED";
  const counting = countdown !== null;
  const inFlight = !onPad && recording;
  return (
    <div className="controls">
      {inFlight && (
        <button
          className={`btn danger ${confirmEnd ? "confirm" : ""}`}
          onClick={() => {
            if (!confirmEnd) return setConfirmEnd(true);
            setConfirmEnd(false);
            run("end");
          }}
          title="Stop the flight now and save a report from the data received so far"
        >
          {confirmEnd ? "CONFIRM END?" : "■ END FLIGHT"}
        </button>
      )}
      {phase === "IDLE" && (
        <button className="btn" onClick={() => run("arm")}>
          ARM
        </button>
      )}
      {phase === "ARMED" && !counting && (
        <button className="btn ghost" onClick={() => run("disarm")}>
          DISARM
        </button>
      )}
      {counting ? (
        <button className="btn danger" onClick={() => run("abort")}>
          ABORT
        </button>
      ) : (
        <button className="btn primary" disabled={!onPad} onClick={() => run("launch")}>
          LAUNCH
        </button>
      )}
      <button
        className="btn"
        disabled={!(onPad || phase === "LANDED") || counting}
        onClick={() => {
          store.clear();
          run("reset");
        }}
        title="Start a fresh simulated session"
      >
        RESET
      </button>
      <div className="seg" title="Simulation speed">
        {[1, 2, 5].map((v) => (
          <button key={v} className={scale === v ? "on" : ""} onClick={() => setScale(v)}>
            {v}×
          </button>
        ))}
      </div>
      <button className="btn ghost" onClick={onSettings} title="Simulation & sensor settings">
        ⚙ SETTINGS
      </button>
      {error && <span className="chip critical">⚠ {error}</span>}
    </div>
  );
}

export function CountdownOverlay() {
  const countdown = useStore((s) => s.status?.sim.countdown ?? null);
  if (countdown === null) return null;
  return (
    <div className="countdown">
      <div className="countdown-box">
        <div className="countdown-num">T−{Math.ceil(Math.max(0, countdown))}</div>
        <div className="countdown-label">LAUNCH SEQUENCE</div>
      </div>
    </div>
  );
}
