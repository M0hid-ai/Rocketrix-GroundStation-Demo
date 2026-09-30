export const PHASES = ["IDLE", "ARMED", "BOOST", "COAST", "DROGUE", "MAIN", "LANDED"] as const;
export type Phase = (typeof PHASES)[number];

/** One decoded + fused telemetry frame, as pushed by the ground station. */
export interface TelemetryMsg {
  type: "tm";
  seq: number;
  t: number; // flight computer clock (s)
  tp: number | null; // T+ since launch (s)
  st: Phase;
  p: number; // pressure Pa
  tc: number; // temperature C
  ab: number | null; // barometric altitude (raw) m
  h: number; // Kalman altitude m
  v: number; // Kalman vertical velocity m/s
  a: number; // Kalman vertical acceleration m/s^2
  ax: number; // axial accel g
  al: number; // lateral accel g
  rr: number; // roll rate deg/s
  tl: number; // tilt deg
  gf: boolean;
  lat: number;
  lon: number;
  hg: number | null; // GPS altitude above pad
  e: number | null;
  n: number | null;
  rng: number | null;
  sat: number;
  bat: number;
  rssi: number;
  snr: number;
  lk: number; // radio link latency ms
  ts: number; // server wall clock when sent (ms)
  th: number | null; // sim truth altitude
  tv: number | null;
}

export interface LinkStatus {
  rx: number;
  sent: number;
  lost_radio: number;
  skipped_busy: number;
  corrupted: number;
  crc_errors: number;
  seq_gaps: number;
  loss_pct: number;
  rx_rate: number;
  rssi: number;
  snr: number;
  airtime_ms: number;
  utilisation: number;
  max_rate_hz: number | null;
  frame_bytes: number;
  last_rx_age_ms: number | null;
}

export interface StatusMsg {
  type: "status";
  sim: {
    phase: Phase;
    t: number;
    countdown: number | null;
    time_scale: number;
    recording: boolean;
    pending_config: boolean;
  };
  link: LinkStatus;
  kalman: { rejected: number; enabled: boolean };
  clients: number;
  ts: number;
}

export interface EventMsg {
  type: "event";
  text: string;
  level: "info" | "warn" | "error" | "success";
  source: "ground" | "sim";
  tp: number | null;
  ts: number;
}

export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  minimum?: number;
  maximum?: number;
  exclusiveMaximum?: number;
  enum?: string[];
  const?: string;
  default?: unknown;
  properties?: Record<string, JsonSchema>;
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  anyOf?: JsonSchema[];
  allOf?: JsonSchema[];
}

export type ConfigValues = Record<string, Record<string, unknown>>;

export interface ConfigPayload {
  values: ConfigValues;
  motor_presets: string[];
  schema: JsonSchema;
  pending: boolean;
}

export interface FlightSummary {
  valid: boolean;
  apogee_m?: number;
  apogee_baro_m?: number;
  apogee_gps_m?: number;
  time_to_apogee_s?: number;
  max_velocity_mps?: number;
  max_accel_g?: number | null;
  burn_time_s?: number | null;
  drogue_descent_mps?: number | null;
  main_descent_mps?: number | null;
  landing_velocity_mps?: number | null;
  flight_time_s?: number;
  drift_m?: number | null;
  min_temp_c?: number | null;
  max_temp_c?: number | null;
  min_battery_v?: number | null;
  apogee_error_m?: number;
  /** set when an operator pressed END FLIGHT instead of waiting for landing */
  ended_early?: boolean;
  ended_in?: Phase;
  ended_by?: string | null;
  phases?: { state: Phase; tp: number | null; alt: number }[];
  link?: Partial<LinkStatus> & { attempted?: number };
  truth?: Record<string, number | null>;
}

export interface FlightDoc {
  id: string;
  started_at: string;
  meta: { rocket: string; motor: string; source: string; config: ConfigValues };
  summary: FlightSummary;
  series: Record<string, (number | null)[]> & { st: Phase[] };
}

export interface FlightListItem {
  id: string;
  started_at: string;
  name: string;
  motor: string;
  apogee_m: number | null;
  flight_time_s: number | null;
  ended_early?: boolean;
}
