<p align="center">
  <img src="assets/logo.svg" width="120" alt="claude-lens logo" />
</p>

<h1 align="center">claude-lens</h1>

<p align="center">
  <i>See Claude clearly.</i><br>
  Live-render Claude Code's terminal replies in a browser tab — markdown, LaTeX, Mermaid, syntax highlighting.
</p>

<p align="center">
  <a href="https://github.com/ViveSieg/claude-lens/stargazers"><img alt="stars" src="https://img.shields.io/github/stars/ViveSieg/claude-lens?style=for-the-badge&logo=github&color=cc785c&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-lens"><img alt="npm version" src="https://img.shields.io/npm/v/claude-lens?style=for-the-badge&logo=npm&color=cb3837&labelColor=141413"></a>
  <a href="https://www.npmjs.com/package/claude-lens"><img alt="npm downloads" src="https://img.shields.io/npm/dm/claude-lens?style=for-the-badge&logo=npm&color=e8a55a&labelColor=141413&label=downloads"></a>
  <a href="https://github.com/ViveSieg/claude-lens/blob/main/LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-5db8a6?style=for-the-badge&labelColor=141413"></a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=for-the-badge&logo=python&logoColor=white&labelColor=141413">
  <img alt="Node" src="https://img.shields.io/badge/node-18%2B-339933?style=for-the-badge&logo=nodedotjs&logoColor=white&labelColor=141413">
  <img alt="macOS · Linux" src="https://img.shields.io/badge/platform-macOS%20%C2%B7%20Linux-faf9f5?style=for-the-badge&labelColor=141413">
</p>

<p align="center">
  <b>English</b> · <a href="README.zh.md">中文</a>
</p>

---

## The problem

Claude Code is a **terminal app**. The terminal renders markdown, but it
flattens everything that doesn't fit a monospace grid:

| What you wrote | What the terminal shows |
|---|---|
| `$\beta = i_C / i_B$` | `β = i_C / i_B` *(escaped, ugly, sometimes broken)* |
| ```mermaid\nflowchart LR\n  A --> B``` | the source code, no diagram |
| Wide tables, syntax-highlighted code, callouts, footnotes | best-effort, often clipped |

Workarounds — copy the reply, paste into a markdown previewer, render it,
swap context — break the loop you're in. **claude-lens** removes the
swap: the same reply that lands in your terminal also appears in a Chrome
tab, fully rendered, in real time.

```
┌─ terminal ─────────────────┐    ┌─ http://127.0.0.1:7456 ──────┐
│ > /lens on                 │    │  Claude Lens                 │
│ > help me with bessel ...  │ ──►│  ─────────────────────────── │
│                            │    │  ## Bessel functions         │
│ <reply streams here>       │    │  J_n(x) = …    (KaTeX)       │
│                            │    │  ┌─────┬─────┐               │
│                            │    │  │ tables render             │
│                            │    │  └─────┴─────┘               │
│                            │    │  ```python … ``` highlighted │
└────────────────────────────┘    └──────────────────────────────┘
```

## What it gives you

| | |
|---|---|
| 🪞 **Mirror** | A Stop hook + local FastAPI + Chrome tab. Every assistant turn auto-renders within ~100 ms. |
| 🎓 **Tutor** *(optional)* | Interactive wizard binding a project to a fixed NotebookLM knowledge base, with five pre-built role templates. |
| 🔭 **Per-session feed** | Each Claude Code session gets its own URL and persistent JSONL history. Add ➕ / delete × / rename ✎ from the sidebar. |
| ↩️ **Bidirectional input** | Browser input bar persists as a `user` message in the session AND writes to a named pipe a terminal wrapper can read. |
| ✂️ **Copy buttons** | Per message: copy markdown source or copy plain text. |
| 🗂️ **TOC sidebar** | Auto-generated from `##`/`###` headings. |
| 🎨 **Editorial design** | Cream canvas + coral accents + serif headlines. |
| 🛡️ **Fail-quiet** | If the server isn't running, the hook silently no-ops. **Never blocks the shell.** |

## Quickstart

```bash
npm install -g claude-lens
claude-lens setup

# in any Claude Code session:
/lens on              # start mirror, register Stop hook, open Chrome
/tutor init           # (optional) bind this project to a NotebookLM knowledge base
```

From source:

```bash
git clone https://github.com/ViveSieg/claude-lens.git
cd claude-lens
./install.sh
```

## Mirror — the core layer

### Pipeline

```
Claude Code session
        │
        │  (assistant turn ends)
        ▼
   Stop hook ──► hooks/stop_lens.py
        │
        │  reads transcript_path, extracts last assistant message
        ▼
   POST /push ──► FastAPI (server/main.py)
                   │
                   ├─► append to ~/.claude-lens/sessions/<id>.jsonl
                   └─► broadcast to all WebSocket clients
                              │
                              ▼
                       Chrome tab renders
                       (marked + KaTeX + Mermaid + highlight.js)
```

### Stop-hook payload

```json
{
  "session_id":    "<claude code session id>",
  "session_label": "<cwd basename>",
  "role":          "assistant",
  "content":       "<the markdown reply>"
}
```

### CLI

