"""Flight recordings: every received frame is kept and saved as CSV + JSON summary on landing."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .summary import downsample, summarise

CSV_FIELDS = ["seq", "t", "tp", "st", "p", "tc", "ab", "h", "v", "a", "ax", "al", "rr", "tl",
              "gf", "lat", "lon", "hg", "e", "n", "sat", "bat", "rssi", "snr", "lk", "th", "tv"]
_ID_RE = re.compile(r"^[0-9A-Za-z_-]+$")


class FlightRecorder:
    def __init__(self, data_dir: Path):
        self.dir = data_dir / "flights"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rows: list[dict[str, Any]] = []
        self.flight_id: str | None = None
        self.started_at: str | None = None

    @property
    def active(self) -> bool:
        return self.flight_id is not None

    def start(self) -> None:
        now = datetime.now()
        self.flight_id = now.strftime("%Y%m%d-%H%M%S")
        self.started_at = now.isoformat(timespec="seconds")
        self.rows = []

    def add(self, row: dict[str, Any]) -> None:
        if self.active:
            self.rows.append(row)

    def finish(self, meta: dict[str, Any], link: dict[str, Any],
               truth: dict[str, Any] | None,
               end: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self.active:
            return None
        summary = summarise(self.rows, link, truth)
        if end:
            summary.update(end)
        doc = {"id": self.flight_id, "started_at": self.started_at, "meta": meta,
               "summary": summary, "series": downsample(self.rows)}
        with open(self.dir / f"{self.flight_id}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(self.rows)
        (self.dir / f"{self.flight_id}.json").write_text(json.dumps(doc))
        self.flight_id = None
        return doc

    def cancel(self) -> None:
        self.flight_id = None
        self.rows = []

    # ------------------------------------------------------------------ archive
    def list(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(self.dir.glob("*.json"), reverse=True):
            try:
                doc = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            s = doc.get("summary", {})
            out.append({"id": doc["id"], "started_at": doc.get("started_at"),
                        "name": doc.get("meta", {}).get("rocket"),
                        "motor": doc.get("meta", {}).get("motor"),
                        "apogee_m": s.get("apogee_m"), "flight_time_s": s.get("flight_time_s"),
                        "ended_early": s.get("ended_early", False)})
        return out

    def load(self, flight_id: str) -> dict[str, Any] | None:
        if not _ID_RE.match(flight_id):
            return None
        path = self.dir / f"{flight_id}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def csv_path(self, flight_id: str) -> Path | None:
        if not _ID_RE.match(flight_id):
            return None
        path = self.dir / f"{flight_id}.csv"
        return path if path.exists() else None

    def delete(self, flight_id: str) -> bool:
        if not _ID_RE.match(flight_id):
            return False
        found = False
        for ext in ("json", "csv"):
            p = self.dir / f"{flight_id}.{ext}"
            if p.exists():
                p.unlink()
                found = True
        return found
