"""
weather_agent.py — Simple tool-calling agent demo.

Demonstrates the basic agent loop: the LLM receives a user prompt, decides to call
a tool (get_temperature), receives the tool result, and produces a final answer.

This is the simplest possible agent — one tool, one turn of tool use.

Usage:
    python examples/weather_agent.py --prompt "What's the weather in Paris?"
    python examples/weather_agent.py --prompt "Compare Tokyo and SF weather" --trace
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Agent, OllamaClient, print_final_output


def get_temperature(city: str) -> str:
    """Get the current weather in a given city."""
    if city.lower() == "san francisco":
        return "72"
    if city.lower() == "paris":
        return "75"
    if city.lower() == "tokyo":
        return "73"
    return "70"


get_temperature_tool_schema = {
    "type": "function",
    "function": {
        "name": "get_temperature",
        "description": "Get the current temperature in a given city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city to get the temperature for.",
                }
            },
            "required": ["city"],
        },
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple weather tool-calling agent")
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--prompt",
        default="What is the weather in San Francisco?",
    )
    parser.add_argument("--trace", action="store_true")
    markdown_group = parser.add_mutually_exclusive_group()
    markdown_group.add_argument("--render-markdown", dest="render_markdown", action="store_true")
    markdown_group.add_argument("--raw", dest="render_markdown", action="store_false")
    parser.set_defaults(render_markdown=True)
    args = parser.parse_args()

    client = OllamaClient(model=args.model, base_url=args.base_url, timeout=args.timeout)

    print("\n=== Weather Agent Demo ===")
    agent = Agent(
        client=client,
        system="You are a helpful assistant that can answer questions using the provided tools.",
        tools=[get_temperature_tool_schema],
        tool_registry={"get_temperature": get_temperature},
        trace=args.trace,
    )

    response = agent.execute(args.prompt)
    print("\nFinal answer:")
    print_final_output(response, render_markdown=args.render_markdown)


if __name__ == "__main__":
    main()
