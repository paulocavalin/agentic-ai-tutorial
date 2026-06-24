"""
mcp_client.py — Adapter that bridges MCP servers into the Agent tool_registry.

Connects to an MCP server (stdio or HTTP), discovers its tools, converts
MCP tool schemas to OpenAI function-calling format, and provides sync-callable
functions that bridge into the async MCP session.
"""

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


def _mcp_schema_to_openai(tool: types.Tool) -> Dict[str, Any]:
    """Convert an MCP tool definition to OpenAI function-calling schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}},
        },
    }


def _make_tool_caller(session: ClientSession, tool_name: str, loop: asyncio.AbstractEventLoop) -> Callable[..., Any]:
    """Create a sync-callable function that calls an MCP tool via the session."""
    def call_tool(**kwargs) -> Any:
        future = asyncio.run_coroutine_threadsafe(
            session.call_tool(tool_name, arguments=kwargs),
            loop,
        )
        result = future.result(timeout=120)

        # Extract text content from MCP result
        parts = []
        for content in result.content:
            if isinstance(content, types.TextContent):
                parts.append(content.text)
            elif isinstance(content, types.EmbeddedResource):
                parts.append(str(content))
            else:
                parts.append(str(content))

        combined = "\n".join(parts)

        # Try to parse as JSON for structured output
        try:
            return json.loads(combined)
        except (json.JSONDecodeError, ValueError):
            return {"result": combined}

    return call_tool


class MCPAgentClient:
    """
    Bridges an MCP server into the Agent's tool system.

    Supports two transports:
      - stdio: pass a StdioServerParameters instance
      - HTTP:  pass a URL string (e.g. "http://localhost:8000/mcp")

    Usage (inside an async function):
        # Stdio transport
        async with MCPAgentClient(StdioServerParameters(...)) as mcp:
            tools, registry = mcp.get_tools()

        # HTTP transport
        async with MCPAgentClient("http://localhost:8000/mcp") as mcp:
            tools, registry = mcp.get_tools()
    """

    def __init__(self, server_params: Union[StdioServerParameters, str]) -> None:
        self.server_params = server_params
        self._session: Optional[ClientSession] = None
        self._tools: List[types.Tool] = []
        self._read = None
        self._write = None
        self._transport_context = None
        self._session_context = None

    @property
    def _is_http(self) -> bool:
        return isinstance(self.server_params, str)

    async def __aenter__(self) -> "MCPAgentClient":
        if self._is_http:
            self._transport_context = streamablehttp_client(self.server_params)
        else:
            self._transport_context = stdio_client(self.server_params)

        result = await self._transport_context.__aenter__()
        # streamablehttp_client yields (read, write, get_session_id)
        # stdio_client yields (read, write)
        self._read, self._write = result[0], result[1]

        self._session_context = ClientSession(self._read, self._write)
        self._session = await self._session_context.__aenter__()

        await self._session.initialize()

        tools_result = await self._session.list_tools()
        self._tools = tools_result.tools
        return self

    async def __aexit__(self, *args) -> None:
        if self._session_context:
            await self._session_context.__aexit__(*args)
        if self._transport_context:
            await self._transport_context.__aexit__(*args)

    def get_tools(self, loop: asyncio.AbstractEventLoop) -> Tuple[List[Dict[str, Any]], Dict[str, Callable[..., Any]]]:
        """
        Returns (tool_schemas, tool_registry) ready for Agent().

        Args:
            loop: The running asyncio event loop (needed for sync→async bridge).
        """
        schemas = [_mcp_schema_to_openai(t) for t in self._tools]
        registry = {
            t.name: _make_tool_caller(self._session, t.name, loop)
            for t in self._tools
        }
        return schemas, registry

    @property
    def tool_names(self) -> List[str]:
        return [t.name for t in self._tools]
