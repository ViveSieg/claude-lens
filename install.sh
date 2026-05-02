#!/usr/bin/env bash
# Install claude-iris: venv + symlinks + slash commands + notebooklm doctor.
set -euo pipefail

# Native Windows (Git Bash / MSYS / Cygwin) isn't supported — bin/listen.py
# requires PyObjC (macOS) or xdotool (Linux), neither reaches Windows
# Terminal. Tell the user to use WSL2 instead, where iris runs as a
# Linux app in read-only mirror mode.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    cat >&2 <<'EOF'
✗ claude-iris doesn't run natively on Windows.

Use WSL2 instead — Microsoft's recommended path for Claude Code on Windows:

  1. Install WSL2 with an Ubuntu image (one-time, in PowerShell as admin):
       wsl --install -d Ubuntu

  2. Open the Ubuntu shell, then install Node 18+ and Python 3.10+:
       sudo apt update && sudo apt install -y nodejs npm python3-venv

  3. Install claude-iris inside Ubuntu (NOT in PowerShell):
       npm i -g claude-iris
       claude-iris setup

Inside WSL the mirror runs in read-only mode: assistant replies still
stream to the browser, but typing back into the terminal from the page
is disabled (Windows Terminal is a native Win32 window, unreachable
from WSL's keystroke injection). Type prompts in the terminal as usual.

EOF
    exit 1
    ;;
esac

REPO="$(cd "$(dirname "$0")" && pwd)"
HOME_CLAUDE="${HOME}/.claude"
VENV_DIR="${REPO}/server/.venv"
COMMANDS_DIR="${HOME_CLAUDE}/commands"
PLUGINS_DIR="${HOME_CLAUDE}/plugins"

# Detect WSL so we can flag read-only mode in the install summary.
IS_WSL=0
if [[ -f /proc/version ]] && grep -qi microsoft /proc/version; then
  IS_WSL=1
fi

echo ">>> claude-iris installer"
echo "    repo: ${REPO}"
if [[ "${IS_WSL}" -eq 1 ]]; then
  echo "    note: running under WSL → mirror will run in READ-ONLY mode"
  echo "          (browser shows replies; typing back into the terminal"
  echo "          from the page is disabled)"
fi

# ── pre-flight: hard dependencies ───────────────────────────────────────
# Catch missing tools BEFORE we start a venv / pip install whose error
# messages are far less actionable than "you need apt install python3-venv".
MISSING=()

if ! command -v python3 >/dev/null 2>&1; then
  MISSING+=("python3")
else
  PY_VER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
  PY_MAJOR=${PY_VER%.*}
  PY_MINOR=${PY_VER#*.}
  if [ "${PY_MAJOR:-0}" -lt 3 ] || { [ "${PY_MAJOR:-0}" -eq 3 ] && [ "${PY_MINOR:-0}" -lt 10 ]; }; then
    MISSING+=("python>=3.10 (have ${PY_VER})")
  fi
  # Debian / Ubuntu / WSL ship python3 without the `venv` module — split
  # into the `python3-venv` apt package. `python3 -m venv` will then fail
  # with a cryptic "ensurepip is not available" error. Catch it here.
  if ! python3 -c "import venv, ensurepip" >/dev/null 2>&1; then
    MISSING+=("python3-venv (the standard library venv module)")
  fi
fi

if ! command -v node >/dev/null 2>&1; then
  MISSING+=("nodejs (>=18)")
else
  NODE_MAJOR=$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || echo 0)
  if [ "${NODE_MAJOR}" -lt 18 ]; then
    MISSING+=("node>=18 (have v${NODE_MAJOR})")
  fi
fi

if ! command -v npm >/dev/null 2>&1; then
  MISSING+=("npm")
fi

if [ "${#MISSING[@]}" -gt 0 ]; then
  echo ""
  echo "✗ missing prerequisites:" >&2
  for m in "${MISSING[@]}"; do
    echo "  - ${m}" >&2
  done
  echo "" >&2
  case "$(uname -s)" in
    Linux)
      if command -v apt-get >/dev/null 2>&1; then
        echo "  Install on Ubuntu / Debian / WSL Ubuntu:" >&2
        echo "    sudo apt update" >&2
        echo "    sudo apt install -y nodejs npm python3 python3-venv python3-pip" >&2
      elif command -v dnf >/dev/null 2>&1; then
        echo "  Install on Fedora / RHEL:" >&2
        echo "    sudo dnf install -y nodejs npm python3 python3-virtualenv" >&2
      elif command -v pacman >/dev/null 2>&1; then
        echo "  Install on Arch:" >&2
        echo "    sudo pacman -S nodejs npm python python-virtualenv" >&2
      fi
      ;;
    Darwin)
      echo "  Install on macOS (Homebrew):" >&2
      echo "    brew install python@3.12 node" >&2
      ;;
  esac
  echo "" >&2
  exit 1
