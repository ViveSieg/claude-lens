/* claude-iris frontend */

const params = new URLSearchParams(location.search);
const explicitSession = params.get("session");
let currentSession = explicitSession || "default";
// Pin = "user has chosen this session, don't auto-jump to a newer one."
// Pinned by: explicit ?session=, sidebar click, manual rename. Not pinned by
// just typing in the input (because the reply lands on the same session).
let pinnedSession = !!explicitSession;
let indexWs = null;
let wsHasConnectedOnce = false;
// Paste-to-upload aliases — kept at module scope so resetPasteState (used
// by switchSession defined further down) can clear them without hitting TDZ.
let pasteCounter = 0;
const pasteAliases = new Map(); // alias text → full path

const els = {
  wsDot: document.getElementById("ws-dot"),
  wsLabel: document.getElementById("ws-label"),
  sessionList: document.getElementById("session-list"),
  toc: document.getElementById("toc"),
  feedTitle: document.getElementById("session-title"),
  feedMeta: document.getElementById("session-meta"),
  messages: document.getElementById("messages"),
  btnClear: document.getElementById("btn-clear"),
  btnCopyAll: document.getElementById("btn-copy-all"),
  btnScroll: document.getElementById("btn-scroll"),
  inputForm: document.getElementById("input-form"),
  inputField: document.getElementById("input-field"),
};

let ws = null;
let messageCache = [];

// ---------- markdown ----------

marked.setOptions({
  gfm: true,
  breaks: false,
  highlight: function (code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value; } catch (_) {}
    }
    try { return hljs.highlightAuto(code).value; } catch (_) {}
    return code;
  },
});

mermaid.initialize({
  startOnLoad: false,
  theme: "base",
  themeVariables: {
    background: "#f5f0e8",
    primaryColor: "#efe9de",
    primaryBorderColor: "#cc785c",
    primaryTextColor: "#141413",
    lineColor: "#6c6a64",
    fontFamily: "Inter, sans-serif",
  },
});

function renderMarkdown(container, src) {
  // Pre-extract mermaid blocks so marked doesn't mangle them.
  const mermaidBlocks = [];
  let protectedSrc = src.replace(/```mermaid\n([\s\S]*?)```/g, (_, code) => {
    const id = mermaidBlocks.length;
    mermaidBlocks.push(code.trim());
    return `<div class="mermaid-slot" data-mid="${id}"></div>`;
  });

  // Replace [image: /abs/path/.../<name>] tokens with a clickable
  // thumbnail. Stored content keeps the full path so the listener still
  // types it into the terminal — this is display-only.
  let imgN = 0;
  protectedSrc = protectedSrc.replace(/\[image:\s*([^\]]+)\]/g, (_, raw) => {
    imgN++;
    const path = raw.trim();
    // Drop any path segments first (defense-in-depth against `../`),
    // then URL-encode so unicode filenames (e.g. `中文.png`) survive
    // round-tripping. The /uploads endpoint already accepts unicode
    // alphanumerics — stripping them client-side broke valid paths.
    const filename = path.split("/").pop() || "";
    const safe = encodeURIComponent(filename);
    const titleAttr = path.replace(/"/g, "&quot;");
    return ` <a href="/uploads/${safe}" target="_blank" rel="noopener" class="msg-img-link" title="${titleAttr}"><img src="/uploads/${safe}" alt="image${imgN}" class="msg-img" /></a> `;
  });

  // Sanitize before injection: marked@12 doesn't strip HTML, and /push
  // accepts content from any localhost process, so a hostile (or buggy)
  // local writer could otherwise plant <script> in the feed. DOMPurify
  // keeps inline formatting and our own image-link tags but drops
  // script/iframe/event-handler attributes etc.
  const html = marked.parse(protectedSrc);
  container.innerHTML = (window.DOMPurify
    ? DOMPurify.sanitize(html, { ADD_ATTR: ["target", "rel"] })
    : html);

  // KaTeX
  if (window.renderMathInElement) {
    renderMathInElement(container, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
      strict: false,
      macros: { "\\dfrac": "\\frac" },
    });
  }

  // Mermaid — use mermaid.render() (more reliable than mermaid.run() on dynamic DOM).
  // Mermaid output bypasses the marked → DOMPurify sanitize above (it's
  // injected later as raw SVG), so we sanitize the SVG separately under
  // the SVG profile before assigning innerHTML.
  container.querySelectorAll(".mermaid-slot").forEach((slot) => {
    const idx = parseInt(slot.dataset.mid, 10);
    const code = mermaidBlocks[idx];
    const renderId = "m-" + Math.random().toString(36).slice(2, 10);
    mermaid
      .render(renderId, code)
      .then(({ svg, bindFunctions }) => {
        slot.innerHTML = window.DOMPurify
          ? DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } })
          : svg;
        slot.classList.add("mermaid");
        if (bindFunctions) bindFunctions(slot);
      })
      .catch((err) => {
        const safe = code.replace(/[<>]/g, (c) => (c === "<" ? "&lt;" : "&gt;"));
        const errMsg = err && err.message ? err.message : "render failed";
        slot.innerHTML =
          '<pre style="background:#fdf3f0;border-left:3px solid #c64545;padding:12px 14px;border-radius:6px;color:#c64545;overflow:auto;font-family:JetBrains Mono,ui-monospace,monospace;font-size:13px"><code>Mermaid: ' +
          errMsg +
          "\n\n" +
          safe +
          "</code></pre>";
      });
  });
}