```
/lens on        start server, register Stop hook, open browser
/lens off       stop server, remove hook
/lens open      re-open the browser tab
/lens status    is the server running?
/lens restart   bounce server
```

The browser auto-opens in Chrome → Chromium → Brave → Edge → system default.

## Tutor — optional NotebookLM layer

`/tutor` scaffolds a project so Claude Code is **bound to a fixed
NotebookLM notebook as a read-only knowledge base** — not a teacher, not
a writeable store. Claude does all the teaching; NotebookLM only
retrieves.

### The Source Anchoring principle

> **Every domain claim in Claude's output must trace to a `/notecraft chat`
> citation.** Claude can repackage, structure, drill, quiz, analogize,
> derive — but never invents domain facts. If the notebook doesn't say
> it, Claude says "not covered" and stops.

This is enforced by every role template. Mechanical operations (algebra,
code execution, file I/O, formatting) don't need a citation. New domain
claims do.

### The wizard

```
/tutor init
  ├─ ① doctor         node, npm, notebooklm-client, Google session, lens server
  ├─ ② notebook       lists your notebooks, you pick one as the knowledge base
  ├─ ③ role           pick from 5 templates (or write a custom one)
  ├─ ④ scaffold       writes ./CLAUDE.md, ./AGENTS.md, ./.claude-lens.json
  ├─ ⑤ start          starts the mirror server + opens Chrome
  └─ ⑥ smoke test     runs one query so you see the full pipeline live
```

Subcommands:

```
/tutor init       full wizard
/tutor notebook   swap the notebook in the current project
/tutor role       swap the role in the current project
/tutor doctor     health-check the current project
/tutor ask "..."  one-shot query through the configured notebook+role
```

### Roles bundled in v0.1

| Role | When to pick | Output schema |
|---|---|---|
| `research-advisor` | Paper pile / literature corpus | Sources / What I did / Conclusion / Not covered |
| `exam-reviewer` | Course materials (lecture notes, textbook chapters, problem sets) | Sources / How I'd explain / Exam topics / Approach / Common mistakes / Conclusion / Not covered |
| `socratic` | Inquiry-driven learning — agent asks instead of answers, uses notebook as fact-check | I ask you / Check (sources) / Not covered |
| `librarian` | Strict retrieval, no commentary, original quotes only | Sources / Source table / Not covered |
| `general` | Catch-all when none of the above quite fits | Sources / My processing / Conclusion / Not covered |

> The bundled role templates render their output sections in Chinese
> (`资料显示`, `我做了什么`, etc.) by default. Translate the files in
> `roles/` if you want fully English output.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `CLAUDE_LENS_HOST` | `127.0.0.1` | bind host |
| `CLAUDE_LENS_PORT` | `7456` | port |
| `CLAUDE_LENS_DATA` | `~/.claude-lens` | session JSONL + pid file |
| `CLAUDE_LENS_ENDPOINT` | `http://127.0.0.1:7456/push` | where the Stop hook POSTs |
| `CLAUDE_LENS_TIMEOUT` | `1.5` | Stop-hook HTTP timeout (s) |

To run a second instance side-by-side (e.g. for two users on a shared
machine), give it a different `CLAUDE_LENS_PORT` and `CLAUDE_LENS_DATA`.

## Bidirectional input

The browser tab has an input bar at the bottom. Submitting does two things:

1. **Persists a `user` message in the current session** — `curl
   http://127.0.0.1:7456/session/<id>` returns it; full history is preserved.
2. **Writes to a named pipe at `~/.claude-lens/input.pipe`** — any terminal
   wrapper can `cat` it.

claude-lens does not auto-inject into Claude Code's prompt — wire that
into a custom shell loop yourself.

## Troubleshooting

**The browser tab is empty / "disconnected — retrying…"**
Check `claude-lens status`. If not running, `claude-lens start`. If port
7456 is taken, set `CLAUDE_LENS_PORT` to something free and re-run
`/lens on`.

**`/tutor init` says `notebooklm-client: MISSING`**
`npm i -g notebooklm-client`. If you see `EACCES`, prefix with `sudo`.

**`/tutor init` says session is missing**
Run `npx notebooklm export-session` — it opens a browser, you sign into
Google, the session is cached at `~/.notebooklm/session.json`. Re-run
the wizard.

**Replies stop appearing in the browser**
The Stop hook may have been removed from `~/.claude/settings.json`. Run
`/lens on` again — it merges the hook back in safely.

## Roadmap

- [ ] Streaming partial-message rendering (today: full message at end of turn)
- [ ] Optional public-tunnel mode (Cloudflare Tunnel / ngrok wrapper)
- [ ] Per-role linting: warn when an output is missing a `[citation]` it should have
- [ ] More roles: `case-analyst`, `translator`, `speech-coach`
- [ ] Built-in `claude-lens listen` to consume the input pipe and forward to your shell loop

## Contributing

Issues and PRs welcome. Two principles to keep in mind if you touch core code:

1. **The Stop hook must never block the shell.** Any path that talks to
   the server must time out fast and silently no-op on failure.
2. **The Source Anchoring contract is the spine of the tutor layer.** New
   roles must enforce it; PRs that loosen it need to make a strong case.

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

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:cc785c,100:e8a55a&height=120&section=footer" alt="" />
</p>
