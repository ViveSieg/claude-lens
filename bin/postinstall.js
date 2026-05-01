#!/usr/bin/env node
/* claude-lens npm postinstall — runs install.sh quietly so the slash
   commands work right after `npm i -g claude-lens`. Failure here MUST
   never break the install — we just print a friendly hint.
*/

"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

if (process.env.CLAUDE_LENS_SKIP_POSTINSTALL === "1") {
  process.exit(0);
}

if (process.platform === "win32") {
  console.log(
    "[claude-lens] Windows is not directly supported — use WSL and run\n" +
      "             `claude-lens setup` from inside the WSL shell."
  );
  process.exit(0);
}

const PKG_ROOT = path.resolve(__dirname, "..");
const INSTALL_SH = path.join(PKG_ROOT, "install.sh");

if (!fs.existsSync(INSTALL_SH)) {
  console.log(
    "[claude-lens] install.sh missing — skipping post-install setup.\n" +
      "             Run `claude-lens setup` manually if needed."
  );
  process.exit(0);
}

const RESET = "\x1b[0m";
const CORAL = "\x1b[38;2;204;120;92m";
const TEAL = "\x1b[38;2;93;184;166m";
const DIM = "\x1b[2m";
const tty = process.stdout.isTTY;
const c = (col, s) => (tty ? col + s + RESET : s);

console.log("");
console.log(c(CORAL, "  claude-lens · post-install"));
console.log(c(DIM, "  Setting up venv + plugin symlink + slash commands..."));
console.log("");

// `--no-notebook` skips the interactive NotebookLM toolchain check so we
// never block the install. Users who want the notebook layer run
// `claude-lens setup` later or invoke `/tutor init` from Claude Code.
const r = spawnSync("bash", [INSTALL_SH, "--no-notebook"], {
  cwd: PKG_ROOT,
  stdio: tty ? "inherit" : "pipe",
});

if (r.status === 0) {
  console.log("");
  console.log(c(TEAL, "  ✓ ready"));
  console.log("");
  console.log(c(DIM, "  next:"));
  console.log("    " + c(CORAL, "claude-lens open") + "    " + c(DIM, "# start mirror + open Chrome + spawn listener"));
  console.log("    " + c(CORAL, "/lens on") + "          " + c(DIM, "# (in any Claude Code session) same thing"));
  console.log("    " + c(CORAL, "/tutor init") + "       " + c(DIM, "# (optional) wire a NotebookLM notebook in"));
  console.log("");
} else {
  console.log("");
  console.log(
    c(CORAL, "  ! post-install setup didn't complete cleanly.")
  );
  console.log(
    c(DIM, "  Most likely Python 3.10+ is missing or pip can't reach PyPI.")
  );
  console.log(c(DIM, "  Try manually:"));
  console.log("    bash " + INSTALL_SH);
  console.log("");
  // Important: do NOT exit non-zero — npm would mark the package as broken.
}

process.exit(0);
