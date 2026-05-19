# Codex Iris

Codex Iris is a Windows/Codex Desktop adaptation of
[`ViveSieg/claude-iris`](https://github.com/ViveSieg/claude-iris).

The upstream project renders Claude Code replies in a browser tab and can bind a
Claude project to a read-only NotebookLM notebook. Codex Desktop does not expose
the same Claude hook pipeline, so this port uses the local Codex session files
instead:

```text
C:\Users\Administrator\.codex\sessions\**\*.jsonl
```

It provides two pieces:

- `codex_iris.py`: a local read-only browser mirror for Codex session JSONL.
- `tutor.ps1`: a Codex Tutor command that queries a bound NotebookLM notebook
  and preserves NotebookLM citation markers such as `[1-3]`.

No Python packages are required for the browser mirror. NotebookLM tutor mode
requires Node.js dependencies.

## Requirements

- Windows PowerShell 5+ or PowerShell 7+
- Python 3.10+
- Node.js 20+
- Google Chrome
- A Google account that can open the target NotebookLM notebook

Install the Node dependencies from the project root:

```powershell
npm install notebooklm notebooklm-client playwright undici
npx playwright install chromium
```

## Start The Codex Mirror

Run from the project root:

```powershell
.\codex-iris\start.ps1
```

Open:

```text
http://127.0.0.1:7456
```

Stop it with:

```powershell
.\codex-iris\stop.ps1
```

## NotebookLM Tutor Mode

The most reliable Windows path is to log in with a real Chrome window and then
query NotebookLM through Chrome DevTools Protocol (CDP).

### 1. Log In

```powershell
cd "C:\Users\Administrator\Documents\New project 2"

$env:CODEX_TUTOR_CHROME_PORT="9555"
$env:CODEX_TUTOR_PROFILE_DIR="$env:USERPROFILE\.notebooklm\manual-chrome-profile-9555"

.\codex-iris\tutor.ps1 login
```

When Chrome opens, log in to Google and make sure the target NotebookLM notebook
is visible. Then return to PowerShell and press Enter to save the session.

Keep this Chrome window open while using CDP mode.

### 2. Use Tutor Commands In A New PowerShell

```powershell
cd "C:\Users\Administrator\Documents\New project 2"

$env:CODEX_TUTOR_CHROME_PORT="9555"
$env:CODEX_TUTOR_TRANSPORT="cdp"

.\codex-iris\tutor.ps1 detail
.\codex-iris\tutor.ps1 ask "Summarize PID control in three sentences."
```

`detail` should print the notebook title and source list. `ask` prints the
NotebookLM answer directly in the terminal.

### 3. Bind A Project

```powershell
.\codex-iris\tutor.ps1 init
```

`init` writes:

- `.codex-tutor.json`
- `AGENTS.md`
- `CLAUDE.md`

These files tell future Codex sessions which NotebookLM notebook is the
read-only source of truth.

## Useful Commands

```powershell
.\codex-iris\tutor.ps1 doctor
.\codex-iris\tutor.ps1 login
.\codex-iris\tutor.ps1 list
.\codex-iris\tutor.ps1 detail
.\codex-iris\tutor.ps1 init
.\codex-iris\tutor.ps1 ask "your question"
```

## Important Environment Variables

- `CODEX_TUTOR_CHROME_PORT`: Chrome remote debugging port, commonly `9555`.
- `CODEX_TUTOR_TRANSPORT`: set to `cdp` to force existing Chrome CDP mode.
- `CODEX_TUTOR_PROFILE_DIR`: Chrome profile used during manual login.
- `CODEX_TUTOR_PROXY`: optional proxy, for example `http://127.0.0.1:7890`.
- `CODEX_TUTOR_API_TIMEOUT_MS`: outer PowerShell wrapper timeout.
- `CODEX_TUTOR_CONNECT_TIMEOUT_MS`: Chrome/NotebookLM connection timeout.
- `CODEX_TUTOR_FETCH_TIMEOUT_MS`: browser-side fetch timeout.
- `CODEX_TUTOR_ASK_TIMEOUT_MS`: NotebookLM chat timeout.

## Troubleshooting

### Chinese Output Is Mojibake

If output looks like `浠ヤ笅鏄...`, the terminal is decoding UTF-8 as GBK.
Run:

```powershell
chcp 65001
```

`tutor.ps1` also forces PowerShell and Node subprocess output to UTF-8.

### PowerShell Keeps Blinking Without An Answer

Check for a stuck Node process attached to Chrome:

```powershell
netstat -ano | Select-String -Pattern ':9555'
Get-Process node
```

If a stale `node.exe` owns the connection, stop it:

```powershell
taskkill /PID <pid> /F
```

The current wrapper also has hard timeouts so new calls return an error instead
of waiting forever.

### TLS Handshake Failure

If HTTP mode fails with SSL/TLS errors, use CDP mode:

```powershell
$env:CODEX_TUTOR_CHROME_PORT="9555"
$env:CODEX_TUTOR_TRANSPORT="cdp"
```

This sends NotebookLM RPC requests inside the already logged-in Chrome page.

### Notebook List Is Empty

The Google account used for CLI login cannot see the bound notebook. Open the
NotebookLM URL in the same Chrome profile, confirm access, then run `login`
again.

## Limitations

- NotebookLM is treated as read-only.
- Codex Iris does not send browser input back into Codex Desktop.
- CDP mode depends on the real Chrome window staying open.
- The NotebookLM private RPC surface can change, so this integration includes
  explicit timeouts and a `doctor` command for diagnosis.