// ---------- session list ----------

async function loadSessions() {
  try {
    const r = await fetch("/sessions");
    const data = await r.json();
    renderSessionList(data.sessions);
  } catch (e) {
    console.error("loadSessions failed", e);
  }
}

function renderSessionList(sessions) {
  els.sessionList.innerHTML = "";

  if (sessions.length === 0) {
    const empty = document.createElement("div");
    empty.className = "session-item";
    empty.style.color = "var(--muted)";
    empty.style.fontStyle = "italic";
    empty.textContent = "No sessions yet";
    els.sessionList.appendChild(empty);
    return;
  }
  for (const s of sessions) {
    const item = document.createElement("div");
    item.className = "session-item" + (s.id === currentSession ? " active" : "");

    const main = document.createElement("div");
    main.className = "session-item-main";
    main.onclick = () => switchSession(s.id);

    const label = document.createElement("div");
    label.className = "session-item-label";
    label.textContent = s.label || s.id;
    main.appendChild(label);

    const idEl = document.createElement("div");
    idEl.className = "session-item-id";
    idEl.textContent = s.id.slice(0, 16) + (s.id.length > 16 ? "…" : "");
    main.appendChild(idEl);

    item.appendChild(main);

    const del = document.createElement("button");
    del.className = "session-del";
    del.title = "Delete this session";
    del.textContent = "×";
    del.onclick = (e) => {
      e.stopPropagation();
      deleteSession(s.id);
    };
    item.appendChild(del);

    els.sessionList.appendChild(item);
  }
}

async function deleteSession(id) {
  if (!confirm(`Delete "${id}" entirely? The session disappears from the sidebar.`)) return;
  try {
    await fetch(`/session/${encodeURIComponent(id)}`, { method: "DELETE" });
    await loadSessions();
    if (id === currentSession) await jumpToNextSession();
  } catch (e) {
    console.warn("deleteSession failed", e);
  }
}

async function jumpToNextSession() {
  // After a true delete the page would otherwise be stuck on a session
  // that no longer has a sidebar entry. Pick the next most-recent real
  // session, or fall through to a clean empty state.
  try {
    const r = await fetch("/sessions");
    const d = await r.json();
    const sessions = (d.sessions || []).filter(s => s.id !== "default");
    if (sessions.length) {
      pinnedSession = false;  // let auto-follow take over again
      switchSession(sessions[0].id, { pin: false });
      return;
    }
  } catch (e) {
    console.warn("jumpToNextSession failed", e);
  }
  currentSession = "default";
  pinnedSession = false;
  wsHasConnectedOnce = false;
  els.feedTitle.textContent = friendlyTitle("default");
  els.messages.innerHTML = "";
  messageCache = [];
  els.feedMeta.textContent = "— no messages yet —";
  resetPasteState();
  reconnectWs();
}

