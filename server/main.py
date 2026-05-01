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
import sys
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
UPLOAD_TTL_DAYS = float(os.environ.get("CLAUDE_LENS_UPLOAD_TTL_DAYS", "7"))


def _cleanup_uploads(ttl_days: float) -> None:
    """Delete upload files older than `ttl_days`. 0 disables cleanup.

    Pasted images would otherwise pile up indefinitely in DATA_DIR/uploads.
    Old session jsonls may still reference them as `[image: /path]` — those
    references just stop resolving (browser shows broken thumbnail), which
    is acceptable since the user clearly opted into a TTL.
    """
    if ttl_days <= 0:
        return
    cutoff = time.time() - ttl_days * 86400
    for p in UPLOAD_DIR.glob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


_cleanup_uploads(UPLOAD_TTL_DAYS)


def _kill_orphan_listeners() -> None:
    """Kill any leftover listen.py processes from a previous server run.

    Listeners are spawned with start_new_session=True so they survive a
    server crash — but that means a fresh server can find an old listener
    still reading the FIFO and intercepting messages with stale code,
    producing the "two listeners race for one FIFO" bug.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude-lens.*bin/listen.py"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    for pid_str in result.stdout.split():
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, 15)  # SIGTERM
        except (OSError, ProcessLookupError):
            pass


_kill_orphan_listeners()

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


# TERM_PROGRAM is set by the terminal emulator on macOS. Map it to the .app
# name AppleScript uses for `tell application "..." to activate`.
_TERM_PROGRAM_TO_APP = {
    "Apple_Terminal": "Terminal",
    "iTerm.app": "iTerm",
    "ghostty": "Ghostty",
    "WezTerm": "WezTerm",
    "Alacritty": "Alacritty",
    "vscode": "Visual Studio Code",
    "tabby": "Tabby",
    "Hyper": "Hyper",
    "warp": "Warp",
    "kitty": "kitty",
}


def _detect_focus_app() -> str | None:
    """Pick the terminal app to bring to front before pasting.

    Override > auto-detect from TERM_PROGRAM. Empty string disables activation.
    """
    override = os.environ.get("CLAUDE_LENS_FOCUS")
    if override is not None:
        return override.strip() or None
    tp = os.environ.get("TERM_PROGRAM", "")
    return _TERM_PROGRAM_TO_APP.get(tp)


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
            focus = _detect_focus_app()
            log.write(
                f"\n[server] spawning listener at {time.strftime('%H:%M:%S')}"
                f" (focus={focus or 'none — current frontmost'})\n"
            )
            log.flush()
            env = os.environ.copy()
            env["CLAUDE_LENS_DATA"] = str(DATA_DIR)
            # Use the server's own python so the listener inherits the venv
            # (incl. PyObjC/Quartz on macOS, which we use for background paste).
            cmd = [sys.executable, str(LISTENER_SCRIPT)]
            if focus:
                cmd += ["--focus", focus]
            self.proc = subprocess.Popen(
                cmd,
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


# Path where Claude Code stores its own per-session JSONL transcripts. We
# read these (read-only) to recover the user's `/rename` custom title even
# when our own session file has been cleared — so the lens sidebar/title
# always reflects the conversation name without waiting for the next Stop
# hook to push it down.
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def find_claude_transcript(session_id: str) -> Path | None:
    if not session_id or session_id == "default":
        return None
    if not CLAUDE_PROJECTS_DIR.exists():
        return None
    matches = list(CLAUDE_PROJECTS_DIR.glob(f"*/{session_id}.jsonl"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def custom_title_from_transcript(session_id: str) -> str | None:
    """Return the latest /rename customTitle for a Claude Code session.

    Records look like:
        {"type": "custom-title", "customTitle": "...", "sessionId": "..."}
    """
    transcript = find_claude_transcript(session_id)
    if not transcript:
        return None
    last_title: str | None = None
    try:
        with transcript.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "custom-title":
                    t = rec.get("customTitle")
                    if t:
                        last_title = t
    except OSError:
        return None
    return last_title


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
        # Authoritative source: Claude Code's `/rename`. Falls back to any
        # label we previously stored, then to the raw session id.
        label = custom_title_from_transcript(f.stem) or last_label or f.stem
        out.append(
            {
                "id": f.stem,
                "label": label,
                "mtime": f.stat().st_mtime,
            }
        )
    return out


def _resolve_label(session_id: str, fallback: str | None) -> str | None:
    """Always prefer the live `/rename` title from Claude Code's transcript
    over what the client sent. Avoids the bug where Clear-ing the lens feed
    loses the label and new messages show the raw UUID until the next push.
    """
    title = custom_title_from_transcript(session_id)
    return title or fallback


@app.post("/push")
async def push(payload: PushPayload) -> dict[str, Any]:
    msg = {
        "session_id": payload.session_id,
        "session_label": _resolve_label(payload.session_id, payload.session_label),
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
        "session_label": _resolve_label(payload.session_id, payload.session_label),
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
