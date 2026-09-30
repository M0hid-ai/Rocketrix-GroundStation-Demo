"""HTTP + WebSocket API. Serves the built dashboard from ``frontend/dist`` when present."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from .auth import COOKIE, SESSION_TTL_S, Auth
from .engine import GroundStation

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("GS_DATA_DIR", ROOT / "backend" / "data"))
FRONTEND_DIST = ROOT / "frontend" / "dist"
USERS_FILE = Path(os.environ.get("GS_USERS_FILE", ROOT / "backend" / "users.txt"))

log = logging.getLogger("uvicorn.error")  # shows up in the server output
station = GroundStation(DATA_DIR)
auth = Auth.from_environment(USERS_FILE, DATA_DIR)
if not auth.users:
    log.warning("No users configured (GS_USERS or %s): nobody can log in", USERS_FILE)

# Everything under /api and the API docs needs a session, except these.
PUBLIC_API = {"/api/health", "/api/auth/login", "/api/auth/logout"}
PROTECTED_PREFIXES = ("/api/", "/docs", "/redoc", "/openapi.json")


@asynccontextmanager
async def lifespan(_: FastAPI):
    station.start()
    yield
    await station.stop()


app = FastAPI(title="Rocket Ground Station", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith(PROTECTED_PREFIXES) and path not in PUBLIC_API:
        user = auth.verify(request.cookies.get(COOKIE))
        if user is None:
            return JSONResponse({"detail": "not logged in"}, status_code=401)
        request.state.user = user
    return await call_next(request)


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: Login, request: Request, response: Response) -> dict[str, Any]:
    client = request.client.host if request.client else "?"
    if auth.rate_limited(client):
        raise HTTPException(429, "too many failed logins, try again in a few minutes")
    if not auth.check_password(body.username, body.password):
        auth.record_failure(client)
        log.warning("failed login for %r from %s", body.username, client)
        raise HTTPException(401, "wrong username or password")
    response.set_cookie(COOKIE, auth.issue(body.username), max_age=SESSION_TTL_S, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https")
    log.info("%s logged in from %s", body.username, client)
    return {"user": body.username}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request) -> dict[str, Any]:
    return {"user": request.state.user}


@app.api_route("/api/health", methods=["GET", "HEAD"])  # HEAD for uptime monitors
def health() -> dict[str, Any]:
    return {"ok": True}


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
def command(action: str, request: Request) -> dict[str, Any]:
    log.info("%s: command %s", request.state.user, action)
    result = station.command(action, user=request.state.user)
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
    # Browsers send cookies on WebSocket handshakes from any site, so also check the origin.
    origin = socket.headers.get("origin")
    hosts = {socket.headers.get("host"), socket.headers.get("x-forwarded-host")}  # tunnels/proxies
    same_origin = origin is None or origin.split("://", 1)[-1] in hosts
    if not same_origin:
        await socket.close()  # rejects the handshake (HTTP 403)
        return
    await socket.accept()
    if auth.verify(socket.cookies.get(COOKIE)) is None:
        await socket.close(code=4401)  # accepted first so the browser sees the code
        return
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