function switchSession(id, opts = {}) {
  if (id === currentSession) return;
  currentSession = id;
  if (opts.pin !== false) pinnedSession = true;
  const url = new URL(location.href);
  url.searchParams.set("session", id);
  history.replaceState({}, "", url);
  els.feedTitle.textContent = friendlyTitle(id);
  // Treat the new ws as a fresh connect (not a reconnect-with-gap), so
  // its onopen doesn't redundantly call loadHistory after we already did.
  wsHasConnectedOnce = false;
  // Paste-state is per-session: aliases reference paths the *previous*
  // session uploaded under, and counter [imageN] should restart from 1
  // so the user sees a clean numbering each time.
  resetPasteState();
  loadHistory();
  loadSessions();
  reconnectWs();
}

function resetPasteState() {
  pasteCounter = 0;
  pasteAliases.clear();
  els.inputField.value = "";
}

function friendlyTitle(id) {
  // Truncate long UUID-style ids gracefully.
  if (id.length > 24) return id.slice(0, 8) + "…";
  return id;
}

async function renameCurrentSession() {
  const current = els.feedTitle.textContent;
  const next = prompt("Rename this session:", current);
  if (next == null) return;
  const trimmed = next.trim();
  if (!trimmed || trimmed === current) return;
  try {
    const r = await fetch(`/session/${encodeURIComponent(currentSession)}/label`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: trimmed }),
    });
    const data = await r.json();
    if (!data.ok) {
      alert("Rename failed: " + (data.error || "unknown error"));
      return;
    }
    els.feedTitle.textContent = trimmed;
    await loadSessions();
  } catch (e) {
    console.warn("rename failed", e);
  }
}

// ---------- history ----------

async function loadHistory() {
  els.messages.innerHTML = "";
  messageCache = [];
  try {
    const r = await fetch(`/session/${currentSession}`);
    const data = await r.json();

    // Find latest label across history.
    let latestLabel = null;
    if (data.messages) {
      for (const m of data.messages) {
        if (m.session_label) latestLabel = m.session_label;
      }
    }
    els.feedTitle.textContent = latestLabel || friendlyTitle(currentSession);

    if (!data.messages || data.messages.length === 0) {
      showEmpty();
      els.feedMeta.textContent = "— no messages yet —";
      return;
    }
    let shown = 0;
    for (const m of data.messages) {
      if (m.role === "system" || m.role === "_cleared") continue; // hide internal meta records
      appendMessage(m, false);
      shown++;
    }
    els.feedMeta.textContent = `${shown} message${shown !== 1 ? "s" : ""}`;
    requestAnimationFrame(() => scrollBottom(true));
    rebuildToc();
  } catch (e) {
    console.error("loadHistory failed", e);
  }
}

function showEmpty() {
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.innerHTML = `
    <h2>Waiting for Claude…</h2>
    <p>Once a Stop hook fires in your terminal session, the assistant reply will appear here.</p>
    <p style="margin-top:18px;font-size:14px">Session: <code>${currentSession}</code></p>
  `;
  els.messages.appendChild(empty);
}

// ---------- messages ----------

