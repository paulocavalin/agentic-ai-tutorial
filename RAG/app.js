const API = "http://localhost:8003";

let allChunks = [];
let isLoading = false;

// ── DOM refs ────────────────────────────────────────────────────────────────

const modelNameEl   = document.getElementById("modelName");
const embedNameEl   = document.getElementById("embedName");
const statusDotEl   = document.getElementById("statusDot");
const statusTextEl  = document.getElementById("statusText");
const indexMetaEl   = document.getElementById("indexMeta");
const chunksGridEl  = document.getElementById("chunksGrid");
const reindexBtn    = document.getElementById("reindexBtn");
const queryInput    = document.getElementById("queryInput");
const askBtn        = document.getElementById("askBtn");
const ragToggle     = document.getElementById("ragToggle");
const pipelineEl    = document.getElementById("pipeline");
const noRagEl       = document.getElementById("noRagResult");
const noRagBodyEl   = document.getElementById("noRagBody");

// Step elements
const steps = {
  embed:    { card: document.getElementById("stepEmbed"),    status: document.getElementById("embedStatus"),    body: document.getElementById("embedBody") },
  retrieve: { card: document.getElementById("stepRetrieve"), status: document.getElementById("retrieveStatus"), body: document.getElementById("retrieveBody") },
  prompt:   { card: document.getElementById("stepPrompt"),   status: document.getElementById("promptStatus"),   body: document.getElementById("promptBody") },
  response: { card: document.getElementById("stepResponse"), status: document.getElementById("responseStatus"), body: document.getElementById("responseBody") },
};

// ── Bootstrap ──────────────────────────────────────────────────────────────

async function init() {
  setStatus("loading", "Connecting…");
  try {
    const res = await fetch(`${API}/health`);
    const data = await res.json();
    modelNameEl.textContent = (data.chat_model || "?").split(":")[0];
    embedNameEl.textContent = (data.embed_model || "?").split(":")[0];

    if (data.ready) {
      setStatus("ok", `Ready · ${data.indexed_chunks} chunks indexed`);
      await loadChunks();
    } else {
      setStatus("loading", "Indexing…");
      await triggerIndex();
    }
  } catch {
    setStatus("error", "Cannot reach server (is it running on :8003?)");
  }
}

function setStatus(state, text) {
  statusDotEl.className = `status-dot ${state}`;
  statusTextEl.textContent = text;
}

async function loadChunks() {
  const res = await fetch(`${API}/chunks`);
  const data = await res.json();
  allChunks = data.chunks || [];
  indexMetaEl.textContent = `${allChunks.length} chunks · ${countDocs(allChunks)} documents`;
  renderChunks(allChunks, []);
}

function countDocs(chunks) {
  return new Set(chunks.map(c => c.source)).size;
}

async function triggerIndex() {
  reindexBtn.disabled = true;
  setStatus("loading", "Indexing knowledge base…");
  try {
    await fetch(`${API}/index`, { method: "POST" });
    setStatus("ok", "Index ready");
    await loadChunks();
  } catch {
    setStatus("error", "Indexing failed");
  } finally {
    reindexBtn.disabled = false;
  }
}

// ── Chunk grid ──────────────────────────────────────────────────────────────

function renderChunks(chunks, highlightIds) {
  chunksGridEl.innerHTML = "";
  const highlightSet = new Set(highlightIds.map((h, i) => ({ id: h, rank: i + 1 })).map(x => x.id));
  const rankMap = {};
  highlightIds.forEach((id, i) => { rankMap[id] = i + 1; });

  chunks.forEach(c => {
    const pill = document.createElement("div");
    const rank = rankMap[c.id];
    pill.className = "chunk-pill" + (rank ? ` highlighted rank-${rank}` : "");
    pill.title = c.text;
    pill.innerHTML = `<span class="pill-src">${escapeHtml(abbrev(c.source, 20))}</span><span class="pill-page">${escapeHtml(c.page)}</span>`;
    chunksGridEl.appendChild(pill);
  });
}

function abbrev(str, max) {
  return str.length > max ? str.slice(0, max - 1) + "…" : str;
}

// ── Query ───────────────────────────────────────────────────────────────────

