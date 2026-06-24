# SimpleAgent — Agentic AI Examples

CLI tool-calling agents using local [Ollama](https://ollama.com/) inference.  
Default model: **gemma4:12b** via `http://localhost:11434/v1`.

> 📖 **[Open the Tutorial](https://paulocavalin.github.io/agentic-ai-tutorial/)** — A progressive, bilingual (EN/PT) guide covering all examples.


## Directory Structure

```
SimpleAgent/
├── core/                   # Agent framework (LLM client + agent loop)
│   ├── models.py           #   Dataclasses: Message, ToolCall, etc.
│   ├── client.py           #   OllamaClient (OpenAI-compatible HTTP)
│   ├── agent.py            #   Agent class (tool-calling loop)
│   ├── mcp_client.py       #   MCPAgentClient (MCP→Agent bridge)
│   └── output.py           #   Rich markdown rendering
├── examples/               # Runnable demos (one per pattern)
│   ├── weather_agent.py    #   Simple single-tool agent
│   ├── search_agent.py     #   Web search + page fetch
│   ├── orchestrator_agent.py   Multi-agent delegation
│   ├── skills_agent.py     #   Dynamic skill/tool loading
│   ├── guardrails_agent.py #   Input/output safety layers
│   ├── hitl_agent.py       #   Human-in-the-loop approval
│   ├── extraction_agent.py #   Structured data extraction
│   ├── memory_agent.py     #   Context memory management
│   ├── mcp_search_agent.py #   MCP: external search server
│   └── mcp_local_db_agent.py   MCP: custom local DB server
├── mcp_servers/            # Custom MCP servers
│   └── inventory_server.py #   SQLite inventory (FastMCP)
├── evaluation/             # Agent evaluation framework
├── tools/                  # Plugin tools (schema.json + handler.py)
├── skills/                 # Skill definitions (SKILL.md)
├── docs/                   # Flow diagrams and explanations
├── notebooks/              # Jupyter notebooks
└── requirements.txt
```

## Setup

```bash
# Prerequisites: Ollama running with gemma4:12b pulled
ollama pull gemma4:12b

# Install dependencies
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

## Running Examples

Each example is self-contained and runs from the project root:

```bash
# Simple weather agent
python examples/weather_agent.py --prompt "What's the weather in Paris?"

# Web search agent
python examples/search_agent.py --prompt "Latest AI trends 2025" --trace

# Multi-agent orchestrator
python examples/orchestrator_agent.py --prompt "Weather in Tokyo and AI news"

# Dynamic skills
python examples/skills_agent.py --prompt "Search for quantum computing news"

# Guardrails (input validation + PII redaction)
python examples/guardrails_agent.py --prompt "Top 3 AI trends"

# Human-in-the-loop
python examples/hitl_agent.py --auto-approve

# Structured extraction
python examples/extraction_agent.py --schema invoice --input "NF ACME, R$1200"

# Memory comparison (naive vs managed)
python examples/memory_agent.py --mode compare

# MCP: External search server (duckduckgo-mcp-server)
python examples/mcp_search_agent.py --prompt "Latest trends in AI agents"

# MCP: Custom local database server
python examples/mcp_local_db_agent.py --prompt "What products are low on stock?"
```

## Common CLI Flags

All examples share these flags:

| Flag | Description |
|------|-------------|
| `--model` | Ollama model name (default: `gemma4:12b`) |
| `--base-url` | Ollama API URL (default: `http://localhost:11434/v1`) |
| `--timeout` | Request timeout in seconds (default: 120) |
| `--trace` | Print full agent loop trace |
| `--render-markdown` / `--raw` | Toggle Rich markdown rendering |

## Evaluation

```bash
python evaluation/evaluate_orchestrator.py --max-cases 3
python evaluation/evaluate_agent.py --help
```
