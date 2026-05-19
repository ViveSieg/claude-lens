# Debug Notes

This file records the hardest issues found while adapting `claude-iris` to
Codex Desktop on Windows. It intentionally excludes cookies, tokens, account
details, and full NotebookLM responses.

## 1. NotebookLM Login Worked, But `list` Returned Empty

Symptom:

```text
NotebookLM returned zero notebooks for the current CLI login.
```

Cause:

The Google account used by the CLI/browser session did not have access to the
bound notebook, or the session was saved from a browser profile that could not
open the target notebook.

Fix:

Use real Chrome with a dedicated profile and confirm that the target notebook is
visible before saving the session:

```powershell
$env:CODEX_TUTOR_CHROME_PORT="9555"
$env:CODEX_TUTOR_PROFILE_DIR="$env:USERPROFILE\.notebooklm\manual-chrome-profile-9555"
.\codex-iris\tutor.ps1 login
```

## 2. TLS Handshake Failures In Headless/HTTP Mode

Symptom:

```text
SSL routines:ssl3_read_bytes:SSL/TLS alert handshake failure
net::ERR_SSL_VERSION_OR_CIPHER_MISMATCH
```

Cause:

NotebookLM/Google rejected the HTTP/headless transport path on this Windows
machine, especially when a local proxy was involved.

Fix:

Prefer CDP mode. It sends RPC calls from inside an already logged-in Chrome page:

```powershell
$env:CODEX_TUTOR_CHROME_PORT="9555"
$env:CODEX_TUTOR_TRANSPORT="cdp"
```

## 3. CDP Connection Used The Wrong Endpoint

Symptom:

```text
browserType.connectOverCDP: Unexpected status 400 when connecting to
http://127.0.0.1:9555/json/version/
This does not look like a DevTools server, try connecting via ws://.
```

Cause:

Playwright must connect to the `webSocketDebuggerUrl` returned by
`/json/version`, not the HTTP metadata endpoint itself.

Fix:

`notebooklm-manual-login.mjs` and `notebooklm-api.mjs` now read:

```text
http://127.0.0.1:9555/json/version
```

and pass `webSocketDebuggerUrl` to `chromium.connectOverCDP(...)`.

## 4. PowerShell Kept Blinking After NotebookLM Had Already Returned

Symptom:

`detail` or `ask` appeared to hang forever. `netstat` showed a stale Node
process connected to Chrome:

```text
127.0.0.1:<port> -> 127.0.0.1:9555 ESTABLISHED node.exe
```

Debug log from the failing path:

```text
[codex-tutor] detail via cdp start
[codex-tutor] withCdpTransport start
[codex-tutor] CDP create start notebook=b2d4333c-d7ae-456a-9402-e0b9eec4f37b
[codex-tutor] CDP endpoint resolved
[codex-tutor] CDP connected
[codex-tutor] CDP using existing page https://notebooklm.google.com/notebook/<id>
[codex-tutor] CDP waiting for tokens on selected page
[codex-tutor] CDP session extracted
[codex-tutor] withCdpTransport callback start
[codex-tutor] CDP execute start https://notebooklm.google.com/_/LabsTailwindUi/data/batchexecute
[codex-tutor] CDP execute end https://notebooklm.google.com/_/LabsTailwindUi/data/batchexecute length=1848
[codex-tutor] detail via cdp raw length 1848
[codex-tutor] withCdpTransport dispose start
```

Cause:

The NotebookLM RPC had completed, but the Playwright CDP connection was left
open. Node stayed alive even though the answer had already been fetched.

Fix:

`CdpNotebookTransport.dispose()` now calls:

```js
await this.browser.close().catch(() => {});
```

`tutor.ps1` also runs the Node API through a timed `ProcessStartInfo` wrapper so
future failures return a timeout instead of blocking the terminal indefinitely.

## 5. NotebookLM Client High-Level API Hung On Windows

Symptom:

Manual browser-side `fetch` to `batchexecute` returned HTTP 200 quickly, but
`notebooklm-client` high-level `getNotebookDetail()` could still hang in this
environment.

Fix:

CDP mode now bypasses the high-level client for `list`, `detail`, and `ask`.
It directly sends the NotebookLM RPC from the authenticated Chrome page and uses
`notebooklm-client` only for parser helpers and RPC constants.

## 6. Chinese Output Became Mojibake

Symptom:

```text
浠ヤ笅鏄 PID ...
```

Cause:

NotebookLM returned UTF-8, but Windows PowerShell displayed it with a legacy
code page.

Fix:

`tutor.ps1` sets:

```powershell
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $OutputEncoding
[Console]::OutputEncoding = $OutputEncoding
```

and reads Node subprocess output with UTF-8. Users can also run:

```powershell
chcp 65001
```

## Final Verified Commands

```powershell
$env:CODEX_TUTOR_CHROME_PORT="9555"
$env:CODEX_TUTOR_TRANSPORT="cdp"

.\codex-iris\tutor.ps1 detail
.\codex-iris\tutor.ps1 ask "用三句话总结 PID 控制"
```

Verified result:

- `detail` returned the notebook title and 4 sources.
- `ask` returned a Chinese answer with NotebookLM citation markers.
- No stale Node process remained connected to port `9555`.
