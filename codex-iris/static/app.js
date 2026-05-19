const state = {
  activeKey: "",
  sessions: [],
  timer: null,
};

const els = {
  health: document.getElementById("health"),
  sessions: document.getElementById("sessions"),
  messages: document.getElementById("messages"),
  title: document.getElementById("sessionTitle"),
  meta: document.getElementById("sessionMeta"),
  showTools: document.getElementById("showTools"),
  autoRefresh: document.getElementById("autoRefresh"),
  refreshButton: document.getElementById("refreshButton"),
  refreshSessions: document.getElementById("refreshSessions"),
  latestButton: document.getElementById("latestButton"),
};

function fmtTime(seconds) {
  if (!seconds) return "";
  return new Date(seconds * 1000).toLocaleString();
}

function text(value) {
  return value == null ? "" : String(value);
}

function shortPath(file) {
  const parts = text(file).split(/[\\/]/);
  return parts.slice(-4).join("/");
}

function nearBottom() {
  const el = els.messages;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 120;
}

function setHash(key) {
  if (!key) return;
  history.replaceState(null, "", `#${encodeURIComponent(key)}`);
}

function keyFromHash() {
  return decodeURIComponent(location.hash.replace(/^#/, ""));
}

async function getJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function loadHealth() {
  try {
    const data = await getJson("/api/health");
    els.health.textContent = data.sessions_root_exists ? "Reading local Codex sessions" : "No Codex sessions folder";
  } catch (err) {
    els.health.textContent = `Server unavailable: ${err.message}`;
  }
}

async function loadSessions() {
  const data = await getJson("/api/sessions");
  state.sessions = data.sessions || [];
  const hashKey = keyFromHash();
  if (!state.activeKey && hashKey) state.activeKey = hashKey;
  if (!state.activeKey && state.sessions[0]) state.activeKey = state.sessions[0].key;
  renderSessions();
}

function renderSessions() {
  if (!state.sessions.length) {
    els.sessions.innerHTML = `<div class="empty">No sessions found</div>`;
    return;
  }
  els.sessions.innerHTML = "";
  for (const item of state.sessions) {
    const button = document.createElement("button");
    button.className = `session-item${item.key === state.activeKey ? " active" : ""}`;
    const label = document.createElement("div");
    label.className = "session-label";
    label.textContent = item.label || item.key;
    const sub = document.createElement("div");
    sub.className = "session-sub";
    sub.textContent = `${fmtTime(item.mtime)}  ${item.message_count} events`;
    button.append(label, sub);
    button.addEventListener("click", () => {
      state.activeKey = item.key;
      setHash(item.key);
      renderSessions();
      loadActiveSession();
    });
    els.sessions.appendChild(button);
  }
}

async function loadActiveSession() {
  if (!state.activeKey) {
    els.messages.innerHTML = `<div class="empty">No session selected</div>`;
    return;
  }
  const keepBottom = nearBottom();
  const data = await getJson(`/api/session?key=${encodeURIComponent(state.activeKey)}`);
  const session = data.session;
  setHash(session.key);
  renderSession(session);
  if (keepBottom) els.messages.scrollTop = els.messages.scrollHeight;
}

function renderSession(session) {
  const cwd = session.meta && session.meta.cwd ? session.meta.cwd : "";
  els.title.textContent = session.label || session.key;
  els.meta.textContent = [shortPath(session.file), cwd].filter(Boolean).join("  |  ");

  const showTools = els.showTools.checked;
  const messages = (session.messages || []).filter((msg) => {
    if (showTools) return true;
    return msg.role === "user" || msg.role === "assistant";
  });

  if (!messages.length) {
    els.messages.innerHTML = `<div class="empty">No visible messages in this session</div>`;
    return;
  }

  els.messages.innerHTML = "";
  for (const msg of messages) {
    const article = document.createElement("article");
    article.className = `message ${msg.role}`;

    const header = document.createElement("div");
    header.className = "message-header";

    const role = document.createElement("div");
    role.className = `role ${msg.role}`;
    role.textContent = [msg.role, msg.phase, msg.kind !== "message" ? msg.kind : ""].filter(Boolean).join(" / ");

    const stamp = document.createElement("div");
    stamp.className = "stamp";
    stamp.textContent = fmtTime(msg.ts);

    const body = document.createElement("pre");
    body.className = `content ${msg.role === "user" || msg.role === "assistant" ? "dialogue" : ""}`;
    body.textContent = text(msg.content);

    header.append(role, stamp);
    article.append(header, body);
    els.messages.appendChild(article);
  }
}

async function refreshAll() {
  try {
    await loadHealth();
    await loadSessions();
    await loadActiveSession();
  } catch (err) {
    els.health.textContent = `Refresh failed: ${err.message}`;
  }
}

function setLiveTimer() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  if (els.autoRefresh.checked) {
    state.timer = setInterval(refreshAll, 1500);
  }
}

els.refreshButton.addEventListener("click", loadActiveSession);
els.refreshSessions.addEventListener("click", refreshAll);
els.latestButton.addEventListener("click", async () => {
  await loadSessions();
  if (state.sessions[0]) {
    state.activeKey = state.sessions[0].key;
    setHash(state.activeKey);
    renderSessions();
    await loadActiveSession();
  }
});
els.showTools.addEventListener("change", loadActiveSession);
els.autoRefresh.addEventListener("change", setLiveTimer);

refreshAll();
setLiveTimer();