fi
echo "    deps: python ${PY_VER}, node v${NODE_MAJOR}, npm $(npm -v)"

# 1. python venv + deps
if [ ! -d "${VENV_DIR}" ]; then
  echo ">>> creating venv at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null
"${VENV_DIR}/bin/pip" install -r "${REPO}/server/requirements.txt" >/dev/null
echo ">>> python deps installed"

# 1a. macOS only: verify Quartz/Cocoa are importable so the background-paste
# path (Cmd+V via CGEventPostToPid, no focus steal) actually works at run
# time. If this fails the listener still works, just visibly flashes the
# terminal forward and back.
if [[ "$(uname -s)" == "Darwin" ]]; then
  if "${VENV_DIR}/bin/python" -c "import Quartz, AppKit" >/dev/null 2>&1; then
    echo ">>> macOS background-paste ready (PyObjC Quartz + AppKit)"
  else
    echo "    ! PyObjC import failed — listener will fall back to AppleScript"
    echo "      (terminal will flash forward and back on each Send)."
    echo "      Retry: ${VENV_DIR}/bin/pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa"
  fi
fi

# 2. directories
mkdir -p "${COMMANDS_DIR}" "${PLUGINS_DIR}"

# 3. symlink plugin dir for discovery
PLUGIN_LINK="${PLUGINS_DIR}/claude-iris"
if [ -L "${PLUGIN_LINK}" ] || [ -e "${PLUGIN_LINK}" ]; then
  rm -rf "${PLUGIN_LINK}"
fi
ln -s "${REPO}" "${PLUGIN_LINK}"
echo ">>> plugin symlinked: ${PLUGIN_LINK}"

# 4. install slash commands
# Symlink (not cp) so a future package upgrade auto-publishes any spec
# changes to the live slash commands. Any leftover plain file from older
# installers gets replaced. The -n on ln prevents creating links inside
# an existing target if the path resolves to a directory mid-race.
for cmd in iris tutor; do
  rm -f "${COMMANDS_DIR}/${cmd}.md"
  ln -snf "${REPO}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done
echo ">>> /iris and /tutor commands linked to ${COMMANDS_DIR}/"

# 5. make scripts executable
chmod +x "${REPO}/hooks/stop_iris.py"
chmod +x "${REPO}/bin/claude-iris" 2>/dev/null || true

# 6. NotebookLM doctor (optional — skip if --no-notebook)
if [[ "${1:-}" != "--no-notebook" ]]; then
  echo ""
  echo ">>> NotebookLM toolchain check (pass --no-notebook to skip)"
  if ! command -v node >/dev/null 2>&1; then
    echo "    ! node missing — install Node.js >=18 manually (https://nodejs.org)"
  else
    echo "    node: $(node --version)"
  fi
  if ! command -v npm >/dev/null 2>&1; then
    echo "    ! npm missing — comes with Node"
  else
    if npm ls -g notebooklm-client --depth=0 >/dev/null 2>&1; then
      echo "    notebooklm-client: already installed globally"
    else
      echo "    installing notebooklm-client globally ..."
      if npm i -g notebooklm-client >/dev/null 2>&1; then
        echo "    notebooklm-client: installed"
      else
        echo "    ! npm i -g notebooklm-client failed (try: sudo npm i -g notebooklm-client)"
      fi
    fi
  fi
  if [ -f "${HOME}/.notebooklm/session.json" ]; then
    echo "    NotebookLM session: present (~/.notebooklm/session.json)"
  else
    echo "    NotebookLM session: MISSING — run later: npx notebooklm export-session"
  fi
fi

echo ""
echo ">>> done."
echo ""
echo "Next steps in any Claude Code session:"
echo "  /iris on            # start mirror server + Stop hook + Chrome tab"
echo "  /tutor init         # walk through NotebookLM setup + pick a role"
echo "  /iris off           # tear down"
echo ""
