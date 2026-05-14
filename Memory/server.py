import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
MODEL = os.getenv("MODEL", "gemma4:latest")
TIMEOUT = int(os.getenv("TIMEOUT", "120"))
MAX_ITER = 6

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared across sessions to demonstrate persistence
MEMORY_STORE: List[Dict[str, Any]] = []
SESSIONS: Dict[str, List[Dict[str, Any]]] = {}

SYSTEM_PROMPT = (
    "You are a personal productivity assistant with persistent long-term memory.\n\n"
    "Tools available:\n"
    "- remember(type, content, tags): Save important information permanently.\n"
    "  type = 'semantic' for preferences/facts, 'episodic' for decisions/events.\n"
    "- recall(query, limit): Search long-term memory before answering.\n\n"
    "Rules:\n"
    "1. At the START of every new conversation, call recall() to retrieve user context.\n"
    "2. When the user shares preferences, project details, or decisions, call remember().\n"
    "3. After saving a memory, confirm briefly: 'Saved that! 🧠'\n"
    "4. Never invent past context — only use what recall() returns.\n"
    "5. Be warm and personal. Use the user's name and project context when known."
)

REMEMBER_TOOL = {
    "type": "function",
    "function": {
        "name": "remember",
        "description": "Persist important information to long-term memory (survives session resets).",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["semantic", "episodic"],
                    "description": "semantic = preferences/facts about the user; episodic = events/decisions",
                },
                "content": {
                    "type": "string",
                    "description": "A clear sentence describing what to remember.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-4 keywords that help retrieval.",
                },
            },
            "required": ["type", "content", "tags"],
        },
    },
}

RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "recall",
        "description": "Search long-term memory for context relevant to the current conversation.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memory.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of memories to return (default: 3).",
                },
            },
            "required": ["query"],
        },
    },
}

TOOLS = [REMEMBER_TOOL, RECALL_TOOL]


def _exec_remember(type: str, content: str, tags: list) -> Dict:
    memory = {
        "id": str(uuid.uuid4())[:8],
        "type": type,
        "content": content,
        "tags": [t.lower().strip() for t in tags],
        "created_at": datetime.now().strftime("%H:%M"),
    }
    MEMORY_STORE.append(memory)
    return {"status": "stored", "memory_id": memory["id"], "type": type}


def _exec_recall(query: str, limit: int = 3) -> Dict:
    if not MEMORY_STORE:
        return {"memories": [], "note": "No memories stored yet."}
    limit = max(1, min(int(limit), 10))
    q_words = set(query.lower().split())
    scored = []
    for m in MEMORY_STORE:
        blob = (m["content"] + " " + " ".join(m["tags"])).lower()
        score = sum(1 for w in q_words if len(w) > 2 and w in blob)
        scored.append((score, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    # Return top relevant; fallback to most recent if nothing scored
    top = [m for s, m in scored if s > 0][:limit]
    if not top:
        top = [m for _, m in scored[:limit]]
    return {"memories": top, "count": len(top)}


def _call_ollama(messages: List[Dict]) -> Dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }
    resp = requests.post(
        f"{OLLAMA_BASE}/chat/completions",
        json=payload,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_tool_args(raw_args: Any) -> Dict:
    if isinstance(raw_args, dict):
        return raw_args
    try:
        return json.loads(raw_args or "{}")
    except Exception:
        return {}


def _approx_tokens(messages: List[Dict]) -> int:
    total = sum(len(str(m.get("content", ""))) for m in messages)
    return total // 4


class ChatRequest(BaseModel):
    session_id: str = ""
    message: str


class ResetRequest(BaseModel):
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "memory_count": len(MEMORY_STORE)}


@app.post("/chat")
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())[:8]
    if session_id not in SESSIONS:
        SESSIONS[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages = SESSIONS[session_id]
    messages.append({"role": "user", "content": req.message})

    events: List[Dict[str, Any]] = []

    for _ in range(MAX_ITER):
        data = _call_ollama(messages)
        raw_msg = data["choices"][0]["message"]
        raw_tool_calls = raw_msg.get("tool_calls") or []
        content = str(raw_msg.get("content") or "")

        reasoning = (
            raw_msg.get("reasoning")
            or raw_msg.get("reasoning_content")
            or raw_msg.get("thinking")
            or ""
        )
        if reasoning:
            events.append({"type": "thinking", "content": str(reasoning)})

        if not raw_tool_calls:
            events.append({"type": "response", "content": content})
            messages.append({"role": "assistant", "content": content})
            break

        if content.strip():
            events.append({"type": "plan", "content": content.strip()})

        messages.append(raw_msg)

        tool_results = []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            name = str(fn.get("name", ""))
            args = _parse_tool_args(fn.get("arguments"))

            events.append({"type": "tool_call", "tool": name, "args": args})

            if name == "remember":
                result = _exec_remember(**{k: args[k] for k in ("type", "content", "tags") if k in args})
            elif name == "recall":
                result = _exec_recall(
                    query=args.get("query", ""),
                    limit=args.get("limit", 3),
                )
            else:
                result = {"error": f"Unknown tool: {name}"}

            events.append({"type": "tool_result", "tool": name, "result": result})

            tool_results.append({
                "tool_call_id": str(tc.get("id", "")),
                "role": "tool",
                "name": name,
                "content": json.dumps(result, ensure_ascii=True),
            })

        messages.extend(tool_results)

    context_info = {
        "message_count": len([m for m in messages if m["role"] not in ("system",)]),
        "estimated_tokens": _approx_tokens(messages),
        "memory_count": len(MEMORY_STORE),
    }

    return {
        "session_id": session_id,
        "events": events,
        "context_info": context_info,
        "memories": MEMORY_STORE,
    }


@app.post("/session/reset")
def reset_session(req: ResetRequest):
    SESSIONS[req.session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return {"ok": True}


@app.get("/memories")
def get_memories():
    return {"memories": MEMORY_STORE, "count": len(MEMORY_STORE)}


@app.delete("/memories")
def clear_all_memories():
    MEMORY_STORE.clear()
    return {"ok": True}


@app.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    global MEMORY_STORE
    before = len(MEMORY_STORE)
    MEMORY_STORE = [m for m in MEMORY_STORE if m["id"] != memory_id]
    if len(MEMORY_STORE) == before:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