function appendMessage(msg, animate = true) {
  const empties = els.messages.querySelectorAll(".empty-state");
  empties.forEach(e => e.remove());

  messageCache.push(msg);

  const card = document.createElement("article");
  card.className = "msg msg-" + (msg.role || "assistant");
  if (animate) card.style.opacity = "0";

  const meta = document.createElement("div");
  meta.className = "msg-meta";

  const byline = document.createElement("div");
  byline.className = "msg-byline";

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar" + (msg.role === "user" ? " user" : "");
  avatar.textContent = (msg.role === "user" ? "U" : "C");

  const name = document.createElement("div");
  name.className = "msg-name";
  name.textContent = msg.role === "user" ? "You" : "Claude";

  byline.appendChild(avatar);
  byline.appendChild(name);

  const ts = document.createElement("div");
  ts.className = "msg-ts";
  ts.textContent = formatTime(msg.ts);

  const tools = document.createElement("div");
  tools.className = "msg-tools";

  const copyMd = document.createElement("button");
  copyMd.className = "tool-btn";
  copyMd.textContent = "copy md";
  copyMd.onclick = () => copyToClipboard(msg.content, copyMd);

  const copyText = document.createElement("button");
  copyText.className = "tool-btn";
  copyText.textContent = "copy text";
  copyText.onclick = () => {
    const tmp = document.createElement("div");
    tmp.innerHTML = marked.parse(msg.content);
    copyToClipboard(tmp.innerText, copyText);
  };

  tools.appendChild(copyMd);
  tools.appendChild(copyText);

  const left = document.createElement("div");
  left.style.display = "flex";
  left.style.alignItems = "center";
  left.style.gap = "12px";
  left.appendChild(byline);
  left.appendChild(ts);

  meta.appendChild(left);
  meta.appendChild(tools);

  const body = document.createElement("div");
  body.className = "md";
  renderMarkdown(body, msg.content);

  card.appendChild(meta);
  card.appendChild(body);
  els.messages.appendChild(card);

  if (animate) {
    requestAnimationFrame(() => {
      card.style.transition = "opacity 0.25s ease";
      card.style.opacity = "1";
    });
    scrollBottom();
  }

  els.feedMeta.textContent = `${messageCache.length} message${messageCache.length > 1 ? "s" : ""}`;
  rebuildToc();
}

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(typeof ts === "number" ? ts * 1000 : ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const old = btn.textContent;
    btn.textContent = "copied";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = old;
      btn.classList.remove("copied");
    }, 1200);
  });
}

function scrollBottom(force = false) {
  const m = els.messages;
  const nearBottom = m.scrollHeight - m.scrollTop - m.clientHeight < 200;
  if (force || nearBottom) {
    m.scrollTop = m.scrollHeight;
  }
}

// ---------- TOC ----------

