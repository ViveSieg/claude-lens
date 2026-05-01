/* claude-lens frontend */

const params = new URLSearchParams(location.search);
let currentSession = params.get("session") || "default";

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
  const protectedSrc = src.replace(/```mermaid\n([\s\S]*?)```/g, (_, code) => {
    const id = mermaidBlocks.length;
    mermaidBlocks.push(code.trim());
    return `<div class="mermaid-slot" data-mid="${id}"></div>`;
  });

  container.innerHTML = marked.parse(protectedSrc);

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
  container.querySelectorAll(".mermaid-slot").forEach((slot) => {
    const idx = parseInt(slot.dataset.mid, 10);
    const code = mermaidBlocks[idx];
    const renderId = "m-" + Math.random().toString(36).slice(2, 10);
    mermaid
      .render(renderId, code)
      .then(({ svg, bindFunctions }) => {
        slot.innerHTML = svg;
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

  // "+ New scratchpad" button always at top.
  // Naming note: this creates a manual mirror bucket (for notes / render tests
  // / demos). It does NOT start a new Claude Code conversation — those appear
  // automatically when the Stop hook fires from any running `claude` process.
  const addBtn = document.createElement("button");
  addBtn.className = "session-add";
  addBtn.textContent = "＋ New scratchpad";
  addBtn.title =
    "Create a manual mirror bucket for notes, demos, or render tests.\n" +
    "Does NOT start a new Claude conversation — those auto-appear when " +
    "you run `claude` in any terminal.";
  addBtn.onclick = createSession;
  els.sessionList.appendChild(addBtn);

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

async function createSession() {
  const name = prompt(
    "Scratchpad name (letters, digits, dash, underscore).\n" +
      "This creates a manual bucket for notes / render tests, " +
      "NOT a new Claude conversation.",
    ""
  );
  if (!name) return;
  const safe = name.trim().replace(/[^A-Za-z0-9_-]/g, "-");
  if (!safe) {
    alert("Invalid scratchpad name.");
    return;
  }
  try {
    const r = await fetch("/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: safe, session_label: name.trim() }),
    });
    const data = await r.json();
    if (!data.ok) {
      alert("Could not create scratchpad: " + (data.error || "unknown error"));
      return;
    }
    await loadSessions();
    switchSession(data.session_id);
  } catch (e) {
    console.warn("createSession failed", e);
  }
}

async function deleteSession(id) {
  // (legacy name kept; works for both auto-created sessions and scratchpads)
  if (!confirm(`Delete "${id}"? This removes its history file.`)) return;
  try {
    await fetch(`/session/${encodeURIComponent(id)}`, { method: "DELETE" });
    await loadSessions();
    if (id === currentSession) switchSession("default");
  } catch (e) {
    console.warn("deleteSession failed", e);
  }
}

function switchSession(id) {
  if (id === currentSession) return;
  currentSession = id;
  const url = new URL(location.href);
  url.searchParams.set("session", id);
  history.replaceState({}, "", url);
  els.feedTitle.textContent = friendlyTitle(id);
  loadHistory();
  loadSessions();
  reconnectWs();
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
      if (m.role === "system") continue; // hide internal meta records
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
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${encodeURIComponent(currentSession)}`);

  ws.onopen = () => {
    els.wsDot.className = "dot dot-ok";
    els.wsLabel.textContent = "connected";
  };

  ws.onclose = () => {
    els.wsDot.className = "dot dot-err";
    els.wsLabel.textContent = "disconnected — retrying…";
    setTimeout(connectWs, 1500);
  };

  ws.onerror = () => {
    els.wsDot.className = "dot dot-err";
  };

  ws.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    if (data.type === "message") {
      if (data.message.role !== "system") appendMessage(data.message, true);
      if (data.message.session_label) {
        els.feedTitle.textContent = data.message.session_label;
      }
    } else if (data.type === "label_changed") {
      els.feedTitle.textContent = data.label;
      loadSessions();
    } else if (data.type === "ready") {
      // initial sync — server is ready
    }
  };
}

function reconnectWs() {
  if (ws) {
    try { ws.close(); } catch (_) {}
  }
  connectWs();
}

// ---------- input ----------

els.inputForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = els.inputField.value.trim();
  if (!text) return;
  els.inputField.value = "";
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
  await fetch(`/session/${currentSession}`, { method: "DELETE" });
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
loadSessions();
loadHistory();
connectWs();

// refresh sessions every 10s in case other terminals push to new sessions
setInterval(loadSessions, 10000);
