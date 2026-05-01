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

Got a notebook (course materials, papers, docs) you want Claude to pull
facts from? Run `/tutor init` and walk through the wizard.

It will:

1. Check your tools are installed.
2. List your NotebookLM notebooks — pick one as the **knowledge base**.
3. Pick a **role** for Claude.
4. Generate a `CLAUDE.md` that locks in the contract.

### Roles you can pick

| Role | Best for |
|---|---|
| **research-advisor** | A pile of papers — research workflow with citations. |
| **exam-reviewer** | Course materials — exam prep, key points, common mistakes. |
| **socratic** | Learn by being asked questions instead of told answers. |
| **librarian** | Pure quote retrieval, no commentary. |
| **general** | A flexible default for anything else. |

### The contract that makes this useful

Every role enforces one rule: **anything Claude says about your topic must
come from the notebook**. Claude can rephrase, restructure, draw analogies,
quiz you, write code — but it can't make up facts that aren't in the
notebook. If something isn't covered, Claude has to say so.

You can trust the answers in a way you can't with vanilla chat. The
notebook is your source of truth; Claude is the smart explainer on top.

---

## How it works (one paragraph)

When Claude finishes a reply in your terminal, a hook reads the message and
sends it to a small local server. The server stores it and pushes it to your
browser tab over WebSocket, where it gets rendered. When you type in the
browser, the reverse happens — your message gets typed into the active
terminal so Claude sees it. If the server isn't running, the hook quietly
does nothing — your terminal is never blocked.

---

## Configuration (you probably don't need this)

| Variable | Default | What it controls |
|---|---|---|
| `CLAUDE_LENS_HOST` | `127.0.0.1` | Bind address. |
| `CLAUDE_LENS_PORT` | `7456` | Port. |
| `CLAUDE_LENS_DATA` | `~/.claude-lens` | Where session files live. |
| `CLAUDE_LENS_LISTEN_GRACE` | `30` | Seconds to wait after browser closes before stopping the typing-listener. |

---

## Troubleshooting

**Browser shows "disconnected — retrying…"**
The mirror server isn't running. Run `/lens on` again, or `claude-lens start`.

**Browser typing doesn't reach my terminal**
On macOS, the keystroke injector needs Accessibility permission. Open
System Settings → Privacy & Security → Accessibility, and enable your
terminal app (Terminal.app or iTerm.app). First run usually fails silently
until permission is granted.

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
