"""HTTP + WebSocket API. Serves the built dashboard from ``frontend/dist`` when present."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .engine import GroundStation

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("GS_DATA_DIR", ROOT / "backend" / "data"))
FRONTEND_DIST = ROOT / "frontend" / "dist"

station = GroundStation(DATA_DIR)


@asynccontextmanager
async def lifespan(_: FastAPI):
    station.start()
    yield
    await station.stop()


app = FastAPI(title="Rocket Ground Station", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "phase": station.sim.truth.phase}


@app.get("/api/status")
def status() -> dict[str, Any]:
    return station.status()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return station.config_payload()


@app.patch("/api/config")
def patch_config(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        station.update_config(patch)
    except ValidationError as exc:
        raise HTTPException(422, detail=json.loads(exc.json())) from exc
    return station.config_payload()


@app.post("/api/config/reset")
def reset_config() -> dict[str, Any]:
    from .config import Config
    station.update_config(Config().model_dump())
    return station.config_payload()


@app.post("/api/command/{action}")
def command(action: str) -> dict[str, Any]:
    result = station.command(action)
    if not result["ok"]:
        raise HTTPException(409, detail=result["error"])
    return result


@app.get("/api/flights")
def flights() -> list[dict[str, Any]]:
    return station.recorder.list()


@app.get("/api/flights/{flight_id}")
def flight(flight_id: str) -> dict[str, Any]:
    doc = station.recorder.load(flight_id)
    if doc is None:
        raise HTTPException(404, "flight not found")
    return doc


@app.get("/api/flights/{flight_id}/csv")
def flight_csv(flight_id: str) -> FileResponse:
    path = station.recorder.csv_path(flight_id)
    if path is None:
        raise HTTPException(404, "flight not found")
    return FileResponse(path, media_type="text/csv", filename=f"flight-{flight_id}.csv")


@app.delete("/api/flights/{flight_id}")
def delete_flight(flight_id: str) -> dict[str, Any]:
    if not station.recorder.delete(flight_id):
        raise HTTPException(404, "flight not found")
    return {"ok": True}


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    queue = station.subscribe()
    try:
        await socket.send_text(json.dumps({
            "type": "hello", "config": station.config_payload(), "status": station.status(),
            "history": [json.loads(m) for m in list(station.history)],
            "last_flight": station.last_flight,
        }))

        async def reader() -> None:
            while True:
                msg = json.loads(await socket.receive_text())
                if msg.get("type") == "ping":  # clock-offset / RTT probe
                    queue.put_nowait(json.dumps({"type": "pong", "id": msg.get("id"),
                                                 "ts": time.time() * 1000}))

        read_task = asyncio.create_task(reader())
        try:
            while True:
                if read_task.done():
                    break
                text = await queue.get()
                await socket.send_text(text)
        finally:
            read_task.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        station.unsubscribe(queue)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
