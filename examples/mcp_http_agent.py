"""
mcp_http_agent.py — Agent that connects to an MCP server via HTTP transport.

Demonstrates how to use the Streamable HTTP transport instead of stdio.
The agent connects to a running MCP server (notes_http_server.py) over HTTP
and uses its tools to manage notes.

Key concepts:
  - MCP over HTTP (Streamable HTTP transport)
  - Same MCPAgentClient, different transport (just pass a URL)
  - Server runs independently — can be on another machine

Prerequisites:
    1. Start the notes server first:
       python mcp_servers/notes_http_server.py

    2. Then run this agent:
       python examples/mcp_http_agent.py --prompt "Create a note about Python decorators"

Usage:
    python examples/mcp_http_agent.py --prompt "List all my notes"
    python examples/mcp_http_agent.py --prompt "Create a note titled 'Meeting' with action items" --trace
    python examples/mcp_http_agent.py --prompt "Delete all notes about testing" --trace
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Agent, MCPAgentClient, OllamaClient, print_final_output


SYSTEM_PROMPT = (
    "You are a helpful note-taking assistant with access to a notes database.\n\n"
    "You can:\n"
    "- Create new notes with a title and content\n"
    "- List all existing notes\n"
    "- Read the full content of a specific note\n"
    "- Delete notes that are no longer needed\n\n"
    "When creating notes, write clear and well-organized content.\n"
    "When listing notes, present them in a readable format.\n"
    "Always confirm actions you've taken."
)

DEFAULT_SERVER_URL = "http://localhost:8000/mcp"


async def main():
    parser = argparse.ArgumentParser(description="Notes agent (MCP over HTTP)")
    parser.add_argument("--prompt", required=True, help="User request")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL, help="MCP server URL")
    parser.add_argument("--model", default="gemma4:12b", help="Ollama model")
    parser.add_argument("--base-url", default="http://localhost:11434/v1", help="Ollama API base URL")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds")
    parser.add_argument("--trace", action="store_true", help="Show tool call traces")
    parser.add_argument("--render-markdown", action="store_true", default=True, help="Render output as markdown")
    parser.add_argument("--raw", action="store_true", help="Output raw text (no markdown)")
    args = parser.parse_args()

    client = OllamaClient(model=args.model, base_url=args.base_url, timeout=args.timeout)

    # Connect to MCP server via HTTP — just pass the URL string
    async with MCPAgentClient(args.server_url) as mcp:
        loop = asyncio.get_running_loop()
        tools, registry = mcp.get_tools(loop)

        if args.trace:
            print(f"[MCP] Connected to {args.server_url}")
            print(f"[MCP] Available tools: {mcp.tool_names}\n")

        agent = Agent(
            client=client,
            tools=tools,
            tool_registry=registry,
            system=SYSTEM_PROMPT,
            trace=args.trace,
        )

        # Run agent in a thread so tool calls can bridge back to the async loop
        result = await asyncio.to_thread(agent.execute, args.prompt)
        print_final_output(result, render_markdown=args.render_markdown and not args.raw)


if __name__ == "__main__":
    asyncio.run(main())
