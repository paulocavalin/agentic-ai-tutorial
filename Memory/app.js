const API = "http://localhost:8002";

let sessionId = "";
let isLoading = false;

const messagesEl = document.getElementById("messages");
const emptyChatEl = document.getElementById("emptyChat");
const memoryEl = document.getElementById("memories");
const emptyMemEl = document.getElementById("emptyMem");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const newSessionBtn = document.getElementById("newSessionBtn");
const clearMemBtn = document.getElementById("clearMemBtn");
const sessionIdEl = document.getElementById("sessionId");
const contextStatsEl = document.getElementById("contextStats");
const memoryCountEl = document.getElementById("memoryCount");
const modelNameEl = document.getElementById("modelName");

// ── Bootstrap ──────────────────────────────────────────────────────────────

async function init() {
  try {
    const res = await fetch(`${API}/health`);
    const data = await res.json();
    modelNameEl.textContent = data.model.split(":")[0];
  } catch {
    modelNameEl.textContent = "unreachable";
  }
  await loadMemories();
}

async function loadMemories() {
  try {
    const res = await fetch(`${API}/memories`);
    const data = await res.json();
    renderMemories(data.memories || []);
  } catch {
    /* silently ignore */
  }
}

// ── Sending a message ───────────────────────────────────────────────────────

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || isLoading) return;

  chatInput.value = "";
  isLoading = true;
  sendBtn.disabled = true;
  emptyChatEl.style.display = "none";

  appendUserBubble(text);
  const spinner = appendSpinner();

  try {
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    });

    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    sessionId = data.session_id;
    sessionIdEl.textContent = sessionId;

    spinner.remove();
    await animateEvents(data.events || []);

    updateContextStats(data.context_info || {});
    renderMemories(data.memories || []);
  } catch (err) {
    spinner.remove();
    appendErrorBubble(err.message || "Request failed");
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
  }
}

// ── Event animation ─────────────────────────────────────────────────────────

