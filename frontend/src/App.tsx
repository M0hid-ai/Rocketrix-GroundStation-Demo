import { useEffect, useState } from "react";
import FlightsView from "./components/FlightsView";
import Login from "./components/Login";
import LiveChart, { type SeriesDef } from "./components/LiveChart";
import { Controls, CountdownOverlay, PhasePipeline } from "./components/MissionBar";
import SettingsDrawer from "./components/SettingsDrawer";
import { AttitudePanel, EventLog, GroundTrack, LinkPanel } from "./components/SidePanels";
import Tiles, { Alerts } from "./components/Tiles";
import { api, LOGGED_OUT } from "./lib/api";
import { store, useStore } from "./lib/store";

// canvas needs literal colours: validated categorical slots 1-3 + neutral grey for reference
const S1 = "#3987e5";
const S2 = "#d95926";
const S3 = "#199e70";
const REF = "#8793a3";

const ALT: SeriesDef[] = [
  { key: "h", label: "Kalman", color: S1, width: 2.5 },
  { key: "ab", label: "Baro raw", color: S2, width: 1.25 },
  { key: "hg", label: "GPS", color: S3, width: 1.25 },
  { key: "th", label: "Sim truth", color: REF, dash: true, width: 1.25 },
];
const VEL: SeriesDef[] = [
  { key: "v", label: "Kalman", color: S1 },
  { key: "tv", label: "Sim truth", color: REF, dash: true, width: 1.25 },
];
const ACC: SeriesDef[] = [{ key: "ax", label: "Axial (IMU)", color: S2 }];
const TEMP: SeriesDef[] = [{ key: "tc", label: "Temperature", color: S3 }];
const PRES: SeriesDef[] = [{ key: "p", label: "Pressure", color: S1 }];
const RSSI: SeriesDef[] = [{ key: "rssi", label: "RSSI", color: S3 }];

const WINDOWS: [number, string][] = [
  [30, "30s"],
  [60, "1m"],
  [180, "3m"],
  [0, "All"],
];

function MissionClock() {
  const { m, st } = useStore((s) => ({ m: s.latest, st: s.status }));
  let main = "T−00:00.0";
  let sub = "on pad";
  const cd = st?.sim.countdown;
  const fmt = (x: number) => {
    const a = Math.abs(x);
    return `${String(Math.floor(a / 60)).padStart(2, "0")}:${(a % 60).toFixed(1).padStart(4, "0")}`;
  };
  if (cd !== null && cd !== undefined) {
    main = `T−${fmt(cd)}`;
    sub = "countdown";
  } else if (m?.tp !== null && m?.tp !== undefined) {
    main = `T+${fmt(m.tp)}`;
    sub = m.st === "LANDED" ? "flight complete" : "mission elapsed";
  }
  return (
    <div className="clock">
      <div className="clock-main">{main}</div>
      <div className="clock-sub">
        {sub} · FC clock {m ? m.t.toFixed(1) : "—"} s
      </div>
    </div>
  );
}

function Connection() {
  const { connected, clients } = useStore((s) => ({ connected: s.connected, clients: s.status?.clients ?? 0 }));
  return (
    <div className="conn">
      <span className={`dot ${connected ? "good" : "bad"}`} />
      {connected ? `Live · ${clients} viewer${clients === 1 ? "" : "s"}` : "Reconnecting…"}
    </div>
  );
}

function LiveView({ onSettings }: { onSettings: () => void }) {
  const [win, setWin] = useState(60);
  return (
    <>
      <div className="mission-bar">
        <div className="panel">
          <PhasePipeline />
        </div>
        <div className="panel" style={{ display: "flex", alignItems: "center" }}>
          <Controls onSettings={onSettings} />
        </div>
      </div>
      <Alerts />
      <Tiles />
      <div className="live-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="controls" style={{ justifyContent: "space-between" }}>
            <span className="panel-title" style={{ margin: 0 }}>
              Live telemetry
            </span>
            <div className="seg" title="Chart time window">
              {WINDOWS.map(([v, l]) => (
                <button key={v} className={win === v ? "on" : ""} onClick={() => setWin(v)}>
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div className="charts">
            <LiveChart title="Altitude" unit="m" series={ALT} windowSec={win} />
            <LiveChart title="Vertical velocity" unit="m/s" series={VEL} windowSec={win} />
            <LiveChart title="Acceleration" unit="g" series={ACC} windowSec={win} decimals={2} hint="body axis" />
            <LiveChart title="Barometric pressure" unit="Pa" series={PRES} windowSec={win} decimals={0} />
            <LiveChart title="Temperature" unit="°C" series={TEMP} windowSec={win} decimals={2} />
            <LiveChart title="Signal strength" unit="dBm" series={RSSI} windowSec={win} decimals={0} />
          </div>
        </div>
        <div className="side">
          <LinkPanel />
          <AttitudePanel />
          <GroundTrack />
          <EventLog />
        </div>
      </div>
    </>
  );
}

export default function App() {
  // undefined = still checking the session cookie, null = logged out
  const [user, setUser] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    api.me().then((r) => setUser(r.user), () => setUser(null));
    const onLoggedOut = () => {
      store.disconnect();
      setUser(null);
    };
    window.addEventListener(LOGGED_OUT, onLoggedOut);
    return () => window.removeEventListener(LOGGED_OUT, onLoggedOut);
  }, []);

  if (user === undefined) return null;
  if (user === null) return <Login onLogin={setUser} />;
  return (
    <Dashboard
      user={user}
      onLogout={() => {
        store.disconnect();
        api.logout().finally(() => setUser(null));
      }}
    />
  );
}

function Dashboard({ user, onLogout }: { user: string; onLogout: () => void }) {
  const [tab, setTab] = useState<"live" | "flights">("live");
  const [settings, setSettings] = useState(false);
  const [toast, setToast] = useState<{ id: string; apogee?: number } | null>(null);
  const [focus, setFocus] = useState<string | null>(null);

  useEffect(() => {
    store.connect();
    return store.onFlightComplete((f) => {
      setToast({ id: f.id, apogee: f.summary.apogee_m });
      setTimeout(() => setToast(null), 10000);
    });
  }, []);

  return (
    <>
      <header className="header">
        <div className="brand">
          <img src="/favicon.svg" width={28} height={28} alt="" />
          <div>
            <div className="brand-title">GROUND STATION</div>
            <div className="brand-sub">L1 ROCKET TELEMETRY</div>
          </div>
          <span className="mode-badge">SIM</span>
        </div>
        <nav className="tabs">
          <button className={`tab ${tab === "live" ? "active" : ""}`} onClick={() => setTab("live")}>
            Live
          </button>
          <button className={`tab ${tab === "flights" ? "active" : ""}`} onClick={() => setTab("flights")}>
            Flight reports
          </button>
        </nav>
        <Connection />
        <MissionClock />
        <div className="user-chip">
          {user}
          <button className="btn sm ghost" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>
      <main className="page">
        {tab === "live" ? <LiveView onSettings={() => setSettings(true)} /> : <FlightsView focusId={focus} />}
      </main>
      <CountdownOverlay />
      {settings && <SettingsDrawer onClose={() => setSettings(false)} />}
      {toast && (
        <div className="toast">
          Flight complete - apogee <b className="mono">{toast.apogee} m</b>{" "}
          <button
            className="btn sm primary"
            style={{ marginLeft: 10 }}
            onClick={() => {
              setFocus(toast.id);
              setTab("flights");
              setToast(null);
            }}
          >
            View report
          </button>
        </div>
      )}
    </>
  );
}
