"""claude-iris server.

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

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA_DIR = Path(os.environ.get("CLAUDE_IRIS_DATA", Path.home() / ".claude-iris"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DIR = DATA_DIR / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PIPE_PATH = DATA_DIR / "input.pipe"

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
UPLOAD_TTL_DAYS = float(os.environ.get("CLAUDE_IRIS_UPLOAD_TTL_DAYS", "7"))
SESSION_TTL_DAYS = float(os.environ.get("CLAUDE_IRIS_SESSION_TTL_DAYS", "30"))


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


def _cleanup_sessions(ttl_days: float) -> None:
    """Delete session jsonls untouched for `ttl_days`. 0 disables.

    Each new Claude conversation gets its own session file; without a TTL
    the sidebar fills with months-old sessions the user no longer cares
    about. Backfill from transcripts means a stale session can always be
    rebuilt if needed — the file isn't load-bearing.

    Tombstone (`.deleted`) files for hard-deleted sessions are also pruned
    here under the same TTL — without that, every session the user ever
    deleted leaves a zero-byte marker in the dir forever.
    """
    if ttl_days <= 0:
        return
    cutoff = time.time() - ttl_days * 86400
    for pattern in ("*.jsonl", "*.deleted"):
        for p in SESSION_DIR.glob(pattern):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass


_cleanup_sessions(SESSION_TTL_DAYS)


def _kill_orphan_listeners() -> None:
    """Kill any leftover listen.py processes from a previous server run.

    Listeners are spawned with start_new_session=True so they survive a
    server crash — but that means a fresh server can find an old listener
    still reading the FIFO and intercepting messages with stale code,
    producing the "two listeners race for one FIFO" bug.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude-iris.*bin/listen.py"],
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

CLEANUP_INTERVAL_SEC = float(os.environ.get("CLAUDE_IRIS_CLEANUP_INTERVAL", "21600"))  # 6h
POLL_INTERVAL_SEC = float(os.environ.get("CLAUDE_IRIS_POLL_INTERVAL", "2"))
POLL_RECENT_WINDOW_SEC = float(os.environ.get("CLAUDE_IRIS_POLL_WINDOW", "600"))  # 10min


async def _cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SEC)
        except asyncio.CancelledError:
            return
        try:
            _cleanup_uploads(UPLOAD_TTL_DAYS)
            _cleanup_sessions(SESSION_TTL_DAYS)
        except Exception:
            pass


