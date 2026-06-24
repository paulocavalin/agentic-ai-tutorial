"""
evaluate_agent.py — Generic agent evaluation framework.

Runs a set of test cases against any agent script (via subprocess or direct import),
scoring each case on three metrics:

  1. tool_routing  — did the agent call the expected tools?
  2. substring     — does the answer contain required text and exclude forbidden text?
  3. llm_judge     — LLM-as-judge: does the answer satisfy the stated criteria?

Test cases are defined in a JSON file:
  [
    {
      "id": "basic_search",
      "prompt": "What is the capital of France?",
      "expected_tools": ["web_search"],           // optional
      "required_substrings": ["Paris"],           // optional
      "forbidden_substrings": ["I don't know"],   // optional
      "min_answer_chars": 20,                     // optional
      "judge_criteria": "The answer must name Paris as the capital of France."  // optional
    },
    ...
  ]

Usage:
  # Evaluate the search agent:
  uv run python evaluate_agent.py \\
    --cases eval_cases.json \\
    --agent search

  # Evaluate the extraction agent on invoice cases:
  uv run python evaluate_agent.py \\
    --cases invoice_eval_cases.json \\
    --agent extraction \\
    --agent-args "--schema invoice"

  # Full report with LLM-as-judge:
  uv run python evaluate_agent.py \\
    --cases eval_cases.json \\
    --agent search \\
    --judge \\
    --output results.json
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import OllamaClient

# ── Test case schema ──────────────────────────────────────────────────────────

def load_cases(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Cases file must be a JSON array, got {type(data).__name__}.")
    return data


# ── Agent runners ─────────────────────────────────────────────────────────────

_AGENT_SCRIPTS = {
    "search":     "ollama_search_agent.py",
    "extraction": "ollama_extraction_agent.py",
    "hitl":       "ollama_hitl_agent.py",
    "guardrails": "ollama_guardrails_agent.py",
    "single":     "ollama_single_agent_skills.py",
    "orchestrator": "ollama_orchestrator_agent.py",
}


def run_agent_subprocess(
    script: str,
    prompt: str,
    extra_args: List[str],
    model: str,
    base_url: str,
    timeout: int,
) -> Tuple[str, List[str], float]:
    """
    Runs an agent script in a subprocess and captures stdout.
    Returns (answer_text, tool_calls_detected, elapsed_seconds).
    """
    cmd = [
        sys.executable, script,
        "--prompt", prompt,
        "--model", model,
        "--base-url", base_url,
        "--timeout", str(timeout),
        "--raw",   # no markdown rendering so we get plain text
    ] + extra_args

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 30,
        )
        elapsed = time.monotonic() - start
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Attempt to extract tool calls from trace output in stderr / stdout
        tool_calls = _parse_tool_calls(stdout + stderr)

        # Extract the "Final answer:" section if present
        answer = _extract_answer(stdout)
        return answer, tool_calls, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return "[TIMEOUT]", [], elapsed
    except Exception as exc:
        elapsed = time.monotonic() - start
        return f"[ERROR: {exc}]", [], elapsed


def _extract_answer(stdout: str) -> str:
    """Extracts text after 'Final answer:' marker, falls back to full stdout."""
    marker = "Final answer:"
    idx = stdout.find(marker)
    if idx != -1:
        return stdout[idx + len(marker):].strip()
    return stdout.strip()


def _parse_tool_calls(output: str) -> List[str]:
    """Heuristically extracts tool names called from trace/log output."""
    tools: List[str] = []
    for line in output.splitlines():
        line_lower = line.lower()
        if "tool_call" in line_lower or "calling tool" in line_lower or '"name":' in line_lower:
            # Look for known tool names in the line
            for known in [
                "web_search", "web_fetch", "list_backups", "delete_files",
                "archive_to_glacier", "check_disk_usage", "extract_invoice",
                "extract_contact", "extract_meeting", "delegate_to_agent",
                "remember", "recall", "search_documents",
            ]:
                if known in line:
                    if known not in tools:
                        tools.append(known)
    return tools


# ── Metrics ───────────────────────────────────────────────────────────────────

def score_routing(case: Dict[str, Any], tool_calls: List[str]) -> Dict[str, Any]:
    expected = case.get("expected_tools", [])
    if not expected:
        return {"metric": "tool_routing", "score": None, "note": "not specified"}
    expected_set = sorted(set(expected))
    observed_set = sorted(set(tool_calls))
    passed = all(t in observed_set for t in expected_set)
    return {
        "metric": "tool_routing",
        "score": 1.0 if passed else 0.0,
        "expected": expected_set,
        "observed": observed_set,
        "missing": [t for t in expected_set if t not in observed_set],
    }


def score_substrings(case: Dict[str, Any], answer: str) -> Dict[str, Any]:
    answer_l = answer.lower()
    required  = case.get("required_substrings", [])
    forbidden = case.get("forbidden_substrings", [])
    min_chars = int(case.get("min_answer_chars", 0))

    missing  = [s for s in required  if s.lower() not in answer_l]
    found_fb = [s for s in forbidden if s.lower() in answer_l]
    long_enough = len(answer.strip()) >= min_chars

    if not required and not forbidden and not min_chars:
        return {"metric": "substring", "score": None, "note": "not specified"}

    passed = not missing and not found_fb and long_enough
    result = {
        "metric": "substring",
        "score": 1.0 if passed else 0.0,
        "missing_required": missing,
        "forbidden_found": found_fb,
    }
    if min_chars:
        result["min_chars"] = min_chars
        result["answer_len"] = len(answer.strip())
        result["length_ok"] = long_enough
    return result


# ── LLM-as-judge ─────────────────────────────────────────────────────────────

_JUDGE_SYSTEM = (
    "You are a strict evaluator. Given a prompt, an expected criteria, and an agent response, "
    "decide if the response satisfies the criteria.\n"
    "Return ONLY valid JSON: "
    '{"verdict": "PASS" | "FAIL", "score": 0.0-1.0, "reason": "<one sentence>"}'
)


def score_llm_judge(
    client: OllamaClient,
    case: Dict[str, Any],
    answer: str,
) -> Dict[str, Any]:
    criteria = case.get("judge_criteria")
    if not criteria:
        return {"metric": "llm_judge", "score": None, "note": "not specified"}

    import requests as _requests
    import re

    user_msg = (
        f"Prompt: {case['prompt']}\n\n"
        f"Criteria: {criteria}\n\n"
        f"Agent response:\n{answer[:2000]}"
    )
    try:
        payload = {
            "model": client.model,
            "messages": [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        }
        resp = _requests.post(
            f"{client.base_url}/chat/completions",
            json=payload,
            timeout=client.timeout,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]

        json_match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            score = float(data.get("score", 0.0))
            return {
                "metric": "llm_judge",
                "score": score,
                "verdict": data.get("verdict", "UNKNOWN"),
                "reason": data.get("reason", ""),
            }
    except Exception as exc:
        return {"metric": "llm_judge", "score": None, "error": str(exc)}

    return {"metric": "llm_judge", "score": None, "note": "parse failed", "raw": raw}


# ── Aggregate & report ────────────────────────────────────────────────────────

def aggregate(scores: List[Dict[str, Any]]) -> float:
    """Computes mean score over metrics that have a numeric score."""
    values = [s["score"] for s in scores if isinstance(s.get("score"), (int, float))]
    return sum(values) / len(values) if values else 0.0


def print_report(results: List[Dict[str, Any]]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["overall_score"] >= 1.0)
    avg = sum(r["overall_score"] for r in results) / total if total else 0.0

    print("\n" + "═" * 60)
    print("  Agent Evaluation Report")
    print("═" * 60)
    print(f"  Cases run : {total}")
    print(f"  Passed    : {passed}/{total}")
    print(f"  Avg score : {avg:.2%}")
    print("═" * 60)

    for r in results:
        icon = "✅" if r["overall_score"] >= 1.0 else ("⚠" if r["overall_score"] >= 0.5 else "❌")
        print(f"\n{icon}  [{r['id']}]  score={r['overall_score']:.2f}  ({r['elapsed']:.1f}s)")
        for s in r["scores"]:
            if s.get("score") is None:
                continue
            score_str = f"{s['score']:.2f}"
            print(f"     {s['metric']:16s} {score_str}", end="")
            if s.get("missing_required"):
                print(f"  missing: {s['missing_required']}", end="")
            if s.get("forbidden_found"):
                print(f"  forbidden: {s['forbidden_found']}", end="")
            if s.get("missing"):
                print(f"  tools missing: {s['missing']}", end="")
            if s.get("reason"):
                print(f"  judge: {s['reason']}", end="")
            print()

    print("\n" + "═" * 60)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generic agent evaluation framework."
    )
    parser.add_argument("--cases", type=Path, default=Path("eval_cases.json"),
                        help="Path to test cases JSON file.")
    parser.add_argument("--agent", choices=list(_AGENT_SCRIPTS.keys()),
                        default="search",
                        help="Which agent script to evaluate.")
    parser.add_argument("--agent-args", type=str, default="",
                        help="Extra CLI args to pass to the agent script (e.g. '--schema invoice').")
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--judge", action="store_true",
                        help="Run LLM-as-judge scoring (requires judge_criteria in cases).")
    parser.add_argument("--max-cases", type=int, default=None,
                        help="Limit number of cases to run.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Save results JSON to this file.")
    parser.add_argument("--trace", action="store_true",
                        help="Pass --trace to agent (verbose, slows output parsing).")
    args = parser.parse_args()

    if not args.cases.exists():
        print(f"Error: cases file not found: {args.cases}", file=sys.stderr)
        sys.exit(1)

    cases = load_cases(args.cases)
    if args.max_cases:
        cases = cases[:args.max_cases]

    script = _AGENT_SCRIPTS[args.agent]
    extra_args = args.agent_args.split() if args.agent_args else []
    if args.trace:
        extra_args.append("--trace")

    client = OllamaClient(model=args.model, base_url=args.base_url, timeout=args.timeout)
    results = []

    for i, case in enumerate(cases, 1):
        case_id = case.get("id", f"case_{i}")
        prompt  = case.get("prompt", "")
        print(f"[{i}/{len(cases)}] Running: {case_id}  …", end=" ", flush=True)

        answer, tool_calls, elapsed = run_agent_subprocess(
            script, prompt, extra_args, args.model, args.base_url, args.timeout
        )

        scores = [
            score_routing(case, tool_calls),
            score_substrings(case, answer),
        ]
        if args.judge:
            scores.append(score_llm_judge(client, case, answer))

        overall = aggregate(scores)
        icon = "✅" if overall >= 1.0 else ("⚠" if overall >= 0.5 else "❌")
        print(f"{icon} ({overall:.2f})")

        results.append({
            "id":            case_id,
            "prompt":        prompt,
            "answer":        answer,
            "tool_calls":    tool_calls,
            "elapsed":       round(elapsed, 2),
            "overall_score": round(overall, 4),
            "scores":        scores,
        })

    print_report(results)

    if args.output:
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
