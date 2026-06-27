#!/usr/bin/env python3
"""Claude Code Stop hook — push the last assistant turn to claude-iris.

Reads the hook-event JSON from stdin, locates the transcript file, extracts
the most recent assistant message's text content, and POSTs it to the
local mirror server. Silent on failure so it never blocks the shell.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = os.environ.get("CLAUDE_IRIS_ENDPOINT", "http://127.0.0.1:7456/push")
# Claude Code blocks the prompt return until Stop hooks finish. Keep this
# tight so a slow / dead iris server can't add noticeable latency between
# turns — 0.8s is plenty for a healthy localhost POST.
TIMEOUT = float(os.environ.get("CLAUDE_IRIS_TIMEOUT", "0.8"))


def read_event() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _extract_text_blocks(rec: dict) -> str:
    """Pull all `type: text` blocks out of an assistant record, joined."""
    msg = rec.get("message", rec)
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            chunks.append(block.get("text", ""))
    return "".join(chunks).strip()


def latest_turn_assistant_text(transcript: Path) -> str | None:
    """Concatenate every assistant text block from the most recent turn.

    A "turn" = everything since the last user message. When Claude calls
    tools mid-reply (e.g. `/notecraft chat`), Claude Code splits the
    assistant output into multiple records separated by tool_use /
    tool_result entries. Taking only the final record drops the opening
    explanation, the tool results, and the analysis — the user sees a
    suspiciously short last paragraph. We keep them all and join with
    blank-line separators.
    """
    if not transcript.exists():
        return None
    current_turn: list[str] = []
    with transcript.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = rec.get("type") or rec.get("role")
            if role == "user":
                # New user turn → drop everything we'd buffered for the prior turn.
                current_turn = []
            elif role == "assistant":
                text = _extract_text_blocks(rec)
                if text:
                    current_turn.append(text)
    if not current_turn:
        return None
    return "\n\n".join(current_turn).strip() or None


def last_title_from_transcript(transcript: Path) -> str | None:
    """Return the most recent conversation title from the transcript.

    Priority: /rename > ai-title.
    Claude Code writes:
      - /rename: {"type": "custom-title", "customTitle": "<name>", "sessionId": "..."}
      - auto:    {"type": "ai-title", "aiTitle": "<name>", "sessionId": "..."}
    """
    if not transcript.exists():
        return None
    rename: str | None = None
    ai_title: str | None = None
    with transcript.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("type")
            if t == "custom-title":
                v = rec.get("customTitle")
                if v:
                    rename = v
            elif t == "ai-title":
                v = rec.get("aiTitle")
                if v:
                    ai_title = v
    return rename or ai_title


def derive_session_label(transcript: Path | None, cwd: str | None) -> str | None:
    if transcript is not None:
        title = last_title_from_transcript(transcript)
        if title:
            return title
    if not cwd:
        return None
    return Path(cwd).name or None


def main() -> int:
    event = read_event()
    transcript_path = event.get("transcript_path")
    session_id = event.get("session_id") or event.get("session", "default")
    cwd = event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR")

    if not transcript_path:
        return 0

    transcript = Path(transcript_path)
    text = latest_turn_assistant_text(transcript)
    if not text:
        return 0

    payload = {
        "session_id": str(session_id),
        "session_label": derive_session_label(transcript, cwd),
        "role": "assistant",
        "content": text,
    }
    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT)
    except (urllib.error.URLError, TimeoutError, OSError):
        # mirror server not running — silently no-op
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
