#!/usr/bin/env bash
# Install claude-lens: venv + symlinks + slash commands + notebooklm doctor.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
HOME_CLAUDE="${HOME}/.claude"
VENV_DIR="${REPO}/server/.venv"
COMMANDS_DIR="${HOME_CLAUDE}/commands"
PLUGINS_DIR="${HOME_CLAUDE}/plugins"

echo ">>> claude-lens installer"
echo "    repo: ${REPO}"

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
PLUGIN_LINK="${PLUGINS_DIR}/claude-lens"
if [ -L "${PLUGIN_LINK}" ] || [ -e "${PLUGIN_LINK}" ]; then
  rm -rf "${PLUGIN_LINK}"
fi
ln -s "${REPO}" "${PLUGIN_LINK}"
echo ">>> plugin symlinked: ${PLUGIN_LINK}"

# 4. install slash commands
cp "${REPO}/commands/lens.md" "${COMMANDS_DIR}/lens.md"
cp "${REPO}/commands/tutor.md" "${COMMANDS_DIR}/tutor.md"
echo ">>> /lens and /tutor commands installed at ${COMMANDS_DIR}/"

# 5. make scripts executable
chmod +x "${REPO}/hooks/stop_lens.py"
chmod +x "${REPO}/bin/claude-lens" 2>/dev/null || true

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
echo "  /lens on            # start mirror server + Stop hook + Chrome tab"
echo "  /tutor init         # walk through NotebookLM setup + pick a role"
echo "  /lens off           # tear down"
echo ""