function rebuildToc() {
  els.toc.innerHTML = "";
  const heads = els.messages.querySelectorAll(".md h2, .md h3");
  let counter = 0;
  heads.forEach(h => {
    if (!h.id) {
      h.id = "toc-" + counter++;
    }
    const a = document.createElement("a");
    a.href = "#" + h.id;
    a.textContent = h.textContent;
    if (h.tagName === "H3") a.classList.add("toc-h3");
    a.onclick = (e) => {
      e.preventDefault();
      h.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    els.toc.appendChild(a);
  });
  if (heads.length === 0) {
    const note = document.createElement("div");
    note.style.fontSize = "12px";
    note.style.color = "var(--muted-soft)";
    note.style.padding = "4px 8px";
    note.textContent = "—";
    els.toc.appendChild(note);
  }
}

// ---------- websocket ----------

function connectWs() {
  // tear down any prior ws so we never end up with two live sockets for the
  // same session (which would broadcast each message twice into this tab).
  if (ws) {
    ws.onopen = null;
    ws.onclose = null;
    ws.onerror = null;
    ws.onmessage = null;
    try { ws.close(); } catch (_) {}
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${encodeURIComponent(currentSession)}`);
  const myWs = ws;

  myWs.onopen = () => {
    if (myWs !== ws) return;
    els.wsDot.className = "dot dot-ok";
    els.wsLabel.textContent = "connected";
    if (wsHasConnectedOnce) {
      // Reconnect (server restart, network blip, sleep/wake) — replay
      // history in case any /push happened while we were disconnected.
      loadHistory();
    }
    wsHasConnectedOnce = true;
  };

  myWs.onclose = () => {
    if (myWs !== ws) return;  // a newer ws has taken over — let it drive retries
    els.wsDot.className = "dot dot-err";
    els.wsLabel.textContent = "disconnected — retrying…";
    setTimeout(connectWs, 1500);
  };

  myWs.onerror = () => {
    if (myWs !== ws) return;
    els.wsDot.className = "dot dot-err";
  };

  myWs.onmessage = (evt) => {
    if (myWs !== ws) return;  // ignore late frames from a superseded socket
    const data = JSON.parse(evt.data);
    if (data.type === "message") {
      if (data.message.role !== "system") appendMessage(data.message, true);
      if (data.message.session_label) {
        els.feedTitle.textContent = data.message.session_label;
      }
    } else if (data.type === "label_changed") {
      els.feedTitle.textContent = data.label;
      loadSessions();
    } else if (data.type === "reload") {
      // backfill (or other server-side mutation) wants the feed re-rendered.
      loadHistory();
    } else if (data.type === "ready") {
      // initial sync — server is ready
    }
  };
}

function reconnectWs() {
  // connectWs handles teardown of any prior ws.
  connectWs();
}

function connectIndexWs() {
  // Subscribe to the broadcast-only __index__ channel so we learn when a
  // brand-new Claude session pushes its first reply, and can hop to it
  // automatically. Without this, opening a new Claude conversation while
  // iris is already open leaves the page stuck on the old session.
  if (indexWs) {
    indexWs.onmessage = null;
    indexWs.onclose = null;
    try { indexWs.close(); } catch (_) {}
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  indexWs = new WebSocket(`${proto}://${location.host}/ws/__index__`);
  const myWs = indexWs;
  myWs.onmessage = (evt) => {
    if (myWs !== indexWs) return;
    let data;
    try { data = JSON.parse(evt.data); } catch (_) { return; }
    if (data.type === "session_touch") {
      const id = data.session;
      if (!id || id === "default" || id === "__index__") return;
      // Always refresh the sidebar so newly active sessions appear.
      loadSessions();
      // Auto-follow if the user hasn't pinned, OR if they're currently
      // sitting on the synthetic "default" bucket (which is never a
      // real conversation — any real session arriving should win).
      const onDefault = currentSession === "default";
      if ((!pinnedSession || onDefault) && id !== currentSession) {
        switchSession(id, { pin: false });
      }
    } else if (data.type === "session_removed") {
      // Some other tab (or curl) hard-deleted a session. Refresh sidebar;
      // jump out if we were viewing the one that just disappeared.
      loadSessions();
      if (data.session && data.session === currentSession) {
        jumpToNextSession();
      }
    }
  };
  myWs.onclose = () => {
    if (myWs !== indexWs) return;
    setTimeout(connectIndexWs, 1500);
  };
}

// ---------- input ----------

// Paste-to-upload: paste an image → upload → insert a short `[imageN]`
// alias in the input box for legibility. On Send, aliases get expanded
// back to `[image: /full/path]` so the listener (and Claude Code on the
// terminal side) still gets the resolvable path. State declared at top
// of the file alongside other module-level globals.

function expandPasteAliases(text) {
  for (const [alias, path] of pasteAliases.entries()) {
    if (text.includes(alias)) {
      text = text.split(alias).join(`[image: ${path}]`);
    }
  }
  return text;
}

els.inputField.addEventListener("paste", async (e) => {
  const items = (e.clipboardData || {}).items || [];
  let imageItem = null;
  for (const it of items) {
    if (it.type && it.type.startsWith("image/")) {
      imageItem = it;
      break;
    }
  }
  if (!imageItem) return; // let the default paste handle text
  e.preventDefault();
  const blob = imageItem.getAsFile();
  if (!blob) return;
  const ext = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg");
  const fd = new FormData();
  fd.append("file", blob, `paste.${ext}`);
  fd.append("session_id", currentSession);
  els.inputField.placeholder = "uploading image…";
  try {
    const r = await fetch("/upload-image", { method: "POST", body: fd });
    const data = await r.json();
    if (data.ok && data.path) {
      pasteCounter++;
      const alias = `[image${pasteCounter}]`;
      pasteAliases.set(alias, data.path);
      const cur = els.inputField.value;
      els.inputField.value = cur ? cur + " " + alias : alias;
      els.inputField.placeholder = "Type a message back to the terminal…";
      els.inputField.focus();
    } else {
      alert("upload failed: " + (data.error || "unknown error"));
    }
  } catch (err) {
    alert("upload failed: " + err.message);
  } finally {
    els.inputField.placeholder = "Type a message back to the terminal…";
  }
});

els.inputForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const raw = els.inputField.value.trim();
  if (!raw) return;
  els.inputField.value = "";
  // Typing into the input is an explicit engagement with this session —
  // pin so a __index__ session_touch from another concurrent Claude
  // session doesn't yank the page away mid-conversation.
  // BUT: never pin to the synthetic "default" bucket. When the user types
  // before any real Claude session has registered (sidebar shows "No
  // sessions yet"), the listener pastes into the terminal, Claude replies,
  // and Stop hook pushes to the real UUID. We *want* the page to jump
  // there — pinning to "default" would leave it stuck without the reply.
  if (currentSession !== "default") {
    pinnedSession = true;
  }
  // Expand `[imageN]` aliases back to `[image: /full/path]` before sending
  // so the listener types a path the terminal-side Claude can resolve.
  const text = expandPasteAliases(raw);
  // Server now persists + broadcasts via WebSocket, so we don't echo locally
  // (otherwise the message would appear twice).
  try {
    const r = await fetch("/input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        session_id: currentSession,
        session_label: els.feedTitle.textContent || currentSession,
      }),
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      console.warn("input not delivered:", data);
    }
  } catch (err) {
    console.warn("input failed:", err);
  }
});

