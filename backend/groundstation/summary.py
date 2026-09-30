"""Post-flight analysis built only from data received on the ground."""

from __future__ import annotations

import math
import statistics
from typing import Any

SERIES_KEYS = ("tp", "h", "ab", "hg", "v", "a", "ax", "p", "tc", "bat", "rssi", "tl", "th")


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def summarise(rows: list[dict[str, Any]], link: dict[str, Any] | None = None,
              truth: dict[str, Any] | None = None) -> dict[str, Any]:
    flight = [r for r in rows if r.get("tp") is not None]
    if not flight:
        return {"valid": False}

    def rows_in(state: str) -> list[dict[str, Any]]:
        return [r for r in flight if r["st"] == state]

    apogee_row = max(flight, key=lambda r: r["h"])
    boost = rows_in("BOOST")
    landed = rows_in("LANDED")
    drogue, main = rows_in("DROGUE"), rows_in("MAIN")

    def settled_descent(rs: list[dict[str, Any]]) -> float | None:
        if not rs:
            return None
        t0 = rs[0]["tp"]
        return _median([-r["v"] for r in rs if r["tp"] - t0 > 2.0])

    phases: list[dict[str, Any]] = []
    for r in rows:
        if not phases or phases[-1]["state"] != r["st"]:
            phases.append({"state": r["st"], "tp": r.get("tp"), "alt": round(r["h"], 1)})

    last_pos = next((r for r in reversed(flight) if r.get("e") is not None), None)
    temps = [r["tc"] for r in flight if r.get("tc") is not None]
    bats = [r["bat"] for r in rows if r.get("bat")]
    ax = [r["ax"] for r in flight if r.get("ax") is not None]
    landing = [-r["v"] for r in main if landed and 0 < landed[0]["tp"] - r["tp"] < 3]

    out: dict[str, Any] = {
        "valid": True,
        "apogee_m": round(apogee_row["h"], 1),
        "apogee_baro_m": round(max((r["ab"] for r in flight if r.get("ab") is not None),
                                   default=0.0), 1),
        "apogee_gps_m": round(max((r["hg"] for r in flight if r.get("hg") is not None),
                                  default=0.0), 1),
        "time_to_apogee_s": round(apogee_row["tp"], 2),
        "max_velocity_mps": round(max(r["v"] for r in flight), 1),
        "max_accel_g": round(max(ax), 2) if ax else None,
        "burn_time_s": round(boost[-1]["tp"], 2) if boost else None,
        "drogue_descent_mps": settled_descent(drogue),
        "main_descent_mps": settled_descent(main),
        "landing_velocity_mps": _median(landing),
        "flight_time_s": round(landed[0]["tp"], 1) if landed else round(flight[-1]["tp"], 1),
        "drift_m": round(math.hypot(last_pos["e"], last_pos["n"]), 1) if last_pos else None,
        "min_temp_c": round(min(temps), 2) if temps else None,
        "max_temp_c": round(max(temps), 2) if temps else None,
        "min_battery_v": round(min(bats), 3) if bats else None,
        "phases": phases,
        "link": link or {},
    }
    if truth:
        out["truth"] = truth
        if truth.get("apogee_m"):
            out["apogee_error_m"] = round(out["apogee_m"] - truth["apogee_m"], 2)
    return out


def downsample(rows: list[dict[str, Any]], max_points: int = 2500) -> dict[str, list]:
    """Column-oriented series for charts, thinned but keeping peaks visible."""
    flight = [r for r in rows if r.get("tp") is not None]
    step = max(1, math.ceil(len(flight) / max_points))
    picked = flight[::step]
    if flight and picked[-1] is not flight[-1]:
        picked.append(flight[-1])
    series: dict[str, list] = {k: [r.get(k) for r in picked] for k in SERIES_KEYS}
    series["st"] = [r["st"] for r in picked]
    return series
