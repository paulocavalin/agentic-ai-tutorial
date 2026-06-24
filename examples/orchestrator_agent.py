"""
orchestrator_agent.py — Multi-agent delegation with an orchestrator.

Demonstrates the orchestrator pattern: a top-level agent that never answers
directly, but routes requests to specialized sub-agents (weather, search)
via a delegate_to_agent tool. Each sub-agent runs independently with its
own tools and system prompt.

Key concepts:
  - Orchestrator decides which sub-agent(s) to invoke
  - Sub-agents are full Agent instances with their own tool registries
  - Orchestrator synthesizes sub-agent results into one final response

Usage:
    python examples/orchestrator_agent.py --prompt "Weather in Tokyo and latest AI news"
    python examples/orchestrator_agent.py --trace
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Agent, OllamaClient, print_final_output
from examples.search_agent import SYSTEM_PROMPT as SEARCH_SYSTEM_PROMPT


ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are an orchestrator agent. Your job is to route user requests to specialized sub-agents.\n\n"
    "Available sub-agents (via delegate_to_agent):\n"
    "- weather-agent: handles weather questions\n"
    "- search-agent: handles general research/current topics\n\n"
    "Rules:\n"
    "1. Never answer weather or research questions directly.\n"
    "2. Always delegate to one or more sub-agents first.\n"
    "3. If the user asks both weather and research, call both agents.\n"
    "4. Pass complete context to each sub-agent since they do not share memory with you.\n"
    "5. After sub-agent results return, synthesize one final response for the user.\n"
    "6. Before each delegation, include a brief planning sentence in the assistant content."
)


WEATHER_SYSTEM_PROMPT = (
    "You are a weather assistant. Use the available weather tool when needed and answer clearly."
)


delegate_to_agent_tool_schema = {
    "type": "function",
    "function": {
        "name": "delegate_to_agent",
        "description": "Delegate a task to a specialized sub-agent and return its result.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "enum": ["weather-agent", "search-agent"],
                    "description": "Which sub-agent should handle the task.",
                },
                "task_context": {
                    "type": "object",
                    "description": "Complete task context for the sub-agent.",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "Question the sub-agent should answer.",
                        }
                    },
                    "required": ["question"],
                },
            },
            "required": ["agent_name", "task_context"],
        },
    },
}


def _load_python_module(module_path: Path):
    module_name = f"tool_module_{module_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_tools(tools_root: str) -> Dict[str, Dict[str, Any]]:
    root = Path(tools_root)
    if not root.exists():
        raise FileNotFoundError(f"Tools directory not found: {tools_root}")

    catalog: Dict[str, Dict[str, Any]] = {}
    for tool_dir in sorted(root.glob("*/")):
        schema_path = tool_dir / "schema.json"
        handler_path = tool_dir / "handler.py"

        if not schema_path.exists() or not handler_path.exists():
            continue

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        function = schema.get("function", {})
        tool_name = str(function.get("name", "")).strip()
        if not tool_name:
            raise ValueError(f"Tool schema missing function.name: {schema_path}")

        module = _load_python_module(handler_path)
        run_func = getattr(module, "run", None)
        if not callable(run_func):
            raise ValueError(f"Tool handler missing callable run(**kwargs): {handler_path}")

        catalog[tool_name] = {
            "name": tool_name,
            "schema": schema,
            "func": run_func,
            "path": str(tool_dir),
        }

    if not catalog:
        raise ValueError(f"No tools discovered under: {tools_root}")
    return catalog


def _build_tool_runtime(tool_names: List[str], tool_catalog: Dict[str, Dict[str, Any]]) -> tuple:
    missing = [name for name in tool_names if name not in tool_catalog]
    if missing:
        raise ValueError(f"Missing tool implementations in catalog: {missing}")

    schemas = [tool_catalog[name]["schema"] for name in tool_names]
    funcs = {name: tool_catalog[name]["func"] for name in tool_names}
    return schemas, funcs


def build_weather_agent_with_tools(client: OllamaClient, trace: bool, tool_catalog: Dict[str, Dict[str, Any]]) -> Agent:
    schemas, funcs = _build_tool_runtime(["get_temperature"], tool_catalog)
    return Agent(
        client=client,
        system=WEATHER_SYSTEM_PROMPT,
        tools=schemas,
        tool_registry=funcs,
        trace=trace,
    )


def build_search_agent_with_tools(client: OllamaClient, trace: bool, tool_catalog: Dict[str, Dict[str, Any]]) -> Agent:
    schemas, funcs = _build_tool_runtime(["web_search", "web_fetch"], tool_catalog)
    return Agent(
        client=client,
        system=SEARCH_SYSTEM_PROMPT,
        tools=schemas,
        tool_registry=funcs,
        trace=trace,
    )


def make_delegate_tool(client: OllamaClient, trace: bool, tool_catalog: Dict[str, Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
    def delegate_to_agent(agent_name: str, task_context: Dict[str, Any]) -> Dict[str, Any]:
        question = str(task_context.get("question", "")).strip()
        if not question:
            return {"agent_name": agent_name, "error": "Missing task_context.question"}

        if trace:
            print(f"\n[TRACE] orchestrator.delegate_to_agent\nagent_name={agent_name} question={question}")

        if agent_name == "weather-agent":
            sub_agent = build_weather_agent_with_tools(client, trace, tool_catalog)
        elif agent_name == "search-agent":
            sub_agent = build_search_agent_with_tools(client, trace, tool_catalog)
        else:
            return {"agent_name": agent_name, "error": f"Unknown agent_name '{agent_name}'"}

        answer = sub_agent.execute(question)
        return {"agent_name": agent_name, "question": question, "answer": answer}

    return delegate_to_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-agent orchestrator demo")
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--tools-root", default="tools")
    parser.add_argument(
        "--prompt",
        default="What's the weather in Tokyo, and summarize the latest agentic AI trends?",
    )
    parser.add_argument("--trace", action="store_true")
    markdown_group = parser.add_mutually_exclusive_group()
    markdown_group.add_argument("--render-markdown", dest="render_markdown", action="store_true")
    markdown_group.add_argument("--raw", dest="render_markdown", action="store_false")
    parser.set_defaults(render_markdown=True)
    args = parser.parse_args()

    client = OllamaClient(model=args.model, base_url=args.base_url, timeout=args.timeout)

    print("\n=== Orchestrator Multi-Agent Demo ===")
    tool_catalog = discover_tools(args.tools_root)

    delegate_tool = make_delegate_tool(client, args.trace, tool_catalog)
    orchestrator = Agent(
        client=client,
        system=ORCHESTRATOR_SYSTEM_PROMPT,
        tools=[delegate_to_agent_tool_schema],
        tool_registry={"delegate_to_agent": delegate_tool},
        trace=args.trace,
        max_iterations=10,
    )

    response = orchestrator.execute(args.prompt)
    print("\nFinal answer:")
    print_final_output(response, render_markdown=args.render_markdown)


if __name__ == "__main__":
    main()
