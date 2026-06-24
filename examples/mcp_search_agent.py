"""
mcp_search_agent.py — Agent that uses an external MCP server for web search.

Demonstrates how to connect to a pre-existing MCP server (duckduckgo-mcp-server)
via stdio transport. The agent dynamically discovers available tools from the
MCP server and uses them to answer research questions.

Key concepts:
  - Connecting to an external MCP server (no code changes needed on server side)
  - Dynamic tool discovery via MCP protocol
  - Async MCP ↔ sync Agent bridge via MCPAgentClient

Prerequisites:
    pip install "mcp[cli]" duckduckgo-mcp-server

Usage:
    python examples/mcp_search_agent.py --prompt "Latest trends in AI agents 2025"
    python examples/mcp_search_agent.py --prompt "Compare Python and Rust for CLI tools" --trace
"""

import argparse
import asyncio
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import StdioServerParameters

from core import Agent, MCPAgentClient, OllamaClient, print_final_output


SYSTEM_PROMPT = (
    "You are a research assistant with access to web search tools.\n\n"
    "Instructions:\n"
    "1. Use the available search tools to find current, relevant information.\n"
    "2. Make 2-4 searches with different queries for comprehensive coverage.\n"
    "3. Synthesize findings into a clear, structured answer with citations.\n"
    "4. If a search returns insufficient results, try alternative queries.\n"
    "5. Always cite sources (URLs) in your final answer.\n"
    "6. Use markdown formatting for readability."
)


async def run_agent(model: str, base_url: str, timeout: int, prompt: str, trace: bool, render_markdown: bool) -> None:
    # Configure the MCP server to connect to
    server_params = StdioServerParameters(
        command="duckduckgo-mcp-server",
        args=[],
    )

    print("\n=== MCP Search Agent Demo ===")
    print("Connecting to duckduckgo-mcp-server via MCP stdio...")

    async with MCPAgentClient(server_params) as mcp:
        print(f"Discovered tools: {mcp.tool_names}")

        # Get the running event loop for the sync→async bridge
        loop = asyncio.get_running_loop()
        tools, registry = mcp.get_tools(loop)

        # Create LLM client and agent with MCP-discovered tools
        client = OllamaClient(model=model, base_url=base_url, timeout=timeout)
        agent = Agent(
            client=client,
            system=SYSTEM_PROMPT,
            tools=tools,
            tool_registry=registry,
            trace=trace,
            max_iterations=10,
        )

        # Run the agent in a thread to avoid blocking the async event loop
        # (Agent.execute is sync but tool calls need the async loop)
        result = await asyncio.to_thread(agent.execute, prompt)

        print("\nFinal answer:")
        print_final_output(result, render_markdown=render_markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP-powered search agent using duckduckgo-mcp-server")
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--prompt",
        default="What are the main trends in agentic AI for 2025? Give me a structured summary with sources.",
    )
    parser.add_argument("--trace", action="store_true")
    markdown_group = parser.add_mutually_exclusive_group()
    markdown_group.add_argument("--render-markdown", dest="render_markdown", action="store_true")
    markdown_group.add_argument("--raw", dest="render_markdown", action="store_false")
    parser.set_defaults(render_markdown=True)
    args = parser.parse_args()

    asyncio.run(run_agent(args.model, args.base_url, args.timeout, args.prompt, args.trace, args.render_markdown))


if __name__ == "__main__":
    main()
