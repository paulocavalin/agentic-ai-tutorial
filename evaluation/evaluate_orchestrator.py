import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Agent, OllamaClient
from examples.orchestrator_agent import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    delegate_to_agent_tool_schema,
    make_delegate_tool,
)


def load_cases(cases_path: Path) -> List[Dict[str, Any]]:
    with cases_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("Cases file must contain a JSON array.")
    return data


def run_case(
    client: OllamaClient,
    prompt: str,
    trace: bool,
) -> Tuple[str, List[str]]:
    delegated_agents: List[str] = []
    base_delegate = make_delegate_tool(client, trace=trace)

    def delegate_with_tracking(agent_name: str, task_context: Dict[str, Any]) -> Dict[str, Any]:
        delegated_agents.append(agent_name)
        return base_delegate(agent_name=agent_name, task_context=task_context)

    orchestrator = Agent(
        client=client,
        system=ORCHESTRATOR_SYSTEM_PROMPT,
        tools=[delegate_to_agent_tool_schema],
        tool_registry={"delegate_to_agent": delegate_with_tracking},
        trace=trace,
        max_iterations=10,
    )

    answer = orchestrator.execute(prompt)
    return answer, delegated_agents


def evaluate_case(case: Dict[str, Any], answer: str, delegated_agents: List[str]) -> Dict[str, Any]:
    expected_agents = case.get("expected_agents", [])
    expected_set = sorted(set(expected_agents))
    observed_set = sorted(set(delegated_agents))
    routing_ok = expected_set == observed_set

    answer_l = answer.lower()
    missing_required = [
        text for text in case.get("required_substrings", []) if text.lower() not in answer_l
    ]
    forbidden_found = [
        text for text in case.get("forbidden_substrings", []) if text.lower() in answer_l
    ]
    min_chars = int(case.get("min_answer_chars", 0))
    min_chars_ok = len(answer.strip()) >= min_chars
    answer_ok = (not missing_required) and (not forbidden_found) and min_chars_ok

    return {
        "id": case.get("id", "unknown"),
        "routing_ok": routing_ok,
        "answer_ok": answer_ok,
        "overall_ok": routing_ok and answer_ok,
        "expected_agents": expected_set,
        "observed_agents": observed_set,
        "missing_required": missing_required,
        "forbidden_found": forbidden_found,
        "min_chars": min_chars,
        "answer_len": len(answer.strip()),
    }


def print_report(results: List[Dict[str, Any]]) -> None:
    total = len(results)
    routing_hits = sum(1 for row in results if row["routing_ok"])
    answer_hits = sum(1 for row in results if row["answer_ok"])
    overall_hits = sum(1 for row in results if row["overall_ok"])

    routing_acc = routing_hits / total if total else 0.0
    answer_acc = answer_hits / total if total else 0.0
    overall_acc = overall_hits / total if total else 0.0

    print("\n=== Multi-agent orchestration evaluation ===")
    print(f"Cases run: {total}")
    print(f"Routing accuracy: {routing_acc:.2%} ({routing_hits}/{total})")
    print(f"Answer accuracy: {answer_acc:.2%} ({answer_hits}/{total})")
    print(f"Overall accuracy: {overall_acc:.2%} ({overall_hits}/{total})")

    print("\n=== Per-case results ===")
    for row in results:
        status = "PASS" if row["overall_ok"] else "FAIL"
        print(f"[{status}] {row['id']}")
        if not row["routing_ok"]:
            print(f"  - expected_agents: {row['expected_agents']}")
            print(f"  - observed_agents: {row['observed_agents']}")
        if not row["answer_ok"]:
            if row["missing_required"]:
                print(f"  - missing_required: {row['missing_required']}")
            if row["forbidden_found"]:
                print(f"  - forbidden_found: {row['forbidden_found']}")
            if row["answer_len"] < row["min_chars"]:
                print(
                    "  - answer_too_short: "
                    f"{row['answer_len']} chars < min {row['min_chars']}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate multi-agent orchestrator routing and outputs")
    parser.add_argument(
        "--cases",
        default="multi_agent_eval_cases.json",
        help="Path to evaluation cases JSON.",
    )
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable trace while running cases (verbose).",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Run only the first N cases (0 means all).",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases)
    cases = load_cases(cases_path)
    if args.max_cases > 0:
        cases = cases[: args.max_cases]

    client = OllamaClient(model=args.model, base_url=args.base_url, timeout=args.timeout)

    results: List[Dict[str, Any]] = []
    running_overall_hits = 0
    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("id", f"case_{index}"))
        prompt = str(case.get("prompt", ""))
        print("\n---")
        print(f"Running case {index}/{len(cases)}: {case_id}")
        print(f"Prompt: {prompt}")

        answer, delegated_agents = run_case(
            client=client,
            prompt=prompt,
            trace=args.trace,
        )
        result = evaluate_case(case, answer, delegated_agents)
        results.append(result)

        if result["overall_ok"]:
            running_overall_hits += 1
        print(
            "Running score: "
            f"{running_overall_hits}/{index} "
            f"({(running_overall_hits / index):.2%})"
        )

    print_report(results)


if __name__ == "__main__":
    main()
