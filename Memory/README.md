# Memory Explorer

Visual demo of **short-term vs long-term memory** in AI agents. A chat interface backed by a local Ollama model that can `remember()` and `recall()` information across sessions.

## What it demonstrates

- **Short-term memory** — the context window (messages in the current session)
- **Long-term memory** — a persistent memory store that survives session resets
- **Semantic memories** — preferences and facts about the user
- **Episodic memories** — decisions, events, and project context
- The `remember()` / `recall()` tool-calling pattern
- What happens when context is cleared but long-term memory is preserved

## Setup

```bash
cd Memory
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Run

Requires Ollama running locally with a model pulled (default: `gemma4:latest`):

```bash
uv run python server.py
```

Open `index.html` directly in your browser. API runs on `http://localhost:8002`.

Override model or Ollama URL:

```bash
MODEL=llama3.2:latest uv run python server.py
OLLAMA_BASE_URL=http://remote-host:11434/v1 uv run python server.py
```

## Usage

1. Type a message introducing yourself or describing a project
2. Watch the agent call `remember()` to save relevant context
3. Click **New Session** to reset the conversation (context window cleared)
4. Send a new message — the agent will call `recall()` and personalize its response
5. The **Long-term Memory** panel persists across sessions; only **Clear All** removes it

## Architecture

**Backend (`server.py`)** — FastAPI app on port 8002. Two in-memory stores:
- `SESSIONS` — per-session message history (short-term context)
- `MEMORY_STORE` — global list of memories (long-term, shared across sessions)

Endpoints:
- `GET /health` — status + memory count
- `POST /chat` — takes `{session_id?, message}`, runs agent loop, returns events + updated memories
- `POST /session/reset` — clears a session's context, preserves `MEMORY_STORE`
- `GET /memories` — list all memories
- `DELETE /memories` — clear all memories
- `DELETE /memories/{id}` — delete one memory

**Frontend (`index.html` + `styles.css` + `app.js`)** — Static files opened directly in browser.
Each `remember()` and `recall()` call is visualized as an expandable event card in the chat.

> **Note:** Recall uses keyword search for simplicity. Production systems use vector embeddings for semantic similarity.
