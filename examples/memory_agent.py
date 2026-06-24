"""
memory_agent.py — Two-agent comparison: naive vs. memory-managed conversation.

Demonstrates the difference between:
  - Naive agent:   keeps full conversation history in context (unbounded growth).
  - Managed agent: rolls conversation into a running summary and stores key
                   facts in a local JSON file (stays compact regardless of length).

Key concepts:
  - Context window management and compression
  - Rolling summaries via LLM
  - Long-term memory via key-value store
  - Side-by-side comparison showing context growth

Usage:
    python examples/memory_agent.py                          # 8-turn comparison
    python examples/memory_agent.py --turns 15 --mode compare
    python examples/memory_agent.py --mode interactive-managed
    python examples/memory_agent.py --mode naive
"""

import argparse
import json
import os
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ── Config ────────────────────────────────────────────────────────────────────

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_MODEL = "gemma4:12b"
SUMMARY_THRESHOLD = 6   # summarise after this many messages in context
SUMMARY_KEEP      = 2   # keep last N full messages after summarising

SESSIONS_DIR = Path.home() / ".ollama_memory_sessions"

# ── Demo conversation script ─────────────────────────────────────────────────
# Used by --compare mode to feed the same prompts to both agents.

DEMO_TURNS = [
    "Hi! My name is Paulo and I work as an AI engineer in São Paulo.",
    "I'm building a course about Generative AI. What topics do you think are most important?",
    "Good suggestions. My students are mostly developers, not researchers.",
    "Actually a few are technical product managers too. Does that change your suggestions?",
    "What was the first thing I told you about myself?",   # memory test
    "What kind of audience did I say I'm teaching?",       # memory test
    "Can you give me a 3-bullet summary of our conversation so far?",
    "Based on everything I've told you, what's the best first demo project for my course?",
    "I forgot — what city did I say I work in?",           # memory test
    "And what's my job title?",                            # memory test
]

# ── LLM call ─────────────────────────────────────────────────────────────────

def _chat(messages: List[Dict], model: str, timeout: int = 120) -> str:
    payload = {"model": model, "messages": messages, "stream": False}
    resp = requests.post(f"{OLLAMA_BASE}/chat/completions", json=payload, timeout=timeout)
    resp.raise_for_status()
    return str(resp.json()["choices"][0]["message"].get("content", ""))

# ── Naive agent ───────────────────────────────────────────────────────────────

NAIVE_SYSTEM = (
    "You are a helpful assistant. "
    "Answer questions clearly and concisely."
)

@dataclass
class NaiveAgent:
    model: str
    history: List[Dict] = field(default_factory=list)

    def chat(self, user_input: str) -> str:
        self.history.append({"role": "user", "content": user_input})
        messages = [{"role": "system", "content": NAIVE_SYSTEM}] + self.history
        response = _chat(messages, self.model)
        self.history.append({"role": "assistant", "content": response})
        return response

    @property
    def context_messages(self) -> int:
        return len(self.history)

    @property
    def context_chars(self) -> int:
        return sum(len(m["content"]) for m in self.history)

# ── Managed agent ─────────────────────────────────────────────────────────────

MANAGED_SYSTEM = (
    "You are a helpful assistant with access to memory tools.\n\n"
    "You have three tools:\n"
    "  remember(key, value) — store a fact for long-term recall\n"
    "  recall(key)          — retrieve a stored fact\n"
    "  forget(key)          — delete a stored fact\n\n"
    "Use remember() proactively to store any user-specific facts "
    "(name, job, preferences, context) that might be useful later.\n"
    "At the start of each turn, briefly recall relevant stored facts.\n"
    "Answer questions clearly and concisely."
)

SUMMARISE_SYSTEM = (
    "You are a conversation summariser. "
    "Create a concise but complete summary of the conversation below. "
    "Preserve all factual details about the user (name, job, goals, preferences). "
    "Output only the summary text, no preamble."
)

def _extract_memories(text: str) -> List[Dict[str, str]]:
    """Parse remember(key, value) calls from assistant response."""
    import re
    hits = re.findall(r'remember\(\s*["\']?([^"\'(),]+)["\']?\s*,\s*["\']?([^"\'()]+)["\']?\s*\)', text)
    return [{"key": k.strip(), "value": v.strip()} for k, v in hits]