async def _transcript_poller() -> None:
    """Tail Claude Code's transcript directory and backfill on changes.

    Stop hook is the low-latency primary path, but Claude Code only loads
    hook config at session start — sessions started before /iris on (or
    while iris was off) never push, so their replies never reach the
    mirror. Polling closes that gap: scan for transcripts touched in the
    last `POLL_RECENT_WINDOW_SEC`, dedup by (mtime, size), invoke backfill
    on changes. Backfill's own fingerprint dedup prevents double-import
    when both the hook and the poller catch the same turn.

    Set CLAUDE_IRIS_POLL_INTERVAL=0 to disable.
    """
    if POLL_INTERVAL_SEC <= 0:
        return
    seen: dict[str, tuple[float, int]] = {}
    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL_SEC)
        except asyncio.CancelledError:
            return
        try:
            if not CLAUDE_PROJECTS_DIR.exists():
                continue
            cutoff = time.time() - POLL_RECENT_WINDOW_SEC
            for f in CLAUDE_PROJECTS_DIR.glob("*/*.jsonl"):
                try:
                    stat = f.stat()
                except OSError:
                    continue
                if stat.st_mtime < cutoff:
                    continue
                key = (stat.st_mtime, stat.st_size)
                fkey = str(f)
                if seen.get(fkey) == key:
                    continue
                seen[fkey] = key
                session_id = f.stem
                if not all(c.isalnum() or c in "-_" for c in session_id):
                    continue
                try:
                    await backfill_session_from_transcript(session_id)
                except Exception:
                    pass
        except Exception:
            pass


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Background tasks for the server lifetime.

    - cleanup: re-run upload/session TTL every 6h.
    - poller: watch Claude Code transcripts for activity that the Stop
      hook might have missed (e.g. sessions started before hook was
      registered). Both fingerprint-dedupe through backfill.
    """
    cleanup = asyncio.create_task(_cleanup_loop())
    poller = asyncio.create_task(_transcript_poller())
    try:
        yield
    finally:
        cleanup.cancel()
        poller.cancel()


app = FastAPI(title="claude-iris", lifespan=_lifespan)


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
            s = self.clients.get(session_id)
            if s is None:
                return
            s.discard(ws)
            if not s:
                # Drop the empty bucket so long-running servers don't
                # accumulate one entry per session ever connected.
                del self.clients[session_id]

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        async with self.lock:
            targets = list(self.clients.get(session_id, ()))
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
LISTENER_GRACE_SEC = float(os.environ.get("CLAUDE_IRIS_LISTEN_GRACE", "30"))


def _is_wsl() -> bool:
    """True if running inside WSL on Windows.

    WSL exposes a Linux kernel with `microsoft` baked into the version
    string. We use this to fall back to read-only mode: server, Stop
    hook, transcript poller, and broadcast all work, but the listener
    can't reach Windows Terminal (xdotool only injects to X11 apps,
    not native Win32 windows), so browser→terminal pasting is disabled.
    """
    if sys.platform != "linux":
        return False
    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


READ_ONLY = _is_wsl() or os.environ.get("CLAUDE_IRIS_READ_ONLY") == "1"
READ_ONLY_REASON = (
    "Running under WSL — browser-to-terminal paste isn't available because "
    "Windows Terminal isn't reachable from inside the WSL X11 server. "
    "Reply mirroring still works fully."
    if _is_wsl()
    else "Read-only mode forced via CLAUDE_IRIS_READ_ONLY=1."
)


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
    override = os.environ.get("CLAUDE_IRIS_FOCUS")
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
        # Read-only mode (WSL / forced) means we never spawn the keystroke
        # injector. The Stop hook / poller / broadcast paths all still
        # work — the page just shows replies without the input bar wired
        # back to the terminal.
        if READ_ONLY:
            return
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
            env["CLAUDE_IRIS_DATA"] = str(DATA_DIR)
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


def session_tombstone(session_id: str) -> Path:
    """Marker file written by DELETE.

    The poller would otherwise re-import a hard-deleted session within
    seconds (the Claude Code transcript still exists). Tombstone tells
    the poller, list_sessions, and backfill to skip this id. Manual
    restore: delete the .deleted file with `rm`.
    """
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
    return SESSION_DIR / f"{safe}.deleted"


def is_tombstoned(session_id: str) -> bool:
    return session_tombstone(session_id).exists()


# Path where Claude Code stores its own per-session JSONL transcripts. We
# read these (read-only) to recover the user's `/rename` custom title even
# when our own session file has been cleared — so the iris sidebar/title
# always reflects the conversation name without waiting for the next Stop
# hook to push it down.
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def find_claude_transcript(session_id: str) -> Path | None:
    if not session_id or session_id == "default":
        return None
    # Real Claude Code session ids are UUIDs (alnum + hyphen). Anything else
    # could carry glob metacharacters (`*`, `?`, `[`) that would silently
    # match the wrong transcript — e.g. `session_id="*"` would return the
    # most recently modified transcript across the entire projects dir.
    if not all(c.isalnum() or c in "-_" for c in session_id):
        return None
    if not CLAUDE_PROJECTS_DIR.exists():
        return None
    matches = list(CLAUDE_PROJECTS_DIR.glob(f"*/{session_id}.jsonl"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _parse_iso_ts(ts_str: Any) -> float | None:
    if not isinstance(ts_str, str) or not ts_str:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


_NOISE_USER_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "<system-reminder>",
    "[Image #",
)


def _is_noise_user_text(text: str) -> bool:
    """Filter Claude Code's wrapper user records out of the iris feed.

    Slash-command invocations, command stdout caveats, and image-paste shims
    all show up as `user` records but aren't real user dialogue — they'd
    pollute the mirrored conversation. We keep records that contain real
    text alongside a wrapper; only fully-synthetic ones are dropped.
    """
    stripped = text.lstrip()
    if not stripped:
        return True
    return stripped.startswith(_NOISE_USER_PREFIXES)


def _extract_user_text(rec: dict) -> str:
    msg = rec.get("message", rec)
    content = msg.get("content", "")
    if isinstance(content, str):
        text = content.strip()
        return "" if _is_noise_user_text(text) else text
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            chunks.append(block.get("text", ""))
    text = "".join(chunks).strip()
    return "" if _is_noise_user_text(text) else text


def _extract_assistant_text(rec: dict) -> str:
    msg = rec.get("message", rec)
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            chunks.append(block.get("text", ""))
    return "".join(chunks).strip()


# Cached single-pass transcript walk: (mtime, size) → {"title": ..., "turns": [...]}.
# Avoids re-reading the whole jsonl on every GET /session/{id} for sessions
# with hundreds of turns, and replaces the previous pair of separate walks.
# Each entry can be MB-sized for long sessions, so we cap at MAX_CACHE
# entries with a simple LRU eviction (insertion order).
_TRANSCRIPT_CACHE: dict[str, tuple[float, int, dict[str, Any]]] = {}
_TRANSCRIPT_CACHE_MAX = int(os.environ.get("CLAUDE_IRIS_TRANSCRIPT_CACHE_MAX", "32"))


def _read_transcript(transcript: Path) -> dict[str, Any]:
    """Return {"title": str|None, "turns": [...]} from a Claude Code transcript.

    Consecutive assistant records (split by tool_use/tool_result mid-turn) are
    merged into a single assistant turn. Cached so repeated callers (backfill,
    label resolution) don't each re-walk the file.
    """
    empty = {"title": None, "turns": []}
    if not transcript.exists():
        return empty
    try:
        stat = transcript.stat()
    except OSError:
        return empty
    key = str(transcript)
    cached = _TRANSCRIPT_CACHE.get(key)
    if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2]

    title: str | None = None
    turns: list[dict[str, Any]] = []
    asst_chunks: list[str] = []
    asst_ts: float | None = None

    def flush_asst() -> None:
        if asst_chunks:
            turns.append(
                {
                    "role": "assistant",
                    "content": "\n\n".join(asst_chunks).strip(),
                    # ts stays None when source records had no timestamp;
                    # backfill treats that as "older than any clear marker".
                    "ts": asst_ts,
                }
            )

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
                rec_type = rec.get("type")
                if rec_type == "custom-title":
                    t = rec.get("customTitle")
                    if t:
                        title = t
                    continue
                role = rec_type or rec.get("role")
                ts = _parse_iso_ts(rec.get("timestamp"))
                if role == "user":
                    flush_asst()
                    asst_chunks = []
                    asst_ts = None
                    text = _extract_user_text(rec)
                    if text:
                        turns.append({"role": "user", "content": text, "ts": ts})
                elif role == "assistant":
                    text = _extract_assistant_text(rec)
                    if text:
                        asst_chunks.append(text)
                    if ts:
                        asst_ts = ts
        flush_asst()
    except OSError:
        return empty

    result = {"title": title, "turns": turns}
    # Insertion-order LRU: evict the oldest when over cap. dict preserves
    # insertion order in Python 3.7+, so popping the first key gives us
    # the least-recently-inserted entry. Updating an existing entry by
    # `del` then re-`set` would also refresh recency but `_read_transcript`
    # is read-mostly per session, so we don't bother.
    if key in _TRANSCRIPT_CACHE:
        del _TRANSCRIPT_CACHE[key]
    _TRANSCRIPT_CACHE[key] = (stat.st_mtime, stat.st_size, result)
    while len(_TRANSCRIPT_CACHE) > _TRANSCRIPT_CACHE_MAX:
        _TRANSCRIPT_CACHE.pop(next(iter(_TRANSCRIPT_CACHE)))
    return result


async def backfill_session_from_transcript(session_id: str) -> int:
    """Import any turns from the Claude Code transcript that aren't already in
    our iris session file. Useful when /iris open is invoked after the terminal
    has already exchanged messages — without this, the feed appears blank.

    Dedup by (role, first 200 chars of content) so re-runs are idempotent.
    Runs under the per-session write lock so concurrent /push from a Stop
    hook can't interleave bytes inside a backfilled jsonl line. When new
    turns are imported, broadcasts reload + session_touch so any open
    page picks them up immediately. Tombstoned sessions (DELETE'd) skip
    entirely so the poller can't silently revive them.
    """
    if is_tombstoned(session_id):
        return 0
    transcript = find_claude_transcript(session_id)
    if not transcript:
        return 0
    parsed = _read_transcript(transcript)  # cached by (mtime, size)
    turns = parsed["turns"]
    if not turns:
        return 0
    async with _write_lock(session_id):
        existing = load_session(session_id)
        cleared_ts = 0.0
        seen: set[tuple[str, str]] = set()
        for m in existing:
            role = m.get("role")
            if role == "_cleared":
                cleared_ts = max(cleared_ts, float(m.get("ts") or 0))
                continue
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                seen.add((role, content.strip()[:200]))
        label = parsed["title"]
        appended = 0
        for turn in turns:
            # Don't re-import history the user explicitly cleared. Turns whose
            # transcript timestamp predates (or equals) the latest clear marker
            # stay out; only post-clear activity flows in.
            if cleared_ts and float(turn.get("ts") or 0) <= cleared_ts:
                continue
            fp = (turn["role"], turn["content"][:200])
            if fp in seen:
                continue
            seen.add(fp)
            append_session(
                session_id,
                {
                    "session_id": session_id,
                    "session_label": label,
                    "role": turn["role"],
                    "content": turn["content"],
                    "ts": turn["ts"],
                },
            )
            appended += 1
    if appended:
        await hub.broadcast(session_id, {"type": "reload"})
        await hub.broadcast("__index__", {"type": "session_touch", "session": session_id})
    return appended


def custom_title_from_transcript(session_id: str) -> str | None:
    """Latest /rename customTitle from Claude Code's transcript, if any."""
    transcript = find_claude_transcript(session_id)
    if not transcript:
        return None
    return _read_transcript(transcript)["title"]


_session_write_locks: dict[str, asyncio.Lock] = {}


def _write_lock(session_id: str) -> asyncio.Lock:
    """One asyncio.Lock per session_id so concurrent /push and /input
    don't interleave bytes inside a single jsonl line."""
    lock = _session_write_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_write_locks[session_id] = lock
    return lock


def append_session(session_id: str, message: dict[str, Any]) -> None:
    with session_file(session_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")


async def append_session_locked(session_id: str, message: dict[str, Any]) -> None:
    async with _write_lock(session_id):
        append_session(session_id, message)


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
    # Sort by timestamp so backfilled turns interleave correctly with whatever
    # was already in the file (which was just append-order before).
    out.sort(key=lambda m: m.get("ts") or 0)
    return out


def list_sessions() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in sorted(SESSION_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        # Skip the synthetic "default" bucket: it's only created when someone
        # types in iris's input box before any real Claude session has pushed,
        # and shows up in the sidebar as confusing duplicate-with-no-replies.
        if f.stem == "default":
            continue
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
        label = custom_title_from_transcript(f.stem) or last_label or f.stem
        out.append(
            {
                "id": f.stem,
                "label": label,
                "mtime": f.stat().st_mtime,
            }
        )
    return out


def _latest_iris_label(session_id: str) -> str | None:
    """Most recent non-null session_label persisted to the iris jsonl.

    Captures both the iris-side `/session/{id}/label` rename and any prior
    /push that already had a label. Used to keep an iris rename from being
    silently clobbered by the next Stop-hook push (whose fallback is the
    cwd basename, not the user's chosen name).
    """
    p = session_file(session_id)
    if not p.exists():
        return None
    last: str | None = None
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lbl = rec.get("session_label")
                if lbl:
                    last = lbl
    except OSError:
        return None
    return last


def _resolve_label(session_id: str, fallback: str | None) -> str | None:
    """Resolve the label for a /push or /input record.

    Priority:
      1. Claude Code `/rename` (authoritative — explicit user action in CC).
      2. iris-side stored label (preserves iris's own rename and prior labels).
      3. Caller's fallback (Stop hook derives this from cwd basename).
    """
    title = custom_title_from_transcript(session_id)
    if title:
        return title
    iris = _latest_iris_label(session_id)
    if iris:
        return iris
    return fallback


@app.post("/push")
async def push(payload: PushPayload) -> dict[str, Any]:
    # Stop hook fired for a session the user explicitly deleted — respect
    # the deletion, don't silently revive. /input would lift the tombstone
    # since that's an explicit user action.
    if is_tombstoned(payload.session_id):
        return {"ok": True, "ignored": "tombstoned"}
    msg = {
        "session_id": payload.session_id,
        "session_label": _resolve_label(payload.session_id, payload.session_label),
        "role": payload.role,
        "content": payload.content,
        "ts": payload.ts or time.time(),
    }
    await append_session_locked(payload.session_id, msg)
    await hub.broadcast(payload.session_id, {"type": "message", "message": msg})
    await hub.broadcast("__index__", {"type": "session_touch", "session": payload.session_id})
    return {"ok": True}


@app.post("/input")
async def push_input(payload: InputPayload) -> dict[str, Any]:
    if READ_ONLY:
        # No listener spawned — the message would be appended to the
        # session jsonl but never typed into a terminal, which is a
        # silent UX failure. Tell the frontend so it can disable the box.
        return JSONResponse(
            {"ok": False, "error": "read-only", "reason": READ_ONLY_REASON},
            status_code=409,
        )
    # /input is an explicit user action — typing here means "I want this
    # session active again." Lift any tombstone so future /push and the
    # poller stop ignoring this id.
    tomb = session_tombstone(payload.session_id)
    if tomb.exists():
        try:
            tomb.unlink()
        except OSError:
            pass
    msg = {
        "session_id": payload.session_id,
        "session_label": _resolve_label(payload.session_id, payload.session_label),
        "role": "user",
        "content": payload.text,
        "ts": time.time(),
    }
    await append_session_locked(payload.session_id, msg)
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
        # JSON-per-line so the listener can log the originating session
        # alongside the text. Newlines inside `text` become \n inside the
        # JSON string, so the framing stays intact.
        line = json.dumps(
            {"session": payload.session_id, "text": payload.text},
            ensure_ascii=False,
        ) + "\n"
        os.write(fd, line.encode("utf-8"))
        os.close(fd)
        return {"ok": True, "pipe": "delivered"}
    except OSError:
        return {"ok": True, "pipe": "no consumer"}


MAX_LABEL_LEN = 200


@app.post("/session/{session_id}/label")
async def rename_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    label = str(payload.get("label", "")).strip()
    if not label:
        return JSONResponse({"ok": False, "error": "label required"}, status_code=400)
    if len(label) > MAX_LABEL_LEN:
        return JSONResponse(
            {"ok": False, "error": f"label too long (max {MAX_LABEL_LEN})"},
            status_code=400,
        )
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
    await append_session_locked(safe, meta)
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
    # backfill broadcasts reload + session_touch internally when it imports.
    backfilled = await backfill_session_from_transcript(session_id)
    messages = load_session(session_id)
    return {"session_id": session_id, "messages": messages, "backfilled": backfilled}


@app.post("/session/{session_id}/clear")
async def clear_session(session_id: str) -> dict[str, Any]:
    """Empty the feed but keep the session in the sidebar.

    Writes a `_cleared` marker so backfill from Claude Code's transcript
    won't immediately re-import the history we just hid. Stop-hook pushes
    for new assistant turns still flow in normally.
    """
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
    p = session_file(safe)
    marker = {
        "session_id": safe,
        "role": "_cleared",
        "ts": time.time(),
    }
    async with _write_lock(safe):
        if p.exists():
            p.unlink()
        with p.open("w", encoding="utf-8") as f:
            f.write(json.dumps(marker, ensure_ascii=False) + "\n")
    await hub.broadcast(safe, {"type": "reload"})
    await hub.broadcast("__index__", {"type": "session_touch", "session": safe})
    return {"ok": True}


@app.delete("/session/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    """Permanently remove the session file and prevent re-import.

    Writes a tombstone (`.deleted`) so the transcript poller doesn't
    silently revive the session within seconds — Claude Code's transcript
    still exists, the poller would otherwise re-walk it and re-create the
    iris jsonl. To bring a deleted session back manually:
        rm ~/.claude-iris/sessions/<session-id>.deleted

    Use POST /session/{id}/clear instead if you want to keep the bucket
    but empty its feed.
    """
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
    p = session_file(safe)
    async with _write_lock(safe):
        if p.exists():
            p.unlink()
        session_tombstone(safe).touch()
    await hub.broadcast("__index__", {"type": "session_removed", "session": safe})
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
    return {
        "ok": True,
        "data_dir": str(DATA_DIR),
        "read_only": READ_ONLY,
        "read_only_reason": READ_ONLY_REASON if READ_ONLY else None,
    }


def main() -> None:
    import uvicorn

    host = os.environ.get("CLAUDE_IRIS_HOST", "127.0.0.1")
    port = int(os.environ.get("CLAUDE_IRIS_PORT", "7456"))
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