async function runQuery() {
  const question = queryInput.value.trim();
  if (!question || isLoading) return;

  isLoading = true;
  askBtn.disabled = true;
  askBtn.textContent = "…";

  const withRag = ragToggle.checked;

  // Reset UI
  pipelineEl.classList.add("hidden");
  noRagEl.classList.add("hidden");
  Object.values(steps).forEach(s => {
    s.card.classList.remove("visible", "active");
    s.status.textContent = "";
    s.status.className = "step-status";
    s.body.innerHTML = "";
  });
  renderChunks(allChunks, []);

  try {
    const res = await fetch(`${API}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: 3, with_rag: withRag }),
    });

    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    if (!withRag) {
      const noRagEvent = data.events.find(e => e.type === "response_no_rag");
      noRagBodyEl.textContent = noRagEvent?.content || data.answer || "";
      noRagEl.classList.remove("hidden");
    } else {
      pipelineEl.classList.remove("hidden");
      await animateEvents(data.events, data.chunks || []);
    }
  } catch (err) {
    alert("Query failed: " + (err.message || err));
  } finally {
    isLoading = false;
    askBtn.disabled = false;
    askBtn.textContent = "Ask";
  }
}

// ── Pipeline animation ──────────────────────────────────────────────────────

async function animateEvents(events, chunks) {
  for (const ev of events) {
    await delay(250);

    if (ev.type === "query_embedded") {
      await showStep("embed", ev, chunks);
    } else if (ev.type === "retrieved") {
      await showStep("retrieve", ev, chunks);
      // Highlight retrieved chunks in the knowledge base grid
      renderChunks(allChunks, (ev.chunks || []).map(c => c.id));
    } else if (ev.type === "prompt_built") {
      await showStep("prompt", ev, chunks);
    } else if (ev.type === "response") {
      await showStep("response", ev, chunks);
    }
  }
}

async function showStep(key, ev, allRetrieved) {
  const s = steps[key];
  s.card.classList.add("visible", "active");
  s.status.textContent = "processing…";
  s.status.className = "step-status loading";

  await delay(400);

  if (key === "embed") {
    s.body.innerHTML = buildEmbedBody(ev);
  } else if (key === "retrieve") {
    s.body.innerHTML = buildRetrieveBody(ev);
  } else if (key === "prompt") {
    s.body.innerHTML = buildPromptBody(ev);
  } else if (key === "response") {
    s.body.innerHTML = buildResponseBody(ev);
  }

  s.status.textContent = "✓ done";
  s.status.className = "step-status done";
  s.card.classList.remove("active");
}

function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ── Step body builders ──────────────────────────────────────────────────────

function buildEmbedBody(ev) {
  const preview = generateFakeVectorPreview();
  return `
    <div class="embed-info">
      <div><strong>Model:</strong> ${escapeHtml(ev.embed_model)}</div>
      <div><strong>Dimensions:</strong> ${ev.vector_dim}</div>
      <div><strong>Input:</strong> "${escapeHtml(ev.question.slice(0, 60))}${ev.question.length > 60 ? "…" : ""}"</div>
    </div>
    <div class="vector-preview">
      query vector → [${preview}] (${ev.vector_dim}d)
    </div>
  `;
}

function generateFakeVectorPreview() {
  const vals = Array.from({ length: 8 }, () => (Math.random() * 2 - 1).toFixed(3));
  return vals.join(", ") + ", …";
}

function buildRetrieveBody(ev) {
  const chunks = ev.chunks || [];
  const threshold = ev.threshold || 0.55;

  const items = chunks.map((c, i) => {
    const score = c.score;
    const scoreClass = score >= 0.75 ? "high" : score >= threshold ? "mid" : "low";
    const isLow = !c.relevant;
    return `
      <div class="retrieval-item rank-${i + 1}${isLow ? " low-score" : ""}">
        <div class="retrieval-item-header">
          <span class="rank-badge">${i + 1}</span>
          <span class="retrieval-src">${escapeHtml(c.source)} · ${escapeHtml(c.page)}</span>
          <div class="score-bar-wrap">
            <div class="score-bar"><div class="score-fill ${scoreClass}" style="width:${Math.round(score * 100)}%"></div></div>
            <span class="score-val ${scoreClass}">${score.toFixed(2)}</span>
          </div>
          ${isLow ? `<span class="low-score-warn">⚠ below threshold (${threshold})</span>` : ""}
        </div>
        <div class="retrieval-text">${escapeHtml(c.text)}</div>
      </div>
    `;
  }).join("");

  return `<div class="retrieval-list">${items}</div>`;
}

function buildPromptBody(ev) {
  return `
    <div class="prompt-meta">${ev.chunk_count} chunk${ev.chunk_count !== 1 ? "s" : ""} injected into context</div>
    <div class="prompt-preview">${escapeHtml(ev.preview)}</div>
  `;
}

function buildResponseBody(ev) {
  return `<div class="response-text">${escapeHtml(ev.content)}</div>`;
}

// ── Suggestions ─────────────────────────────────────────────────────────────

document.querySelectorAll(".suggestion").forEach(btn => {
  btn.addEventListener("click", () => {
    queryInput.value = btn.dataset.q;
    runQuery();
  });
});

// ── Event listeners ─────────────────────────────────────────────────────────

askBtn.addEventListener("click", runQuery);
reindexBtn.addEventListener("click", triggerIndex);

queryInput.addEventListener("keydown", e => {
  if (e.key === "Enter") runQuery();
});

ragToggle.addEventListener("change", () => {
  // Show/hide step cards label based on toggle state
  const label = document.querySelector(".toggle-label span:last-child");
  label.textContent = ragToggle.checked ? "RAG enabled" : "RAG disabled (baseline)";
});

// ── Utilities ───────────────────────────────────────────────────────────────

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Start ───────────────────────────────────────────────────────────────────

init();
