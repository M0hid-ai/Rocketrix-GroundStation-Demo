import type { ConfigPayload, FlightDoc, FlightListItem } from "./types";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  command: (action: string) => req<{ ok: boolean }>(`/api/command/${action}`, { method: "POST" }),
  patchConfig: (patch: object) =>
    req<ConfigPayload>("/api/config", { method: "PATCH", body: JSON.stringify(patch) }),
  resetConfig: () => req<ConfigPayload>("/api/config/reset", { method: "POST" }),
  flights: () => req<FlightListItem[]>("/api/flights"),
  flight: (id: string) => req<FlightDoc>(`/api/flights/${id}`),
  deleteFlight: (id: string) => req<{ ok: boolean }>(`/api/flights/${id}`, { method: "DELETE" }),
  csvUrl: (id: string) => `/api/flights/${id}/csv`,
};
