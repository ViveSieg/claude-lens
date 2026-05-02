<p align="center">
  <img src="assets/logo.svg" width="120" alt="claude-iris logo" />
</p>

<h1 align="center">claude-iris</h1>

<p align="center">
  <i>See Claude clearly.</i><br>
  Claude Code's terminal replies, rendered live in your browser —
  with real markdown, math, diagrams, and code highlighting.
</p>

<p align="center">
  <a href="https://github.com/ViveSieg/claude-iris/stargazers"><img alt="stars" src="https://img.shields.io/github/stars/ViveSieg/claude-iris?style=for-the-badge&logo=github&color=cc785c&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-iris"><img alt="npm version" src="https://img.shields.io/npm/v/claude-iris?style=for-the-badge&logo=npm&color=cb3837&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-iris"><img alt="npm downloads" src="https://img.shields.io/npm/dm/claude-iris?style=for-the-badge&logo=npm&color=e8a55a&labelColor=141413&label=downloads"></a>
  <a href="https://github.com/ViveSieg/claude-iris/blob/main/LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-5db8a6?style=for-the-badge&labelColor=141413"></a>
</p>

<p align="center">
  <b>English</b> · <a href="README.zh.md">中文</a>
</p>

---

## What does it do?

The terminal squashes everything into monospace text. Math turns into
garbled characters, tables get cut off, diagrams stay as source code.
**claude-iris** mirrors every reply you get from Claude Code into a Chrome
tab where it actually looks the way it was written.

You keep typing in your terminal. The browser is a beautiful read-only
window — same conversation, two views.

```
┌─ terminal ─────────────────┐    ┌─ browser ─────────────────────┐
│ > help me with bessel ...  │    │  ## Bessel functions          │
│                            │ ──►│                               │
│ <reply streams here>       │    │  J_n(x) = …  (rendered math)  │
│                            │    │  ┌────────┐  (real tables)    │
│                            │    │  │        │                   │
│                            │    │  └────────┘                   │
└────────────────────────────┘    └───────────────────────────────┘
```

---

## Install — one command

```bash
npm install -g claude-iris
```

That's it. The package auto-runs its own setup so the slash commands work
inside Claude Code immediately. No `claude-iris setup` needed.

You'll need: macOS or Linux (or [WSL2 on Windows](#windows-via-wsl2)),
Python 3.10+, Node 18+, and Claude Code. The installer pre-flights all of
these and prints copy-paste apt / brew commands if any are missing.

**Upgrading later:**

```bash
npm i -g claude-iris@latest
```

Re-runs the post-install with the new version, refreshes the venv (any
new requirements get installed), and updates the slash commands so the
latest behavior of `/iris` and `/tutor` lands without any other action.

### <a id="windows-via-wsl2"></a> Windows — via WSL2

Native Windows isn't supported. The keystroke-injection layer needs PyObjC
(macOS) or xdotool (Linux), neither of which can drive Windows Terminal.
**Install WSL2 instead**, which is also Anthropic's recommended path for
Claude Code on Windows. The mirror server runs in WSL Linux; the browser
opens on the Windows host. Inside WSL the page runs in **read-only mode**
— assistant replies still stream live, but the input bar is hidden because
typing back into the terminal from the page isn't possible across the
WSL ↔ Windows boundary.

**One-time WSL2 setup** (PowerShell as admin):

```powershell
wsl --install -d Ubuntu
```

That installs WSL2 itself and Ubuntu **24.04 LTS** (the current default —
recommended). Reboot if prompted. On Win11 with WSLg this also enables GUI
forwarding automatically.

> Why Ubuntu 24.04? It ships with Python 3.12, modern OpenSSL, and pre-built
> wheels for everything in `requirements.txt`. Older images (20.04, Debian
> bullseye) work too but you'll need to manually upgrade Python.

**Then inside the Ubuntu shell**:

```bash
# 1. Tools claude-iris depends on (Ubuntu's nodejs is too old by default;
#    use NodeSource for Node 20 LTS):
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt update
sudo apt install -y nodejs python3 python3-venv python3-pip

# 2. Claude Code (per Anthropic's official docs):
npm install -g @anthropic-ai/claude-code

# 3. claude-iris itself:
npm install -g claude-iris
```