async function animateEvents(events) {
  for (const ev of events) {
    appendEvent(ev);
    await delay(300);
    scrollToBottom();
  }
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function appendEvent(ev) {
  if (ev.type === "response") {
    appendAssistantBubble(ev.content);
    return;
  }

  const card = document.createElement("div");
  let cls = "event ";
  let icon = "•";
  let label = "";
  let subtitle = "";
  let body = "";

  if (ev.type === "thinking") {
    cls += "thinking";
    icon = "🤔";
    label = "THINKING";
    subtitle = ev.content.slice(0, 60) + (ev.content.length > 60 ? "…" : "");
    body = ev.content;
  } else if (ev.type === "plan") {
    cls += "plan";
    icon = "📋";
    label = "PLANNING";
    subtitle = ev.content.slice(0, 60) + (ev.content.length > 60 ? "…" : "");
    body = ev.content;
  } else if (ev.type === "tool_call") {
    const isRemember = ev.tool === "remember";
    cls += isRemember ? "tool-call-remember" : "tool-call-recall";
    icon = isRemember ? "🧠" : "🔍";
    label = `TOOL CALL · ${ev.tool}()`;
    subtitle = isRemember
      ? `[${ev.args.type}] ${(ev.args.content || "").slice(0, 50)}…`
      : `"${ev.args.query || ""}"`;
    body = JSON.stringify(ev.args, null, 2);
  } else if (ev.type === "tool_result") {
    const isRemember = ev.tool === "remember";
    cls += isRemember ? "tool-result-remember" : "tool-result-recall";
    icon = isRemember ? "✅" : "📂";
    label = `RESULT · ${ev.tool}()`;
    const r = ev.result || {};
    if (isRemember) {
      subtitle = `stored as ${r.memory_id} (${r.type})`;
    } else {
      const count = (r.memories || []).length;
      subtitle = count > 0 ? `${count} memor${count === 1 ? "y" : "ies"} found` : "no memories found";
    }
    body = JSON.stringify(ev.result, null, 2);
  }

  card.className = cls;
  card.innerHTML = `
    <div class="event-header" onclick="toggleEvent(this)">
      <span class="event-icon">${icon}</span>
      <span class="event-label">${label}</span>
      <span class="event-subtitle">${escapeHtml(subtitle)}</span>
      <span class="event-toggle">▾</span>
    </div>
    <div class="event-body"><pre>${escapeHtml(body)}</pre></div>
  `;

  messagesEl.appendChild(card);
}

function toggleEvent(header) {
  const body = header.nextElementSibling;
  const toggle = header.querySelector(".event-toggle");
  body.classList.toggle("open");
  toggle.textContent = body.classList.contains("open") ? "▴" : "▾";
}

// ── Bubble helpers ──────────────────────────────────────────────────────────

function appendUserBubble(text) {
  const el = document.createElement("div");
  el.className = "msg user";
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollToBottom();
}

function appendAssistantBubble(text) {
  const el = document.createElement("div");
  el.className = "msg response";
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollToBottom();
}

function appendErrorBubble(msg) {
  const el = document.createElement("div");
  el.className = "msg response";
  el.style.borderColor = "#fca5a5";
  el.style.background = "#fef2f2";
  el.textContent = `⚠️ ${msg}`;
  messagesEl.appendChild(el);
  scrollToBottom();
}

function appendSpinner() {
  const el = document.createElement("div");
  el.className = "spinner";
  el.innerHTML = `<span>🧠 Agent thinking</span><span class="dot-anim"></span>`;
  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── Memory panel ────────────────────────────────────────────────────────────

function renderMemories(memories) {
  memoryCountEl.textContent = `${memories.length} memor${memories.length === 1 ? "y" : "ies"}`;

  if (!memories.length) {
    memoryEl.innerHTML = "";
    memoryEl.appendChild(emptyMemEl);
    emptyMemEl.style.display = "block";
    return;
  }

  emptyMemEl.style.display = "none";

  // Keep existing cards, only add/remove as needed
  const existing = new Set([...memoryEl.querySelectorAll(".memory-card")].map(el => el.dataset.id));
  const incoming = new Set(memories.map(m => m.id));

  // Remove deleted
  memoryEl.querySelectorAll(".memory-card").forEach(el => {
    if (!incoming.has(el.dataset.id)) el.remove();
  });

  // Add new (prepend so newest is top)
  const newMems = memories.filter(m => !existing.has(m.id));
  newMems.forEach(m => {
    const card = buildMemoryCard(m);
    memoryEl.insertBefore(card, memoryEl.firstChild);
  });
}

function buildMemoryCard(m) {
  const card = document.createElement("div");
  card.className = `memory-card ${m.type}`;
  card.dataset.id = m.id;

  const tags = (m.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("");

  card.innerHTML = `
    <div class="memory-card-top">
      <span class="memory-type">${m.type}</span>
      <span class="memory-time">${m.created_at || ""}</span>
      <button class="memory-delete" onclick="deleteMemory('${m.id}')" title="Delete">✕</button>
    </div>
    <div class="memory-content">${escapeHtml(m.content)}</div>
    <div class="memory-tags">${tags}</div>
  `;

  return card;
}

async function deleteMemory(id) {
  try {
    await fetch(`${API}/memories/${id}`, { method: "DELETE" });
    await loadMemories();
  } catch {
    /* ignore */
  }
}

// ── Session & memory controls ───────────────────────────────────────────────

async function newSession() {
  if (!sessionId) return;
  if (!confirm("Clear the conversation context? Long-term memories are preserved.")) return;

  await fetch(`${API}/session/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });

  // Clear chat UI, keep memory panel
  messagesEl.innerHTML = "";
  messagesEl.appendChild(emptyChatEl);
  emptyChatEl.style.display = "block";
  updateContextStats({});

  // Visual cue: flash the memory panel
  document.querySelector(".memory-panel").style.outline = "2px solid var(--accent)";
  setTimeout(() => {
    document.querySelector(".memory-panel").style.outline = "";
  }, 800);

  appendSystemNote("🔄 New session started — context window cleared. Long-term memories preserved.");
}

function appendSystemNote(text) {
  emptyChatEl.style.display = "none";
  const el = document.createElement("div");
  el.style.cssText = "text-align:center;font-size:12px;font-family:var(--mono);color:#888;padding:8px;border-radius:8px;background:#f3f4f6;animation:fadeIn 0.3s ease;";
  el.textContent = text;
  messagesEl.appendChild(el);
  scrollToBottom();
}

async function clearAllMemories() {
  if (!confirm("Clear all long-term memories? This cannot be undone.")) return;
  await fetch(`${API}/memories`, { method: "DELETE" });
  await loadMemories();
}

// ── Context stats ───────────────────────────────────────────────────────────

function updateContextStats(info) {
  const msgs = info.message_count || 0;
  const toks = info.estimated_tokens || 0;
  contextStatsEl.textContent = `${msgs} msg${msgs !== 1 ? "s" : ""} · ~${toks} tokens`;
}

// ── Utilities ───────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Event listeners ─────────────────────────────────────────────────────────

sendBtn.addEventListener("click", sendMessage);

chatInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

newSessionBtn.addEventListener("click", newSession);
clearMemBtn.addEventListener("click", clearAllMemories);

// ── Start ───────────────────────────────────────────────────────────────────

init();