// ---------- buttons ----------

els.btnClear.addEventListener("click", async () => {
  if (!confirm(`Clear all messages in "${currentSession}"?`)) return;
  await fetch(`/session/${encodeURIComponent(currentSession)}/clear`, { method: "POST" });
  loadHistory();
  loadSessions();
});

els.btnCopyAll.addEventListener("click", () => {
  const all = messageCache.map(m => `## ${m.role === "user" ? "You" : "Claude"} — ${formatTime(m.ts)}\n\n${m.content}`).join("\n\n---\n\n");
  copyToClipboard(all, els.btnCopyAll);
});

els.btnScroll.addEventListener("click", () => scrollBottom(true));

// ---------- boot ----------

els.feedTitle.textContent = friendlyTitle(currentSession);
els.feedTitle.title = "Click to rename";
els.feedTitle.style.cursor = "pointer";
els.feedTitle.addEventListener("click", renameCurrentSession);

async function pickInitialSession() {
  // If the URL pinned a session, honor it. Otherwise switch to the most
  // recently touched real session — without this, the page lands on the
  // synthetic "default" session while the Stop hook pushes replies under
  // Claude Code's actual session UUID, and the user sees nothing arrive.
  if (explicitSession) {
    loadSessions();
    loadHistory();
    connectWs();
    connectIndexWs();
    return;
  }
  try {
    const r = await fetch("/sessions");
    const d = await r.json();
    const sessions = (d.sessions || []).filter(s => s.id !== "default");
    if (sessions.length) {
      currentSession = sessions[0].id;
      els.feedTitle.textContent = sessions[0].label || friendlyTitle(currentSession);
    }
  } catch (e) {
    console.error("pickInitialSession failed", e);
  }
  loadSessions();
  loadHistory();
  connectWs();
  connectIndexWs();
}

pickInitialSession();

// refresh sessions every 10s in case other terminals push to new sessions
setInterval(loadSessions, 10000);
