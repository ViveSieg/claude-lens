<p align="center">
  <img src="assets/logo.svg" width="120" alt="claude-lens logo" />
</p>

<h1 align="center">claude-lens</h1>

<p align="center">
  <i>See Claude clearly.</i><br>
  Claude Code's terminal replies, rendered live in your browser —
  with real markdown, math, diagrams, and code highlighting.
</p>

<p align="center">
  <a href="https://github.com/ViveSieg/claude-lens/stargazers"><img alt="stars" src="https://img.shields.io/github/stars/ViveSieg/claude-lens?style=for-the-badge&logo=github&color=cc785c&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-lens"><img alt="npm version" src="https://img.shields.io/npm/v/claude-lens?style=for-the-badge&logo=npm&color=cb3837&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-lens"><img alt="npm downloads" src="https://img.shields.io/npm/dm/claude-lens?style=for-the-badge&logo=npm&color=e8a55a&labelColor=141413&label=downloads"></a>
  <a href="https://github.com/ViveSieg/claude-lens/blob/main/LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-5db8a6?style=for-the-badge&labelColor=141413"></a>
</p>

<p align="center">
  <b>English</b> · <a href="README.zh.md">中文</a>
</p>

---

## What does it do?

The terminal squashes everything into monospace text. Math turns into
garbled characters, tables get cut off, diagrams stay as source code.
**claude-lens** mirrors every reply you get from Claude Code into a Chrome
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
npm install -g claude-lens
```

That's it. The package auto-runs its own setup so the slash commands work
inside Claude Code immediately. No `claude-lens setup` needed.

You'll need: macOS or Linux, Python 3.10+, Node 18+, and Claude Code.

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
> **3. Restart** that terminal app fully (Cmd+Q, reopen), then `/lens restart`.
> macOS only re-reads permissions when the process starts.
>
> Sanity check: `~/.claude-lens/listen.log` should be quiet. If it shows
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
/lens on
```

This starts the local mirror server, opens a Chrome tab pointed at it,
and registers a hook so every future reply auto-renders in the tab.
Stop with `/lens off`.

### What you can do in the browser tab

- **Watch replies render live** — markdown, $\LaTeX$, Mermaid diagrams, syntax-highlighted code, tables.
- **Switch between Claude conversations** — every `claude` session you start in any terminal shows up as its own feed in the sidebar.
- **Type back to the terminal** — there's an input bar at the bottom. What you type appears in the feed AND gets typed into your active Claude Code terminal automatically.
- **Paste images** — `Cmd+V` a screenshot directly into the input bar. It uploads, the path gets appended to your message, and Claude can read it.
- **Rename or delete feeds** — click the title to rename, hover a feed to get a `×` delete button.

### The slash commands

| Command | What it does |
|---|---|
| `/lens on` | Start mirror server, hook, browser. |
| `/lens off` | Stop everything. |
| `/lens open` | Re-open the browser tab. |
| `/lens status` | Is the server running? |
| `/lens restart` | Restart the server. |

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

If you also run `/lens on`, replies stream into your browser tab with
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

**Browser → terminal pipeline (macOS):**
1. You type in the lens input bar; press Send.
2. Server writes the text to a FIFO; listener reads it.
3. Listener calls `pbcopy` (handles full Unicode incl. CJK reliably — keystroke injection drops/sticks on non-ASCII).
4. Listener resolves the terminal app's pid via `NSWorkspace`, posts Cmd+V + Return to that pid via `CGEventPostToPid`. **No app activation, no focus flash.**
5. The terminal app receives the keystrokes as if you pressed them — pastes the clipboard, hits Return.

If PyObjC isn't installed (rare — it's a requirements.txt dep), the listener
falls back to AppleScript activate-paste-restore, which works but visibly
flashes the terminal forward and back.

**Pasted images:** dropping/pasting an image into the lens input uploads it
to `~/.claude-lens/uploads/<session>-<stamp>-<rand>.<ext>`. The input shows a
short `[imageN]` alias; on Send it expands to `[image: /full/path]` so the
terminal-side Claude can `Read` the file. The browser feed renders the
token as a 280×220 thumbnail. Old uploads are auto-pruned (default 7 days).

---

## Configuration (you probably don't need this)

| Variable | Default | What it controls |
|---|---|---|
| `CLAUDE_LENS_HOST` | `127.0.0.1` | Bind address. |
| `CLAUDE_LENS_PORT` | `7456` | Port. |
| `CLAUDE_LENS_DATA` | `~/.claude-lens` | Where session files live. |
| `CLAUDE_LENS_LISTEN_GRACE` | `30` | Seconds to wait after browser closes before stopping the typing-listener. |
| `CLAUDE_LENS_FOCUS` | *(auto)* | macOS: name of the terminal app to paste into (e.g. `Ghostty`, `Terminal`, `iTerm`). Auto-detected from `$TERM_PROGRAM` when the server starts; set this to override. |
| `CLAUDE_LENS_UPLOAD_TTL_DAYS` | `7` | macOS/Linux: delete pasted-image files older than N days at server startup. `0` disables cleanup. |

---

## Troubleshooting

**Browser shows "disconnected — retrying…"**
The mirror server isn't running. Run `/lens on` again, or `claude-lens start`.

**Browser typing doesn't reach my terminal (macOS)**
The keystroke injector uses `osascript` and needs **Accessibility**
permission for whichever terminal runs `claude`. See
[macOS one-time setup](#install--one-command) above.
You can confirm this is the cause by checking `~/.claude-lens/listen.log`
for `not allowed assistive access` / `osascript 不允许发送按键 (1002)`.
After granting, restart the terminal and run `/lens restart`.

**Replies stop appearing in the browser**
The Stop hook may have been removed from `~/.claude/settings.json`. Run
`/lens on` to put it back.

**`/tutor init` says NotebookLM tools are missing**
`npm i -g notebooklm-client`, then `npx notebooklm export-session` to log
in to Google. Re-run `/tutor init`.

---

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
  <a href="https://star-history.com/#ViveSieg/claude-lens&Date">
    <img src="https://api.star-history.com/svg?repos=ViveSieg/claude-lens&type=Date" alt="Star history" width="640">
  </a>
</p>

## License

[MIT](LICENSE).
