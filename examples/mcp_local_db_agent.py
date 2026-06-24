"""
mcp_local_db_agent.py — Agent that uses a custom local MCP server for inventory management.

Demonstrates how to build and connect to your own MCP server. The server
(mcp_servers/inventory_server.py) wraps a local SQLite database and exposes
tools for querying and managing product inventory.

Key concepts:
  - Building a custom MCP server with FastMCP
  - Agent discovers tools dynamically from YOUR server
  - Practical example: natural language interface to a database
  - Full lifecycle: agent queries data, reasons, and takes actions

Prerequisites:
    pip install "mcp[cli]"

Usage:
    python examples/mcp_local_db_agent.py --prompt "What products do we have in Electronics?"
    python examples/mcp_local_db_agent.py --prompt "Which items are low on stock?" --trace
    python examples/mcp_local_db_agent.py --prompt "Add a new product: USB Cable, Electronics, $9.99, 500 units"
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import StdioServerParameters

from core import Agent, MCPAgentClient, OllamaClient, print_final_output


SYSTEM_PROMPT = (
    "You are an inventory management assistant with access to a product database.\n\n"
    "You can:\n"
    "- Search and filter products by name, category, or price range\n"
    "- Check inventory statistics and low-stock alerts\n"
    "- Add new products to the catalog\n"
    "- Update stock quantities\n\n"
    "Instructions:\n"
    "1. Use the available tools to query the database — never guess product data.\n"
    "2. When the user asks about inventory, first query to get current data.\n"
    "3. Present results clearly using tables or bullet points.\n"
    "4. For stock updates, confirm what you're changing and report the result.\n"
    "5. Use markdown formatting for readability.\n"
    "6. Answer in the same language as the user's question."
)

# Path to our custom MCP server
SERVER_PATH = str(Path(__file__).resolve().parent.parent / "mcp_servers" / "inventory_server.py")


async def run_agent(model: str, base_url: str, timeout: int, prompt: str, trace: bool, render_markdown: bool) -> None:
    # Configure our custom MCP server (spawned via stdio)
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER_PATH],
    )

    print("\n=== MCP Local Database Agent Demo ===")
    print(f"Connecting to inventory MCP server ({SERVER_PATH})...")

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
        )

        # Run the agent in a thread (sync Agent, async MCP tools)
        result = await asyncio.to_thread(agent.execute, prompt)

        print("\nFinal answer:")
        print_final_output(result, render_markdown=render_markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP-powered inventory agent using a local SQLite server")
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--prompt",
        default="Give me an overview of the inventory: how many products, what categories, and which items are low on stock?",
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