@dataclass
class ManagedAgent:
    model: str
    session_name: str = "default"
    summary: str = ""
    recent: List[Dict] = field(default_factory=list)   # last N full messages
    memory_store: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._path = SESSIONS_DIR / f"{self.session_name}.json"
        if self._path.exists():
            self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        data = {
            "summary":      self.summary,
            "recent":       self.recent,
            "memory_store": self.memory_store,
        }
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _load(self) -> None:
        data = json.loads(self._path.read_text())
        self.summary      = data.get("summary", "")
        self.recent       = data.get("recent", [])
        self.memory_store = data.get("memory_store", {})

    # ── Memory tools ─────────────────────────────────────────────────────────

    def remember(self, key: str, value: str) -> None:
        self.memory_store[key.lower().strip()] = value.strip()

    def recall(self, key: str) -> Optional[str]:
        return self.memory_store.get(key.lower().strip())

    def forget(self, key: str) -> None:
        self.memory_store.pop(key.lower().strip(), None)

    # ── Summarisation ────────────────────────────────────────────────────────

    def _maybe_summarise(self) -> None:
        """Compress recent history into the rolling summary when it grows too long."""
        if len(self.recent) < SUMMARY_THRESHOLD:
            return
        to_compress = self.recent[:-SUMMARY_KEEP]
        keep = self.recent[-SUMMARY_KEEP:]

        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in to_compress
        )
        prefix = f"Existing summary:\n{self.summary}\n\n" if self.summary else ""
        raw = _chat(
            [{"role": "user", "content": f"{prefix}New conversation to summarise:\n{history_text}"}],
            self.model,
        )
        # Use SUMMARISE_SYSTEM as a system message
        self.summary = _chat(
            [
                {"role": "system", "content": SUMMARISE_SYSTEM},
                {"role": "user",   "content": f"{prefix}New conversation:\n{history_text}"},
            ],
            self.model,
        )
        self.recent = keep

    # ── Chat ─────────────────────────────────────────────────────────────────

    def chat(self, user_input: str) -> str:
        # Build context: system + optional summary + memory snapshot + recent + current
        memory_block = ""
        if self.memory_store:
            items = "\n".join(f"  {k}: {v}" for k, v in self.memory_store.items())
            memory_block = f"\n\n[Long-term memory]\n{items}"

        system_content = MANAGED_SYSTEM + memory_block
        if self.summary:
            system_content += f"\n\n[Conversation summary so far]\n{self.summary}"

        messages = [{"role": "system", "content": system_content}]
        messages += self.recent
        messages.append({"role": "user", "content": user_input})

        response = _chat(messages, self.model)

        # Extract any remember() calls the agent made
        for mem in _extract_memories(response):
            self.remember(mem["key"], mem["value"])

        # Update recent history
        self.recent.append({"role": "user",      "content": user_input})
        self.recent.append({"role": "assistant", "content": response})

        # Summarise if needed
        self._maybe_summarise()
        self._save()

        return response

    @property
    def context_messages(self) -> int:
        return len(self.recent) + (1 if self.summary else 0)

    @property
    def context_chars(self) -> int:
        recent_chars  = sum(len(m["content"]) for m in self.recent)
        summary_chars = len(self.summary)
        memory_chars  = sum(len(k) + len(v) for k, v in self.memory_store.items())
        return recent_chars + summary_chars + memory_chars

# ── Display helpers ───────────────────────────────────────────────────────────

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text
    _con = Console()

    def _header(text: str, style: str = "bold white") -> None:
        _con.print(f"\n[{style}]{text}[/{style}]")

    def _panel(title: str, body: str, style: str = "white") -> None:
        _con.print(Panel(body[:2000], title=title, border_style=style, expand=True))

    def _info(text: str) -> None:
        _con.print(f"[dim]{text}[/dim]")

    def _compare_responses(turn: int, prompt: str, naive_r: str, managed_r: str,
                           naive_ctx: int, managed_ctx: int) -> None:
        _con.print(f"\n[bold orange1]Turn {turn}[/bold orange1]  [dim]{prompt[:80]}[/dim]")
        _con.print(Panel(
            naive_r[:600] + ("…" if len(naive_r) > 600 else ""),
            title=f"[red]NAIVE (context: {naive_ctx} msgs)[/red]",
            border_style="red",
            expand=True,
        ))
        _con.print(Panel(
            managed_r[:600] + ("…" if len(managed_r) > 600 else ""),
            title=f"[green]MANAGED (context: {managed_ctx} msgs)[/green]",
            border_style="green",
            expand=True,
        ))

except ImportError:
    _con = None

    def _header(text: str, **_) -> None:
        print(f"\n{'─'*60}\n{text}\n{'─'*60}")

    def _panel(title: str, body: str, **_) -> None:
        print(f"\n[{title}]\n{body[:2000]}")

    def _info(text: str) -> None:
        print(text)

    def _compare_responses(turn, prompt, naive_r, managed_r, naive_ctx, managed_ctx) -> None:
        print(f"\nTurn {turn}: {prompt[:80]}")
        print(f"  NAIVE   (ctx:{naive_ctx}): {naive_r[:300]}")
        print(f"  MANAGED (ctx:{managed_ctx}): {managed_r[:300]}")

# ── Modes ─────────────────────────────────────────────────────────────────────

