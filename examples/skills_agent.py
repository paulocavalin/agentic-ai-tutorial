"""
skills_agent.py — Single agent with dynamic skill loading.

Demonstrates an agent that starts with only one meta-tool (load_skill) and
dynamically discovers and activates domain-specific tools at runtime.
Skills are defined as Markdown files (skills/*/SKILL.md) that describe
available tools; tools are discovered from the tools/ directory.

Key concepts:
  - Lazy tool activation (agent starts lightweight)
  - Skill catalog as a registry of capabilities
  - Tools auto-registered after skill is loaded

Usage:
    python examples/skills_agent.py --prompt "Weather in Tokyo and latest AI news"
    python examples/skills_agent.py --prompt "Create a plan for my project" --trace
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Agent, OllamaClient, print_final_output


BASE_SYSTEM_PROMPT = (
    "You are a single assistant with dynamic skills.\n\n"
    "You start with only one capability tool: load_skill(skill_name).\n"
    "For any user request that needs a domain skill, you MUST call load_skill first.\n"
    "After a skill is loaded, its tools become available automatically.\n"
    "Then use those tools to answer the user.\n\n"
    "Rules:\n"
    "1. Never assume a skill is loaded before calling load_skill.\n"
    "2. You can load multiple skills for combined requests.\n"
    "3. Do not use tools that are not currently available.\n"
    "4. Use tools when needed; do not hallucinate tool outputs.\n"
    "5. Keep final answers clear and concise, using markdown when helpful."
)


LOAD_SKILL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "load_skill",
        "description": "Load a skill by name and activate its tools automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Skill name to load.",
                }
            },
            "required": ["skill_name"],
        },
    },
}


def parse_skill_markdown(content: str) -> Dict[str, Any]:
    lines = [line.rstrip() for line in content.splitlines()]
    name = ""
    description_lines: List[str] = []
    instructions_lines: List[str] = []
    tools: List[str] = []
    section = ""

    for line in lines:
        if line.startswith("# "):
            name = line[2:].strip().lower()
            continue
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue

        stripped = line.strip()
        if section == "description" and stripped:
            description_lines.append(stripped)
        elif section == "instructions" and stripped:
            instructions_lines.append(stripped)
        elif section == "tools" and stripped.startswith("- "):
            tools.append(stripped[2:].strip())

    if not name:
        raise ValueError("Skill markdown missing '# <name>' title")
    if not tools:
        raise ValueError(f"Skill '{name}' has no tools declared")

    return {
        "name": name,
        "description": " ".join(description_lines).strip(),
        "instructions": "\n".join(instructions_lines).strip(),
        "tools": tools,
        "content": content,
    }


def discover_skill_catalog(skills_root: str) -> Dict[str, Dict[str, Any]]:
    root = Path(skills_root)
    if not root.exists():
        raise FileNotFoundError(f"Skills directory not found: {skills_root}")

    catalog: Dict[str, Dict[str, Any]] = {}
    for skill_file in sorted(root.glob("*/SKILL.md")):
        parsed = parse_skill_markdown(skill_file.read_text(encoding="utf-8"))
        parsed["path"] = str(skill_file)
        catalog[parsed["name"]] = parsed

    if not catalog:
        raise ValueError(f"No SKILL.md files found under: {skills_root}")
    return catalog


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
        doc_path = tool_dir / "TOOL.md"

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

        doc = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""

        catalog[tool_name] = {
            "name": tool_name,
            "schema": schema,
            "func": run_func,
            "doc": doc,
            "path": str(tool_dir),
        }

    if not catalog:
        raise ValueError(f"No tools discovered under: {tools_root}")
    return catalog


def build_skill_catalog_text(skill_catalog: Dict[str, Dict[str, Any]]) -> str:
    lines: List[str] = []
    for skill_name, item in sorted(skill_catalog.items()):
        desc = item.get("description", "")
        tools = ", ".join(item.get("tools", []))
        lines.append(f"- {skill_name}: {desc} (tools: {tools})")
    return "\n".join(lines)


def make_load_skill_tool(
    agent: Agent,
    skill_catalog: Dict[str, Dict[str, Any]],
    tool_catalog: Dict[str, Dict[str, Any]],
    trace: bool,
) -> Callable[..., Dict[str, Any]]:
    loaded_skills: set[str] = set()
    activated_tools: set[str] = set()

    def load_skill(skill_name: str) -> Dict[str, Any]:
        name = str(skill_name).strip().lower()
        if not name:
            return {"ok": False, "error": "skill_name is required"}
        if name not in skill_catalog:
            return {
                "ok": False,
                "error": f"Unknown skill '{name}'",
                "available_skills": sorted(skill_catalog.keys()),
            }

        skill = skill_catalog[name]
        if name not in loaded_skills:
            loaded_skills.add(name)
            agent.messages.append(
                {
                    "role": "system",
                    "content": (
                        f"[LOADED SKILL: {name}]\n"
                        "Skill details below are now active:\n\n"
                        f"{skill['content']}"
                    ),
                }
            )

        newly_activated: List[str] = []
        for tool_name in skill.get("tools", []):
            if tool_name in activated_tools:
                continue
            if tool_name not in tool_catalog:
                continue
            activated_tools.add(tool_name)
            newly_activated.append(tool_name)
            agent.tools.append(tool_catalog[tool_name]["schema"])
            agent.tool_registry[tool_name] = tool_catalog[tool_name]["func"]

        if trace:
            print("\n[TRACE] load_skill")
            print(json.dumps({
                "skill": name,
                "newly_activated_tools": newly_activated,
                "loaded_skills": sorted(loaded_skills),
                "active_tools": sorted(activated_tools),
            }, ensure_ascii=True, indent=2))

        return {
            "ok": True,
            "skill_name": name,
            "loaded_skills": sorted(loaded_skills),
            "newly_activated_tools": newly_activated,
            "active_tools": sorted(activated_tools),
        }

    return load_skill


def build_agent(
    client: OllamaClient,
    skill_catalog: Dict[str, Dict[str, Any]],
    tool_catalog: Dict[str, Dict[str, Any]],
    trace: bool,
) -> Agent:
    skill_catalog_text = build_skill_catalog_text(skill_catalog)
    system_prompt = (
        f"{BASE_SYSTEM_PROMPT}\n\n"
        "Available Skill Catalog (lightweight):\n"
        f"{skill_catalog_text}\n\n"
        "Remember: call load_skill before using domain tools."
    )

    agent = Agent(
        client=client,
        system=system_prompt,
        tools=[LOAD_SKILL_TOOL_SCHEMA],
        tool_registry={},
        trace=trace,
        max_iterations=12,
    )

    agent.tool_registry["load_skill"] = make_load_skill_tool(agent, skill_catalog, tool_catalog, trace)
    return agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-agent with dynamic skill loading")
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--skills-root", default="skills")
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

    print("\n=== Skills Agent Demo ===")
    skill_catalog = discover_skill_catalog(args.skills_root)
    tool_catalog = discover_tools(args.tools_root)

    agent = build_agent(client, skill_catalog, tool_catalog, args.trace)
    response = agent.execute(args.prompt)
    print("\nFinal answer:")
    print_final_output(response, render_markdown=args.render_markdown)


if __name__ == "__main__":
    main()
