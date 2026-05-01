#!/usr/bin/env python3
"""Claude Code Stop hook — push the last assistant turn to claude-lens.

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

ENDPOINT = os.environ.get("CLAUDE_LENS_ENDPOINT", "http://127.0.0.1:7456/push")
TIMEOUT = float(os.environ.get("CLAUDE_LENS_TIMEOUT", "1.5"))


def read_event() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def last_assistant_text(transcript: Path) -> str | None:
    if not transcript.exists():
        return None
    last_text: str | None = None
    with transcript.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Records vary: {"type":"assistant","message":{"content":[...]}} or
            # {"role":"assistant","content":[...]}
            role = rec.get("type") or rec.get("role")
            if role != "assistant":
                continue
            msg = rec.get("message", rec)
            content = msg.get("content")
            if isinstance(content, str):
                last_text = content
                continue
            if not isinstance(content, list):
                continue
            chunks: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    chunks.append(block.get("text", ""))
            if chunks:
                last_text = "".join(chunks).strip()
    return last_text


def last_custom_title(transcript: Path) -> str | None:
    """Return the most recent /rename title for this session, if any.

    Claude Code writes one record per /rename:
        {"type": "custom-title", "customTitle": "<name>", "sessionId": "..."}
    """
    if not transcript.exists():
        return None
    last_title: str | None = None
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
    return last_title


def derive_session_label(transcript: Path | None, cwd: str | None) -> str | None:
    if transcript is not None:
        title = last_custom_title(transcript)
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
    text = last_assistant_text(transcript)
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
