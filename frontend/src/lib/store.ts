/**
 * Telemetry store + WebSocket client.
 *
 * Latency-critical path: every message is written into column buffers the moment it arrives.
 * Rendering is decoupled: charts pull from the buffers on requestAnimationFrame and React
 * widgets re-render at most ~20 times a second, so a 100 Hz stream never floods React.
 */
import { useSyncExternalStore } from "react";
import { LOGGED_OUT } from "./api";
import type {
  ConfigPayload,
  EventMsg,
  FlightDoc,
  Phase,
  StatusMsg,
  TelemetryMsg,
} from "./types";

export const SERIES = ["t", "h", "ab", "hg", "th", "v", "tv", "a", "ax", "p", "tc", "bat", "rssi"] as const;
export type SeriesKey = (typeof SERIES)[number];

const MAX_POINTS = 60_000;

export interface Peaks {
  maxAlt: number;
  maxVel: number;
  maxAccelG: number;
  apogeeTp: number | null;
}

export interface Latency {
  radioMs: number; // simulated radio time-on-air + serial
  groundMs: number; // ground station -> this browser
  rttMs: number | null;
}

class Store {
  cols: Record<SeriesKey, (number | null)[]> = Object.fromEntries(
    SERIES.map((k) => [k, []]),
  ) as unknown as Record<SeriesKey, (number | null)[]>;
  latest: TelemetryMsg | null = null;
  status: StatusMsg | null = null;
  config: ConfigPayload | null = null;
  events: EventMsg[] = [];
  track: { e: number; n: number }[] = [];
  peaks: Peaks = { maxAlt: 0, maxVel: 0, maxAccelG: 0, apogeeTp: null };
  tZero: number | null = null; // flight computer time at launch
  phaseMarks: { t: number; phase: Phase }[] = [];
  lastFlight: FlightDoc | null = null;
  connected = false;
  latency: Latency = { radioMs: 0, groundMs: 0, rttMs: null };
  clockOffset = 0; // server clock - local clock (ms)
  msgRate = 0;

  version = 0; // bumps (throttled) when widgets should re-render
  dataVersion = 0; // bumps on every telemetry frame
  private listeners = new Set<() => void>();
  private dirty = false;
  private lastEmit = 0;
  private ws: WebSocket | null = null;
  private pingSent = new Map<number, number>();
  private pingId = 0;
  private rateCount = 0;
  private flightListeners = new Set<(f: FlightDoc) => void>();

  constructor() {
    const loop = (now: number) => {
      if (this.dirty && now - this.lastEmit > 50) {
        this.dirty = false;
        this.lastEmit = now;
        this.version++;
        this.listeners.forEach((l) => l());
      }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
    setInterval(() => {
      this.msgRate = this.rateCount;
      this.rateCount = 0;
      this.ping();
    }, 1000);
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  onFlightComplete(fn: (f: FlightDoc) => void) {
    this.flightListeners.add(fn);
    return () => {
      this.flightListeners.delete(fn);
    };
  }

  private touch() {
    this.dirty = true;
  }

  connect() {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return; // already connected/connecting
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws = ws;
    ws.onopen = () => {
      this.connected = true;
      this.touch();
      this.ping();
    };
    ws.onclose = (ev) => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.connected = false;
      this.touch();
      if (ev.code === 4401) window.dispatchEvent(new Event(LOGGED_OUT)); // session gone: stop retrying
      else setTimeout(() => this.connect(), 1000);
    };
    ws.onmessage = (ev) => this.handle(JSON.parse(ev.data));
  }

  disconnect() {
    const ws = this.ws;
    this.ws = null;
    this.connected = false;
    ws?.close();
    this.touch();
  }

  private ping() {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const id = ++this.pingId;
    this.pingSent.set(id, performance.now());
    this.ws.send(JSON.stringify({ type: "ping", id }));
  }

  clear() {
    SERIES.forEach((k) => (this.cols[k].length = 0));
    this.latest = null;
    this.track = [];
    this.events = [];
    this.peaks = { maxAlt: 0, maxVel: 0, maxAccelG: 0, apogeeTp: null };
    this.tZero = null;
    this.phaseMarks = [];
    this.dataVersion++;
    this.touch();
  }

  private handle(m: any) {
    switch (m.type) {
      case "tm":
        this.ingest(m as TelemetryMsg, true);
        break;
      case "status":
        this.status = m;
        this.touch();
        break;
      case "event":
        this.events.push(m);
        if (this.events.length > 300) this.events.shift();
        this.touch();
        break;
      case "config":
        this.config = m.config;
        this.touch();
        break;
      case "hello":
        this.clear();
        this.config = m.config;
        this.status = m.status;
        this.lastFlight = m.last_flight;
        for (const h of m.history) {
          if (h.type === "tm") this.ingest(h, false);
          else if (h.type === "event") this.events.push(h);
        }
        this.touch();
        break;
      case "reset":
        this.clear();
        break;
      case "flight_complete":
        this.lastFlight = m.flight;
        this.flightListeners.forEach((l) => l(m.flight));
        this.touch();
        break;
      case "pong": {
        const sent = this.pingSent.get(m.id);
        this.pingSent.delete(m.id);
        if (sent !== undefined) {
          const rtt = performance.now() - sent;
          // server stamped the pong half an RTT ago (NTP-style estimate)
          const offset = m.ts - (Date.now() - rtt / 2);
          this.clockOffset = this.latency.rttMs === null ? offset : 0.8 * this.clockOffset + 0.2 * offset;
          this.latency.rttMs = rtt;
        }
        break;
      }
    }
  }

  private ingest(m: TelemetryMsg, live: boolean) {
    const c = this.cols;
    for (const k of SERIES) c[k].push((m as any)[k] ?? null);
    if (c.t.length > MAX_POINTS * 1.1) {
      const drop = c.t.length - MAX_POINTS;
      for (const k of SERIES) c[k].splice(0, drop);
    }
    const prev = this.latest;
    if (!prev || prev.st !== m.st) this.phaseMarks.push({ t: m.t, phase: m.st });
    if (m.tp !== null && this.tZero === null) this.tZero = m.t - m.tp;
    if (m.e !== null && m.n !== null && m.gf) {
      const last = this.track[this.track.length - 1];
      if (!last || last.e !== m.e || last.n !== m.n) this.track.push({ e: m.e, n: m.n });
    }
    if (m.tp !== null) {
      const p = this.peaks;
      if (m.h > p.maxAlt) {
        p.maxAlt = m.h;
        p.apogeeTp = m.tp;
      }
      p.maxVel = Math.max(p.maxVel, m.v);
      p.maxAccelG = Math.max(p.maxAccelG, m.ax);
    }
    this.latest = m;
    if (live) {
      this.rateCount++;
      this.latency.radioMs = m.lk;
      const g = Date.now() + this.clockOffset - m.ts;
      this.latency.groundMs = 0.9 * this.latency.groundMs + 0.1 * Math.max(0, g);
    }
    this.dataVersion++;
    this.touch();
  }
}

export const store = new Store();

/** Re-render (throttled to ~20 Hz) whenever the store changes. */
export function useStore<T>(select: (s: Store) => T): T {
  useSyncExternalStore(store.subscribe, () => store.version);
  return select(store);
}

export function formatT(t: number, tZero: number | null): string {
  if (tZero === null) return `${t.toFixed(1)}s`;
  const d = t - tZero;
  return `T${d < 0 ? "−" : "+"}${Math.abs(d).toFixed(1)}`;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Locale-independent HH:MM:SS (some Linux locales make Intl throw). */
export function clockTime(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function dateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
