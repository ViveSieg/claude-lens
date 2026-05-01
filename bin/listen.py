#!/usr/bin/env python3
"""claude-lens listen — type browser input into the front terminal.

Reads lines from ~/.claude-lens/input.pipe and sends keystrokes + Return
to the OS-frontmost window via osascript (macOS) or xdotool (Linux).
The mirror server spawns this on first WebSocket connect and tears it
down after grace when the last browser tab closes.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("CLAUDE_LENS_DATA", Path.home() / ".claude-lens"))
PIPE = DATA_DIR / "input.pipe"
SYSTEM = platform.system()


def ensure_pipe() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PIPE.exists():
        os.mkfifo(PIPE)


def _osascript_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _quartz_paste_to_pid(pid: int) -> bool:
    """Post Cmd+V + Return to a specific pid without activating its app.

    Returns True on success. Quartz CGEventPostToPid lets us deliver key
    events to a target process even when it isn't the frontmost — so the
    terminal pastes the clipboard in the background and the lens browser
    keeps focus (no flash, no jump).
    """
    try:
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventPostToPid,
            CGEventSetFlags,
            kCGEventFlagMaskCommand,
        )
    except ImportError:
        return False
    # macOS virtual keycodes: V=9, Return=36
    for is_down in (True, False):
        ev = CGEventCreateKeyboardEvent(None, 9, is_down)
        CGEventSetFlags(ev, kCGEventFlagMaskCommand)
        CGEventPostToPid(pid, ev)
    for is_down in (True, False):
        ev = CGEventCreateKeyboardEvent(None, 36, is_down)
        CGEventPostToPid(pid, ev)
    return True


def _find_app_pid(name: str) -> int | None:
    """Return the pid of a running app whose localized name matches `name`."""
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return None
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        try:
            if app.localizedName() == name:
                return int(app.processIdentifier())
        except Exception:
            continue
    return None


def inject_macos(text: str, *, focus_app: str | None) -> None:
    """Inject text into focus_app (or current frontmost) via clipboard.

    Strategy:
    1. pbcopy the text (handles all Unicode incl. CJK; `keystroke` can't).
    2. If focus_app is set and Quartz is available → CGEventPostToPid,
       which delivers Cmd+V + Return to that pid in the background. No
       app activation, no focus flash.
    3. Fall back to osascript activate-paste-restore-prevApp if Quartz
       isn't available (e.g. PyObjC missing) or the pid lookup fails.

    Clipboard caveat: this clobbers the user's clipboard. We don't restore
    it because macOS only round-trips text reliably — images/files through
    AppleScript is lossy.
    """
    try:
        subprocess.run(
            ["pbcopy"], input=text.encode("utf-8"), check=True, timeout=2
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        print(f"[listen] pbcopy failed: {e}", file=sys.stderr)
        return

    if focus_app:
        pid = _find_app_pid(focus_app)
        if pid and _quartz_paste_to_pid(pid):
            return
        # Fallback: activate, paste, restore. Visible flash but works.
        script = (
            'tell application "System Events"\n'
            '    set prevApp to name of first application process whose frontmost is true\n'
            'end tell\n'
            f'tell application "{focus_app}" to activate\n'
            'tell application "System Events"\n'
            '    delay 0.08\n'
            '    keystroke "v" using {command down}\n'
            '    delay 0.05\n'
            '    key code 36\n'
            '    delay 0.05\n'
            'end tell\n'
            'try\n'
            '    if prevApp is not "' + focus_app + '" then\n'
            '        tell application prevApp to activate\n'
            '    end if\n'
            'end try\n'
        )
    else:
        script = (
            'tell application "System Events"\n'
            '    delay 0.05\n'
            '    keystroke "v" using {command down}\n'
            '    delay 0.05\n'
            '    key code 36\n'
            'end tell\n'
        )
    subprocess.run(["osascript", "-e", script], check=False)


def inject_linux(text: str) -> None:
    if not shutil.which("xdotool"):
        print(
            "[listen] xdotool not found — install via apt/yum/pacman.",
            file=sys.stderr,
        )
        return
    subprocess.run(["xdotool", "type", "--delay", "20", text], check=False)
    subprocess.run(["xdotool", "key", "Return"], check=False)


def inject(text: str, *, focus_app: str | None) -> None:
    if SYSTEM == "Darwin":
        inject_macos(text, focus_app=focus_app)
    elif SYSTEM == "Linux":
        inject_linux(text)
    else:
        print(f"[listen] platform {SYSTEM} not supported", file=sys.stderr)


def banner(args: argparse.Namespace) -> None:
    print()
    print("claude-lens listen")
    print(f"  pipe:        {PIPE}")
    print(f"  platform:    {SYSTEM}")
    print(f"  inject:      {'on' if args.inject else 'off (dry-run, log only)'}")
    if args.inject and args.focus:
        print(f"  focus app:   {args.focus}")
    if SYSTEM == "Darwin" and args.inject:
        print()
        print("  macOS Accessibility permission required for keystroke injection.")
        print("  System Settings → Privacy & Security → Accessibility → enable")
        print("  your terminal (Terminal.app or iTerm.app). First run usually")
        print("  fails silently until permission is granted.")
    print()
    if args.inject:
        print("  Focus your Claude Code terminal window. Browser messages will")
        print("  be typed into it automatically.")
    else:
        print("  Dry run — every line received from the browser is printed below")
        print("  but NOT injected. Add --inject to enable typing.")
    print("  Ctrl-C to stop.")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claude-lens listen")
    parser.add_argument(
        "--dry-run",
        dest="inject",
        action="store_false",
        help="log lines but do NOT inject keystrokes (default is to inject)",
    )
    parser.add_argument(
        "--focus",
        default=None,
        help="macOS only: name of the app to activate before each keystroke "
        "(e.g. 'Terminal', 'iTerm2'). Default: don't activate, type into current focus.",
    )
    parser.set_defaults(inject=True)
    args = parser.parse_args(argv)

    ensure_pipe()
    banner(args)

    while True:
        try:
            # Re-open per-line: a write closes the pipe; we re-open to wait for next.
            with open(PIPE, "r") as f:
                for raw in f:
                    line = raw.rstrip("\n")
                    if not line:
                        continue
                    print(f"  ▸ {line}")
                    if args.inject:
                        inject(line, focus_app=args.focus)
        except KeyboardInterrupt:
            print("\n[listen] stopped.")
            return 0
        except OSError as e:
            print(f"[listen] pipe error: {e}", file=sys.stderr)
            time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
