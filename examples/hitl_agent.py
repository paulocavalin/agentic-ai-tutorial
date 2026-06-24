"""
hitl_agent.py — Infrastructure agent with Human-in-the-Loop approval checkpoints.

Demonstrates the Approval Checkpoint pattern: any tool marked as "destructive"
pauses execution and prompts the operator for confirmation before proceeding.
This is essential for safe agentic automation of high-impact operations.

Key concepts:
  - Destructive vs. read-only tool classification
  - Interactive approval gate before irreversible actions
  - Agent adapts when an action is denied (suggests alternatives)
  - Auto-approve mode for CI/demo scenarios

Usage:
    python examples/hitl_agent.py
    python examples/hitl_agent.py --prompt "Delete old backup files" --trace
    python examples/hitl_agent.py --auto-approve   # skip prompts (CI / demo mode)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Agent, OllamaClient, print_final_output

# ── Tool implementations (simulated) ─────────────────────────────────────────


def list_backups(bucket: str, older_than_days: int = 90) -> Dict[str, Any]:
    """Read-only. Lists backup files matching the age filter (simulated)."""
    all_files = [
        {"name": "backup-2024-10-01.tar.gz", "size_gb": 0.8,  "age_days": 102},
        {"name": "backup-2024-10-08.tar.gz", "size_gb": 0.5,  "age_days": 95},
        {"name": "backup-2024-10-15.tar.gz", "size_gb": 1.1,  "age_days": 88},
        {"name": "backup-2024-11-01.tar.gz", "size_gb": 0.9,  "age_days": 71},
        {"name": "backup-2024-11-15.tar.gz", "size_gb": 0.7,  "age_days": 57},
        {"name": "backup-2024-12-01.tar.gz", "size_gb": 1.0,  "age_days": 41},
        {"name": "backup-2024-12-15.tar.gz", "size_gb": 1.2,  "age_days": 27},
        {"name": "backup-2025-01-01.tar.gz", "size_gb": 0.95, "age_days": 10},
    ]
    eligible = [f for f in all_files if f["age_days"] > older_than_days]
    return {
        "bucket": bucket,
        "filter_days": older_than_days,
        "eligible_files": eligible,
        "total_eligible": len(eligible),
        "total_size_gb": round(sum(f["size_gb"] for f in eligible), 2),
    }


def delete_files(bucket: str, files: List[str]) -> Dict[str, Any]:
    """DESTRUCTIVE. Permanently deletes backup files from the bucket (simulated)."""
    return {
        "deleted": files,
        "count": len(files),
        "bucket": bucket,
        "status": "success",
        "note": "[SIMULATION] No files were actually deleted.",
    }


def archive_to_glacier(bucket: str, files: List[str]) -> Dict[str, Any]:
    """DESTRUCTIVE. Moves files to Glacier storage tier (simulated)."""
    return {
        "archived": files,
        "count": len(files),
        "new_storage_class": "GLACIER",
        "estimated_cost_per_gb_month": 0.004,
        "retrieval_time_hours": "3-5",
        "note": "[SIMULATION] No files were actually moved.",
    }


def check_disk_usage(path: str = "/") -> Dict[str, Any]:
    """Read-only. Returns disk usage information (simulated)."""
    return {"path": path, "total_gb": 500, "used_gb": 387, "free_gb": 113, "usage_percent": 77}


# ── Tool schemas ──────────────────────────────────────────────────────────────

list_backups_schema = {
    "type": "function",
    "function": {
        "name": "list_backups",
        "description": "Lists backup files in a bucket filtered by age. Read-only, safe.",
        "parameters": {
            "type": "object",
            "properties": {
                "bucket":          {"type": "string", "description": "S3 bucket path, e.g. s3://prod-backups"},
                "older_than_days": {"type": "integer", "description": "Return files older than this many days. Default 90."},
            },
            "required": ["bucket"],
        },
    },
}

delete_files_schema = {
    "type": "function",
    "function": {
        "name": "delete_files",
        "description": "[DESTRUTIVA] Permanently deletes a list of files from the bucket.",
        "parameters": {
            "type": "object",
            "properties": {
                "bucket": {"type": "string"},
                "files":  {"type": "array", "items": {"type": "string"}, "description": "List of file names to delete."},
            },
            "required": ["bucket", "files"],
        },
    },
}

archive_to_glacier_schema = {
    "type": "function",
    "function": {
        "name": "archive_to_glacier",
        "description": "[DESTRUTIVA] Moves files to Glacier archive tier. Reduces cost but adds retrieval delay.",
        "parameters": {
            "type": "object",
            "properties": {
                "bucket": {"type": "string"},
                "files":  {"type": "array", "items": {"type": "string"}},
            },
            "required": ["bucket", "files"],
        },
    },
}

check_disk_usage_schema = {
    "type": "function",
    "function": {
        "name": "check_disk_usage",
        "description": "Returns disk usage statistics for a path. Read-only, safe.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Filesystem path to check. Default '/'."},
            },
        },
    },
}

# ── Approval checkpoint ───────────────────────────────────────────────────────

_DESTRUCTIVE_TOOLS = {"delete_files", "archive_to_glacier"}


def _format_checkpoint(tool_name: str, args: Dict[str, Any]) -> str:
    lines = [
        "",
        "╔══════════════════════════════════════════════════════════════╗",
        "║       ⚠  APPROVAL REQUIRED — DESTRUCTIVE ACTION  ⚠         ║",
        "╚══════════════════════════════════════════════════════════════╝",
        f"  Tool      : {tool_name}",
        f"  Arguments : {json.dumps(args, ensure_ascii=False, indent=4)}",
        "",
        "  This action is irreversible or high-impact.",
        "  Review the arguments above before approving.",
        "",
        "  [A] Approve   [N] Deny   [D] Tool details",
        "──────────────────────────────────────────────────────────────",
    ]
    return "\n".join(lines)


def _ask_approval(tool_name: str, args: Dict[str, Any], auto_approve: bool) -> Tuple[bool, str]:
    """Shows an approval prompt and waits for human input."""
    print(_format_checkpoint(tool_name, args))

    if auto_approve:
        print("  [AUTO-APPROVE] Automatic approval enabled. Proceeding.\n")
        return True, "auto-approved"

    while True:
        try:
            choice = input("  Your decision [a/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Interrupted by operator.")
            return False, "interrupted"

        if choice in ("a", "s", "y", "sim", "yes"):
            return True, ""
        elif choice in ("n", "no", ""):
            try:
                reason = input("  Reason (optional): ").strip()
            except (EOFError, KeyboardInterrupt):
                reason = ""
            return False, reason or "rejected by operator"
        elif choice == "d":
            print(f"\n  Documentation for '{tool_name}':")
            schemas = {"delete_files": delete_files_schema, "archive_to_glacier": archive_to_glacier_schema}
            if tool_name in schemas:
                desc = schemas[tool_name]["function"]["description"]
                params = schemas[tool_name]["function"]["parameters"]["properties"]
                print(f"  {desc}")
                for k, v in params.items():
                    print(f"    {k}: {v.get('description', '')}")
            print()
        else:
            print("  Enter 'a' to approve or 'n' to deny.")


def make_guarded_registry(base_registry: Dict, auto_approve: bool, trace: bool) -> Dict:
    """Wraps destructive tools with an approval gate."""
    guarded = {}
    for name, fn in base_registry.items():
        if name in _DESTRUCTIVE_TOOLS:
            def _make_wrapper(fn_=fn, name_=name):
                def wrapper(**kwargs):
                    approved, reason = _ask_approval(name_, kwargs, auto_approve)
                    if not approved:
                        print(f"\n  ❌ Operation '{name_}' denied: {reason}\n")
                        return {
                            "status": "denied",
                            "tool": name_,
                            "reason": reason,
                            "note": "O agente deve propor uma alternativa ou encerrar a tarefa.",
                        }
                    print(f"\n  ✅ Aprovado. Executando '{name_}'…\n")
                    return fn_(**kwargs)
                return wrapper
            guarded[name] = _make_wrapper()
        else:
            guarded[name] = fn
    return guarded


# ── Main ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a cloud infrastructure automation agent.

You have access to tools for listing, inspecting, and modifying resources.

CRITICAL RULE: Tools marked as [DESTRUCTIVE] require human approval.
The approval system is already integrated — when you call a destructive tool,
the operator will be consulted automatically. You do not need to ask for permission manually.

After a denied operation, suggest viable alternatives.
Be objective, provide concrete numbers (size in GB, estimated costs).
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Infrastructure agent with Human-in-the-Loop approval checkpoints."
    )
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--prompt",
        default="I need to free up space in the bucket s3://prod-backups. Delete backups older than 90 days.",
    )
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve all destructive actions.")
    markdown_group = parser.add_mutually_exclusive_group()
    markdown_group.add_argument("--render-markdown", dest="render_markdown", action="store_true")
    markdown_group.add_argument("--raw", dest="render_markdown", action="store_false")
    parser.set_defaults(render_markdown=True)
    args = parser.parse_args()

    client = OllamaClient(model=args.model, base_url=args.base_url, timeout=args.timeout)

    base_registry = {
        "list_backups": list_backups,
        "delete_files": delete_files,
        "archive_to_glacier": archive_to_glacier,
        "check_disk_usage": check_disk_usage,
    }
    registry = make_guarded_registry(base_registry, args.auto_approve, args.trace)

    print("\n=== Human-in-the-Loop Infrastructure Agent ===")
    if args.auto_approve:
        print("[AUTO-APPROVE MODE: automatic approvals enabled]")

    agent = Agent(
        client=client,
        system=SYSTEM_PROMPT,
        tools=[list_backups_schema, delete_files_schema, archive_to_glacier_schema, check_disk_usage_schema],
        tool_registry=registry,
        trace=args.trace,
    )

    response = agent.execute(args.prompt)
    print("\nFinal answer:")
    print_final_output(response, render_markdown=args.render_markdown)


if __name__ == "__main__":
    main()
