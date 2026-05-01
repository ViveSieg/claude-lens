"""claude-lens server.

POST /push          assistant reply from Stop hook → store + broadcast.
POST /input         browser → user message + named pipe.
POST /upload-image  pasted screenshot → disk; returns path.
GET/POST /session*  session CRUD.
WebSocket /ws/{id}  per-session live feed; spawns/teardowns listener.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA_DIR = Path(os.environ.get("CLAUDE_LENS_DATA", Path.home() / ".claude-lens"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DIR = DATA_DIR / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PIPE_PATH = DATA_DIR / "input.pipe"

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

app = FastAPI(title="claude-lens")


class PushPayload(BaseModel):
    session_id: str = "default"
    session_label: str | None = None
    role: str = "assistant"
    content: str
    ts: float | None = None


class InputPayload(BaseModel):
    text: str
    session_id: str = "default"
    session_label: str | None = None


class Hub:
    def __init__(self) -> None:
        self.clients: dict[str, set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()

    async def join(self, session_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.clients[session_id].add(ws)

    async def leave(self, session_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.clients[session_id].discard(ws)

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        async with self.lock:
            targets = list(self.clients[session_id])
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.leave(session_id, ws)

    async def total_clients(self) -> int:
        async with self.lock:
            return sum(len(s) for k, s in self.clients.items() if k != "__index__")


hub = Hub()


LISTENER_SCRIPT = ROOT.parent / "bin" / "listen.py"
LISTENER_LOG = DATA_DIR / "listen.log"
LISTENER_GRACE_SEC = float(os.environ.get("CLAUDE_LENS_LISTEN_GRACE", "30"))


class ListenerManager:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.stop_task: asyncio.Task | None = None
        self.lock = asyncio.Lock()

    def _alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    async def ensure_running(self) -> None:
        async with self.lock:
            if self.stop_task and not self.stop_task.done():
                self.stop_task.cancel()
                self.stop_task = None
            if self._alive():
                return
            if not LISTENER_SCRIPT.exists():
                return
            log = LISTENER_LOG.open("a", encoding="utf-8")
            log.write(f"\n[server] spawning listener at {time.strftime('%H:%M:%S')}\n")
            log.flush()
            env = os.environ.copy()
            env["CLAUDE_LENS_DATA"] = str(DATA_DIR)
            self.proc = subprocess.Popen(
                ["python3", str(LISTENER_SCRIPT)],
                stdout=log,
                stderr=log,
                env=env,
                start_new_session=True,
            )

    async def schedule_stop(self) -> None:
        async with self.lock:
            if not self._alive():
                return
            if self.stop_task and not self.stop_task.done():
                return
            self.stop_task = asyncio.create_task(self._delayed_stop())

    async def _delayed_stop(self) -> None:
        try:
            await asyncio.sleep(LISTENER_GRACE_SEC)
        except asyncio.CancelledError:
            return
        async with self.lock:
            if self._alive():
                try:
                    self.proc.terminate()
                except ProcessLookupError:
                    pass
                self.proc = None
                with LISTENER_LOG.open("a", encoding="utf-8") as f:
                    f.write(f"[server] listener stopped at {time.strftime('%H:%M:%S')}\n")


listener = ListenerManager()


def session_file(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
    return SESSION_DIR / f"{safe}.jsonl"


def append_session(session_id: str, message: dict[str, Any]) -> None:
    with session_file(session_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")


def load_session(session_id: str) -> list[dict[str, Any]]:
    p = session_file(session_id)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def list_sessions() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in sorted(SESSION_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        last_label = ""
        try:
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        msg = json.loads(line)
                        if msg.get("session_label"):
                            last_label = msg["session_label"]
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
        out.append(
            {
                "id": f.stem,
                "label": last_label or f.stem,
                "mtime": f.stat().st_mtime,
            }
        )
    return out


@app.post("/push")
async def push(payload: PushPayload) -> dict[str, Any]:
    msg = {
        "session_id": payload.session_id,
        "session_label": payload.session_label,
        "role": payload.role,
        "content": payload.content,
        "ts": payload.ts or time.time(),
    }
    append_session(payload.session_id, msg)
    await hub.broadcast(payload.session_id, {"type": "message", "message": msg})
    await hub.broadcast("__index__", {"type": "session_touch", "session": payload.session_id})
    return {"ok": True}


@app.post("/input")
async def push_input(payload: InputPayload) -> dict[str, Any]:
    msg = {
        "session_id": payload.session_id,
        "session_label": payload.session_label,
        "role": "user",
        "content": payload.text,
        "ts": time.time(),
    }
    append_session(payload.session_id, msg)
    await hub.broadcast(payload.session_id, {"type": "message", "message": msg})
    await hub.broadcast("__index__", {"type": "session_touch", "session": payload.session_id})

    if not PIPE_PATH.exists():
        try:
            os.mkfifo(PIPE_PATH)
        except FileExistsError:
            pass
        except OSError as e:
            return {"ok": True, "pipe": f"mkfifo failed: {e}"}
    try:
        fd = os.open(PIPE_PATH, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, (payload.text + "\n").encode("utf-8"))
        os.close(fd)
        return {"ok": True, "pipe": "delivered"}
    except OSError:
        return {"ok": True, "pipe": "no consumer"}


@app.post("/session/{session_id}/label")
async def rename_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    label = str(payload.get("label", "")).strip()
    if not label:
        return JSONResponse({"ok": False, "error": "label required"}, status_code=400)
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
    if not session_file(safe).exists():
        return JSONResponse({"ok": False, "error": "session not found"}, status_code=404)
    meta = {
        "session_id": safe,
        "session_label": label,
        "role": "system",
        "content": f"_renamed at {time.strftime('%Y-%m-%d %H:%M:%S')}_",
        "ts": time.time(),
    }
    append_session(safe, meta)
    await hub.broadcast(safe, {"type": "label_changed", "label": label})
    await hub.broadcast("__index__", {"type": "session_touch", "session": safe})
    return {"ok": True, "label": label}


@app.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    session_id: str = Form("default"),
) -> dict[str, Any]:
    """Receive a pasted/dropped image, save to disk, return its path."""
    name = file.filename or "image.png"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ".png"
    if ext not in ALLOWED_IMAGE_EXT:
        ext = ".png"
    safe_session = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rand = secrets.token_hex(3)
    out = UPLOAD_DIR / f"{safe_session}-{stamp}-{rand}{ext}"
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return JSONResponse({"ok": False, "error": "file too large"}, status_code=413)
    out.write_bytes(data)
    return {
        "ok": True,
        "path": str(out),
        "size": len(data),
        "filename": out.name,
    }


@app.get("/uploads/{name}")
async def get_upload(name: str) -> Any:
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    p = UPLOAD_DIR / safe
    if not p.exists() or not p.is_file():
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return FileResponse(p)


@app.post("/session")
async def create_session(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or "").strip()
    label = payload.get("session_label") or session_id
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    if not safe:
        return JSONResponse({"ok": False, "error": "invalid session_id"}, status_code=400)
    path = session_file(safe)
    if not path.exists():
        seed = {
            "session_id": safe,
            "session_label": label,
            "role": "system",
            "content": f"_session created at {time.strftime('%Y-%m-%d %H:%M:%S')}_",
            "ts": time.time(),
        }
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(seed, ensure_ascii=False) + "\n")
    return {"ok": True, "session_id": safe, "label": label}


@app.get("/sessions")
async def get_sessions() -> dict[str, Any]:
    return {"sessions": list_sessions()}


@app.get("/session/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    return {"session_id": session_id, "messages": load_session(session_id)}


@app.delete("/session/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    p = session_file(session_id)
    if p.exists():
        p.unlink()
    return {"ok": True}


@app.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    await hub.join(session_id, websocket)
    if session_id != "__index__":
        await listener.ensure_running()
    try:
        await websocket.send_json({"type": "ready", "session_id": session_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(session_id, websocket)
        if session_id != "__index__" and await hub.total_clients() == 0:
            await listener.schedule_stop()


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "data_dir": str(DATA_DIR)}


def main() -> None:
    import uvicorn

    host = os.environ.get("CLAUDE_LENS_HOST", "127.0.0.1")
    port = int(os.environ.get("CLAUDE_LENS_PORT", "7456"))
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