The post-install pre-flights `python3 / venv / node / npm`. If anything's
missing it stops with the exact apt one-liner. From then on, every Claude
Code session inside Ubuntu can use `/iris on`, `/tutor init`, and the rest
exactly like on macOS — minus the input bar.

**Tip:** put your project under `~/projects/...` *inside* WSL rather than
on `/mnt/c/...`. WSL → Windows filesystem crossing is ~10× slower, and
Claude Code's transcript poller will feel the lag.

**What happens during install:** post-install creates a sandboxed Python venv
inside the package directory and installs everything from `server/requirements.txt`
into it (FastAPI/uvicorn, plus PyObjC `Quartz` + `Cocoa` on macOS for
background paste). **Nothing touches your global Python.** Last line of the
install output should say `>>> macOS background-paste ready (PyObjC Quartz + AppKit)`
on macOS — if instead you see `PyObjC import failed`, the install hint
shows the one-liner to retry.

> **macOS one-time setup — required for "type back to terminal"**
>
> Browser → terminal typing posts synthetic keyboard events to your
> terminal app. The default path uses **Quartz `CGEventPostToPid`** so
> the paste happens in the background without stealing focus from the
> browser tab. **Grant the permissions below before your first Send** —
> otherwise the listener silently no-ops and you'll see your message in
> the browser but nothing in the terminal.
>
> **1. Accessibility** (always required — must be added manually)
> **System Settings → Privacy & Security → Accessibility** → click `+`,
> add your **terminal app**: `Terminal.app`, `iTerm`, `Ghostty`,
> `WezTerm`, `Alacritty` etc. — whichever one runs `claude` — and
> **toggle the switch ON**. Adding without toggling does nothing.
>
> **2. Automation** (only matters if Quartz path falls back to AppleScript)
> If `pyobjc-framework-Quartz` isn't installed (rare — it's a requirements
> dep), the listener falls back to `osascript` which needs Automation
> permission. macOS pops *"… wants to control 'System Events.app'."* on
> first send — click **OK**. If you misclicked, fix it at **System
> Settings → Privacy & Security → Automation** → expand your terminal app
> → enable `System Events`.
>
> **3. Restart** that terminal app fully (Cmd+Q, reopen), then `/iris restart`.
> macOS only re-reads permissions when the process starts.
>
> Sanity check: `~/.claude-iris/listen.log` should be quiet. If it shows
> `not allowed assistive access` / `osascript 不允许发送按键 (1002)`,
> Accessibility isn't on yet. If it shows `Not authorized to send Apple
> events to System Events`, Automation isn't on yet.
>
> Receiving replies in the browser does **not** need either permission —
> only the input-bar typing does.

---

## Use it

Inside any Claude Code session, type:

```
/iris on
```

This starts the local mirror server, opens a Chrome tab pointed at it,
and registers a hook so every future reply auto-renders in the tab.
Stop with `/iris off`.

### Recommended layout

The right layout depends on platform, because what iris can do at the
terminal differs between macOS (full bidirectional, no focus flash) and
WSL (read-only mirror).

- **macOS — browser-only is fine, minimize the terminal.** Background
  paste via Quartz `CGEventPostToPid` means the terminal never needs
  focus — it doesn't even need to be visible. Open `/iris on`, minimize
  your terminal, and live entirely in the iris tab: type prompts in the
  input bar, read replies in the rendered feed. The terminal still exists
  and Claude Code is still doing real work behind the scenes; you just
  don't have to look at it.
- **Windows + WSL — split-screen, browser LEFT, terminal RIGHT.** Under
  WSL the iris page runs in read-only mode (input bar is hidden), so you
  type prompts directly in the terminal. Side-by-side is the only sane
  workflow there.
  - Drag Chrome to the left edge until snap kicks in (or `Win + ←`), then
    pick the right half for Windows Terminal from the snap layouts that
    appear (or `Win + →` after focusing the terminal).
  - Power user: split the WT pane itself (`Alt+Shift+D`) and run
    `claude` on one side / a free shell on the other — both panes still
    sit inside the right half of the screen.
- **Linux native — your call.** Full bidirectional like macOS, so
  browser-only is comfortable; or `Super` + `←/→` for half-screen if you
  prefer eyes on both.
- **Linux:** GNOME / KDE both honour `Super` + `←/→` for half-screen tile.

The "↓ Bottom" button in the iris feed means you can scroll up and read
older replies without losing track of the latest — new messages do **not**
auto-scroll the feed (intentional UX choice so you don't get yanked away
mid-paragraph).

### What you can do in the browser tab

- **Watch replies render live** — markdown, $\LaTeX$, Mermaid diagrams, syntax-highlighted code, tables.
- **Switch between Claude conversations** — every `claude` session you start in any terminal shows up as its own feed in the sidebar.
- **Type back to the terminal** — there's an input bar at the bottom. What you type appears in the feed AND gets typed into your active Claude Code terminal automatically.
- **Paste images** — `Cmd+V` a screenshot directly into the input bar. It uploads, the path gets appended to your message, and Claude can read it.
- **Rename or delete feeds** — click the title to rename, hover a feed to get a `×` delete button.

### The slash commands

| Command | What it does |
|---|---|
| `/iris on` | Start mirror server, hook, browser. |
| `/iris off` | Stop everything. |
| `/iris open` | Re-open the browser tab. |
| `/iris status` | Is the server running? |
| `/iris restart` | Restart the server. |

---

## Optional: connect a NotebookLM notebook

`/tutor` is a wizard that wires a **NotebookLM notebook** (your course
materials, papers, internal docs) into the project as a **read-only**
knowledge base, and locks Claude into a contract: *every domain fact in
the answer must come from the notebook, or Claude must explicitly say
"not covered."*

### First-time setup — `/tutor init`

In any terminal in your project directory:

```
cd path/to/your/project
claude
```

Then inside Claude Code:

```
/tutor init
```

The wizard walks four steps:

**1. Doctor** — checks Node, npm, the `notebooklm-client` package, and
   that you've signed into Google once. If `notebooklm-client` is
   missing it offers `npm i -g notebooklm-client`. If the Google session
   is missing it runs `npx notebooklm export-session` and pops a browser
   for you to sign in.

**2. Pick a notebook** — lists your existing NotebookLM notebooks and
   asks you to choose the one for *this* project. The wizard captures
   its id + title.

**3. Pick a role** — five built-ins or a custom one (table below).

**4. Render `CLAUDE.md` + `AGENTS.md`** in the project root, with the
   notebook id, title, and chosen role baked in. Future `claude`
   sessions in this directory automatically pick up the contract.

### Sub-commands

| Command | What it does |
|---|---|
| `/tutor init` | Full interactive setup (the four steps above). |
| `/tutor doctor` | Re-run the tool/auth check only — useful after `npm i -g notebooklm-client` or re-login. |
| `/tutor notebook` | Re-pick the notebook for this project (keeps role). |
| `/tutor role` | Re-pick the role (keeps notebook). |
| `/tutor ask "<question>"` | One-shot: query the bound notebook and print the answer with `[1][2]` citations preserved. |

### Roles you can pick

| Role | Best for |
|---|---|
| **research-advisor** | A pile of papers — research workflow with `资料显示 / 我做了什么 / 结论 / 资料没覆盖的`. |
| **exam-reviewer** | Course materials — exam prep with `资料显示 / 我怎么讲 / 考点整理 / 解题方法 / 易错点 / 结论 / 资料没覆盖的`. |
| **socratic** | Learn by being asked. Outputs `我反问你 (3 题) / 校对 / 资料没覆盖的`. |
| **librarian** | Pure quote retrieval, no commentary. Outputs `资料显示 / 来源对照表 / 资料未覆盖`. |
| **general** | Flexible default — `资料显示 / 我的处理 / 结论 / 资料没覆盖的`. |
| **custom** | Roll your own (`/tutor init` step 3, option 6). The wizard still wires in the contract. |

### After setup, just talk

Once `CLAUDE.md` is generated, every reply Claude gives in this project
queries the notebook first via `notebooklm-client` (the integration is
called from inside the role's prompt), then repackages the answer in the
chosen format. No further commands needed.

If you also run `/iris on`, replies stream into your browser tab with
proper LaTeX, Mermaid diagrams, and code highlighting — useful for
courses with formulas (the `exam-reviewer` role assumes this).

### The contract that makes this useful

Every role enforces one rule: **anything Claude says about your topic
must come from the notebook**. Claude can rephrase, restructure, draw
analogies, quiz you, write code — but it cannot make up facts that
aren't in the notebook. If something isn't covered, Claude has to say
so explicitly. Citations like `[1][2]` from the notebook are preserved
verbatim in answers.

You can trust the answers in a way you can't with vanilla chat. The
notebook is your source of truth; Claude is the smart explainer on top.

---

## How it works (one paragraph)

When Claude finishes a reply in your terminal, a hook reads the message and
sends it to a small local server. The server stores it and pushes it to your
browser tab over WebSocket, where it gets rendered. When you type in the
browser, the reverse happens — the listener pastes your message via the
clipboard into your terminal app. On macOS it does this in the **background**
via Quartz (`CGEventPostToPid`) so the terminal never steals focus from your
browser tab. If the server isn't running, the hook quietly does nothing —
your terminal is never blocked.

**Two-path safety net.** Claude Code only reads hook config at session start,
so a Claude conversation that was already running before `/iris on` doesn't
hold the Stop hook and won't push. iris closes the gap by polling
`~/.claude/projects/*/<sid>.jsonl` every 2s (`CLAUDE_IRIS_POLL_INTERVAL`) for
transcripts touched in the last 10 minutes, importing any new turns directly.
Both paths share fingerprint-based dedup, so you never get duplicates. **Net
effect:** every assistant turn from every running Claude session lands in the
browser within at most 2 seconds, with or without the hook.

**Browser → terminal pipeline (macOS):**
1. You type in the iris input bar; press Send.
2. Server writes the text to a FIFO; listener reads it.
3. Listener calls `pbcopy` (handles full Unicode incl. CJK reliably — keystroke injection drops/sticks on non-ASCII).
4. Listener resolves the terminal app's pid via `NSWorkspace`, posts Cmd+V + Return to that pid via `CGEventPostToPid`. **No app activation, no focus flash.**
5. The terminal app receives the keystrokes as if you pressed them — pastes the clipboard, hits Return.

If PyObjC isn't installed (rare — it's a requirements.txt dep), the listener
falls back to AppleScript activate-paste-restore, which works but visibly
flashes the terminal forward and back.

**Pasted images:** dropping/pasting an image into the iris input uploads it
to `~/.claude-iris/uploads/<session>-<stamp>-<rand>.<ext>`. The input shows a
short `[imageN]` alias; on Send it expands to `[image: /full/path]` so the
terminal-side Claude can `Read` the file. The browser feed renders the
token as a 280×220 thumbnail. Old uploads are auto-pruned (default 7 days).

---

## Configuration (you probably don't need this)

| Variable | Default | What it controls |
|---|---|---|
| `CLAUDE_IRIS_HOST` | `127.0.0.1` | Bind address. |
| `CLAUDE_IRIS_PORT` | `7456` | Port. |
| `CLAUDE_IRIS_DATA` | `~/.claude-iris` | Where session files live. |
| `CLAUDE_IRIS_LISTEN_GRACE` | `30` | Seconds to wait after browser closes before stopping the typing-listener. |
| `CLAUDE_IRIS_FOCUS` | *(auto)* | macOS: name of the terminal app to paste into (e.g. `Ghostty`, `Terminal`, `iTerm`). Auto-detected from `$TERM_PROGRAM` when the server starts; set this to override. |
| `CLAUDE_IRIS_UPLOAD_TTL_DAYS` | `7` | Delete pasted-image files older than N days (at startup and every 6h). `0` disables. |
| `CLAUDE_IRIS_SESSION_TTL_DAYS` | `30` | Delete session jsonls untouched for N days. `0` disables. |
| `CLAUDE_IRIS_POLL_INTERVAL` | `2` | Transcript fallback poll interval (seconds). `0` disables polling and relies on the Stop hook only. |
| `CLAUDE_IRIS_POLL_WINDOW` | `600` | Polling only considers transcripts modified in the last N seconds. |
| `CLAUDE_IRIS_CLEANUP_INTERVAL` | `21600` | Background TTL sweep period (seconds, default 6h). |
| `CLAUDE_IRIS_TRANSCRIPT_CACHE_MAX` | `32` | LRU cap on parsed-transcript cache entries. Each entry is the parsed turn list of one session; bumping this trades RAM for fewer re-walks of long jsonls. |
| `CLAUDE_IRIS_READ_ONLY` | *(unset)* | Set to `1` to force read-only mode on any platform (hides the input bar, no listener, /input returns 409). WSL is auto-detected — you only need this for testing the read-only UI on macOS/Linux. |
| `CLAUDE_IRIS_ENDPOINT` | `http://127.0.0.1:7456/push` | Where the Stop hook POSTs assistant turns. Override only if you ran the server under a non-default `CLAUDE_IRIS_HOST` / `CLAUDE_IRIS_PORT`. |
| `CLAUDE_IRIS_TIMEOUT` | `0.8` | Stop-hook POST timeout in seconds. Stays tight so a slow / dead server can't add latency between Claude turns. |
| `CLAUDE_IRIS_SKIP_POSTINSTALL` | *(unset)* | Set to `1` before `npm i -g claude-iris` to skip the auto-setup (CI, Dockerfiles). Run `claude-iris setup` manually afterwards. |

---

## Troubleshooting

**Browser shows "disconnected — retrying…"**
The mirror server isn't running. Run `/iris on` again, or `claude-iris start`.

**Browser typing doesn't reach my terminal (macOS)**
The keystroke injector uses `osascript` and needs **Accessibility**
permission for whichever terminal runs `claude`. See
[macOS one-time setup](#install--one-command) above.
You can confirm this is the cause by checking `~/.claude-iris/listen.log`
for `not allowed assistive access` / `osascript 不允许发送按键 (1002)`.
After granting, restart the terminal and run `/iris restart`.

**Replies stop appearing in the browser**
The Stop hook may have been removed from `~/.claude/settings.json`. Run
`/iris on` to put it back. Even if the hook is genuinely missing, the
2-second transcript poller will catch up new turns automatically.

**A session I × out of the sidebar comes back later**
That's not happening — DELETE writes a tombstone (`~/.claude-iris/sessions/<id>.deleted`) that the poller respects, so a hard-deleted session stays gone. To bring one back manually:
```bash
rm ~/.claude-iris/sessions/<session-id>.deleted
```
Or just type into the iris input bar with that session selected — `/input` lifts the tombstone automatically (treats typing as explicit re-engagement).

**`/tutor init` says NotebookLM tools are missing**
`npm i -g notebooklm-client`, then `npx notebooklm export-session` to log
in to Google. Re-run `/tutor init`.

---

## Design limits

claude-iris is built for **single-machine, single-user, one-Claude-terminal-at-a-time** workflows. The three constraints below are direct architectural choices, not bugs to file:

- **The listener is global, not per-session.** A single `listen.py` types into whichever terminal is currently focused (or whatever `CLAUDE_IRIS_FOCUS` points at). If you have two Claude Code terminals running, browser input still goes only to the focused one — `session_id` doesn't route keystrokes.
- **`/push` trusts localhost implicitly.** The server listens on `127.0.0.1` with no auth; any local process can write to any session. Don't expose port 7456 to the public internet on an untrusted box.
- **`DATA_DIR` is owned by one user.** Defaults to `~/.claude-iris/`. Different OS users on the same machine each get their own dir, but running two iris servers under the same user collides on PID file, FIFO, and session jsonls.

## What's planned

- Streaming partial-message rendering.
- A simple way to share the mirror over the network or via a public tunnel.
- More role templates (translation, case analysis, speech coach).

## Contributing

Issues and PRs welcome. Two non-negotiables:

1. The Stop hook must never block your shell.
2. The "facts come from the notebook" contract is the heart of the tutor layer. New roles must enforce it.

## Credits

- Built on top of [Claude Code](https://docs.claude.com/en/docs/claude-code/overview).
- NotebookLM access via [`notebooklm-client`](https://github.com/icebear0828/notebooklm-client).
- Rendering: [marked](https://marked.js.org/) · [KaTeX](https://katex.org/) · [Mermaid](https://mermaid.js.org/) · [highlight.js](https://highlightjs.org/).

## Star history

<p align="center">
  <a href="https://star-history.com/#ViveSieg/claude-iris&Date">
    <img src="https://api.star-history.com/svg?repos=ViveSieg/claude-iris&type=Date" alt="Star history" width="640">
  </a>
</p>

## License

[MIT](LICENSE).