def run_compare(model: str, turns: int) -> None:
    """Run both agents through the same script, printing side-by-side responses."""
    _header("Memory Demo: Naive vs. Managed Agent Comparison", "bold orange1")
    _info(f"Model: {model}  |  Turns: {turns}  |  Summary threshold: {SUMMARY_THRESHOLD} messages")

    naive   = NaiveAgent(model=model)
    managed = ManagedAgent(model=model, session_name="_compare_temp")

    # Clear any leftover state from a prior compare run
    if managed._path.exists():
        managed._path.unlink()
        managed.summary = ""
        managed.recent  = []
        managed.memory_store = {}

    prompts = DEMO_TURNS[:turns]

    for i, prompt in enumerate(prompts, 1):
        print()
        _info(f">>> Turn {i}/{len(prompts)}: {prompt}")

        naive_r   = naive.chat(prompt)
        managed_r = managed.chat(prompt)

        _compare_responses(
            i, prompt, naive_r, managed_r,
            naive.context_messages, managed.context_messages,
        )

        # After memory tests (turn 5+), show memory store
        if i >= 5 and managed.memory_store:
            _info(f"  [Memory store] {managed.memory_store}")

    # Summary stats
    _header("Summary", "bold white")
    _info(f"Naive   — final context: {naive.context_messages} messages, {naive.context_chars} chars")
    _info(f"Managed — final context: {managed.context_messages} messages, {managed.context_chars} chars")
    if naive.context_chars > 0:
        reduction = (1 - managed.context_chars / naive.context_chars) * 100
        _info(f"Context reduction: {reduction:.0f}% smaller")
    if managed.summary:
        _panel("Rolling Summary (Managed Agent)", managed.summary, "green")
    if managed.memory_store:
        _panel("Long-term Memory Store", json.dumps(managed.memory_store, indent=2, ensure_ascii=False), "cyan")


def run_interactive(agent_cls, model: str, session: str) -> None:
    """Interactive chat with a single agent."""
    agent = agent_cls(model=model, session_name=session) if agent_cls == ManagedAgent \
            else NaiveAgent(model=model)

    label = "Managed" if agent_cls == ManagedAgent else "Naive"
    _header(f"{label} Memory Agent — Interactive Mode", "bold orange1")
    if agent_cls == ManagedAgent and agent.memory_store:
        _info(f"Loaded session '{session}' — {len(agent.memory_store)} memories, summary: {bool(agent.summary)}")
    _info("Type your message. Press Ctrl+C or type 'quit' to exit.\n")

    turn = 0
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not user_input or user_input.lower() in ("quit", "exit", "bye"):
            break

        turn += 1
        response = agent.chat(user_input)
        print(f"\nAssistant: {response}\n")

        ctx_info = f"[ctx: {agent.context_messages} msgs, {agent.context_chars} chars]"
        if isinstance(agent, ManagedAgent) and agent.memory_store:
            ctx_info += f"  [memories: {list(agent.memory_store.keys())}]"
        _info(ctx_info)


def run_demo(agent_cls, model: str, session: str, turns: int) -> None:
    """Run a scripted demo with one agent."""
    agent = agent_cls(model=model, session_name=session) if agent_cls == ManagedAgent \
            else NaiveAgent(model=model)
    label = "Managed" if agent_cls == ManagedAgent else "Naive"
    _header(f"{label} Memory Agent — Scripted Demo ({turns} turns)", "bold orange1")

    prompts = DEMO_TURNS[:turns]
    for i, prompt in enumerate(prompts, 1):
        _info(f"\nTurn {i}: {prompt}")
        response = agent.chat(prompt)
        _panel(f"Turn {i}", response, "green" if agent_cls == ManagedAgent else "red")
        ctx = f"context: {agent.context_messages} msgs"
        if isinstance(agent, ManagedAgent) and agent.memory_store:
            ctx += f"  |  memories: {list(agent.memory_store.keys())}"
        _info(ctx)

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Memory agent demo: naive vs. managed context."
    )
    parser.add_argument("--model",   default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=None,
                        help="Ollama base URL (default: $OLLAMA_BASE_URL or http://localhost:11434/v1)")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--turns",   type=int, default=8,
                        help="Number of scripted turns to run (max 10).")
    parser.add_argument(
        "--mode",
        choices=["compare", "naive", "managed", "interactive-naive", "interactive-managed"],
        default="compare",
        help=(
            "compare: run both agents on the same script side-by-side.\n"
            "naive/managed: run one agent through the scripted demo.\n"
            "interactive-*: free-form chat with one agent."
        ),
    )
    parser.add_argument("--session", default="default",
                        help="Session name for managed agent persistence.")
    args = parser.parse_args()

    if args.base_url:
        global OLLAMA_BASE
        OLLAMA_BASE = args.base_url

    turns = min(args.turns, len(DEMO_TURNS))

    if args.mode == "compare":
        run_compare(args.model, turns)
    elif args.mode == "naive":
        run_demo(NaiveAgent, args.model, args.session, turns)
    elif args.mode == "managed":
        run_demo(ManagedAgent, args.model, args.session, turns)
    elif args.mode == "interactive-naive":
        run_interactive(NaiveAgent, args.model, args.session)
    elif args.mode == "interactive-managed":
        run_interactive(ManagedAgent, args.model, args.session)


if __name__ == "__main__":
    main()
