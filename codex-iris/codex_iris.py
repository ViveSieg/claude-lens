from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
SESSIONS_ROOT = CODEX_HOME / "sessions"
MAX_TOOL_CHARS = int(os.environ.get("CODEX_IRIS_MAX_TOOL_CHARS", "40000"))


SKIP_PREFIXES = (
    "<environment_context>",
    "<permissions instructions>",
    "<app-context>",
    "<collaboration_mode>",
    "<skills_instructions>",
    "<plugins_instructions>",
)


def iso_to_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clip_text(value: Any, limit: int = MAX_TOOL_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n\n[truncated {omitted} characters]"


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype in {"input_text", "output_text", "text"}:
            parts.append(str(block.get("text", "")))
        elif btype in {"image_url", "input_image"}:
            parts.append("[image]")
        elif btype == "local_image":
            parts.append(f"[local image: {block.get('path', '')}]")
    return "\n".join(p for p in parts if p).strip()


def should_skip_dialogue(role: str, text: str) -> bool:
    if role not in {"user", "assistant"}:
        return True
    stripped = text.lstrip()
    if not stripped:
        return True
    return stripped.startswith(SKIP_PREFIXES)


def session_key(path: Path) -> str:
    return path.resolve().relative_to(SESSIONS_ROOT.resolve()).as_posix()


def resolve_session_key(key: str) -> Path | None:
    normalized = unquote(key).strip().replace("\\", "/")
    if not normalized:
        return None
    candidate = (SESSIONS_ROOT / Path(*normalized.split("/"))).resolve()
    root = SESSIONS_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.is_file() and candidate.suffix == ".jsonl":
        return candidate
    return None


def session_files() -> list[Path]:
    if not SESSIONS_ROOT.exists():
        return []
    files = [p for p in SESSIONS_ROOT.rglob("*.jsonl") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def read_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    bad = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if isinstance(rec, dict):
                    records.append(rec)
    except OSError:
        bad += 1
    return records, bad


def make_message(
    idx: int,
    timestamp: str | None,
    role: str,
    content: str,
    *,
    kind: str = "message",
    source: str = "",
    phase: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "idx": idx,
        "timestamp": timestamp,
        "ts": iso_to_epoch(timestamp),
        "role": role,
        "kind": kind,
        "phase": phase,
        "source": source,
        "content": content,
        "meta": meta or {},
    }


def format_function_call(payload: dict[str, Any]) -> str:
    name = payload.get("name") or payload.get("tool") or "tool"
    args = payload.get("arguments", "")
    if isinstance(args, str):
        try:
            args_text = json.dumps(json.loads(args), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            args_text = args
    else:
        args_text = json.dumps(args, ensure_ascii=False, indent=2)
    return f"{name}\n{args_text}".strip()


def parse_session(path: Path) -> dict[str, Any]:
    records, bad = read_records(path)
    meta: dict[str, Any] = {}
    messages: list[dict[str, Any]] = []
    event_dialogue_exists = any(
        r.get("type") == "event_msg"
        and r.get("payload", {}).get("type") in {"user_message", "agent_message"}
        for r in records
    )

    for idx, rec in enumerate(records):
        timestamp = rec.get("timestamp")
        rec_type = rec.get("type")
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}

        if rec_type == "session_meta":
            meta.update(payload)
            continue

        if rec_type == "event_msg":
            ptype = payload.get("type")
            if ptype == "user_message":
                text = str(payload.get("message") or "").strip()
                if text:
                    messages.append(
                        make_message(idx, timestamp, "user", text, source="event_msg")
                    )
            elif ptype == "agent_message":
                text = str(payload.get("message") or "").strip()
                if text:
                    messages.append(
                        make_message(
                            idx,
                            timestamp,
                            "assistant",
                            text,
                            source="event_msg",
                            phase=payload.get("phase"),
                        )
                    )
            elif ptype == "token_count":
                info = payload.get("info", {})
                total = info.get("total_token_usage") if isinstance(info, dict) else None
                if total:
                    messages.append(
                        make_message(
                            idx,
                            timestamp,
                            "stats",
                            json.dumps(total, ensure_ascii=False, indent=2),
                            kind="tokens",
                            source="event_msg",
                        )
                    )
            continue

        if rec_type != "response_item":
            continue

        ptype = payload.get("type")
        if ptype == "function_call":
            messages.append(
                make_message(
                    idx,
                    timestamp,
                    "tool",
                    clip_text(format_function_call(payload)),
                    kind="call",
                    source="response_item",
                    meta={"call_id": payload.get("call_id"), "name": payload.get("name")},
                )
            )
        elif ptype == "function_call_output":
            messages.append(
                make_message(
                    idx,
                    timestamp,
                    "tool",
                    clip_text(payload.get("output", "")),
                    kind="output",
                    source="response_item",
                    meta={"call_id": payload.get("call_id")},
                )
            )
        elif ptype in {"web_search_call", "tool_call"}:
            messages.append(
                make_message(
                    idx,
                    timestamp,
                    "tool",
                    clip_text(payload),
                    kind=ptype,
                    source="response_item",
                )
            )
        elif ptype == "message" and not event_dialogue_exists:
            role = str(payload.get("role") or "")
            text = content_text(payload.get("content"))
            if not should_skip_dialogue(role, text):
                messages.append(
                    make_message(
                        idx,
                        timestamp,
                        role,
                        text,
                        source="response_item",
                        phase=payload.get("phase"),
                    )
                )

    stat = path.stat()
    first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
    last_visible = next((m for m in reversed(messages) if m["role"] in {"user", "assistant"}), None)
    label = first_user.replace("\n", " ").strip()[:80]
    if not label:
        label = meta.get("cwd") or path.stem
    return {
        "key": session_key(path),
        "file": str(path),
        "meta": meta,
        "label": label,
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "bad_lines": bad,
        "message_count": len(messages),
        "last": last_visible,
        "messages": messages,
    }


def list_sessions() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in session_files():
        parsed = parse_session(path)
        parsed.pop("messages", None)
        out.append(parsed)
    return out


class CodexIrisHandler(BaseHTTPRequestHandler):
    server_version = "codex-iris/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        stream = getattr(sys, "stderr", None)
        if stream is not None:
            stream.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_bytes(body, "application/json; charset=utf-8", status)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"ok": False, "error": message}, status.value)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "time": now_iso(),
                    "codex_home": str(CODEX_HOME),
                    "sessions_root": str(SESSIONS_ROOT),
                    "sessions_root_exists": SESSIONS_ROOT.exists(),
                }
            )
            return

        if path == "/api/sessions":
            self.send_json({"ok": True, "sessions": list_sessions()})
            return

        if path == "/api/session":
            key = qs.get("key", [""])[0]
            target = resolve_session_key(key)
            if target is None:
                self.send_error_json(HTTPStatus.NOT_FOUND, "session not found")
                return
            self.send_json({"ok": True, "session": parse_session(target)})
            return

        if path == "/api/latest":
            files = session_files()
            if not files:
                self.send_error_json(HTTPStatus.NOT_FOUND, "no sessions found")
                return
            self.send_json({"ok": True, "session": parse_session(files[0])})
            return

        self.serve_static(path)

    def serve_static(self, request_path: str) -> None:
        if request_path in {"", "/"}:
            target = STATIC_ROOT / "index.html"
        else:
            relative = unquote(request_path.lstrip("/"))
            target = (STATIC_ROOT / relative).resolve()
            try:
                target.relative_to(STATIC_ROOT.resolve())
            except ValueError:
                self.send_error_json(HTTPStatus.FORBIDDEN, "forbidden")
                return
        if not target.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "not found")
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        self.send_bytes(target.read_bytes(), content_type)


def run(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), CodexIrisHandler)
    print(f"codex-iris listening on http://{host}:{port}", flush=True)
    print(f"reading sessions from {SESSIONS_ROOT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex session mirror inspired by claude-iris.")
    parser.add_argument("--host", default=os.environ.get("CODEX_IRIS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODEX_IRIS_PORT", "7456")))
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
