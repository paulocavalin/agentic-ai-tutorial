"""
extraction_agent.py — Structured data extraction using tool calling.

Demonstrates how to use the LLM's tool-calling mechanism as a structured output
channel: instead of generating free text, the model fills in tool parameters
that match a JSON schema, effectively extracting structured data from text.

Built-in schemas:
  - invoice:  vendor, total, items, dates, confidence
  - contact:  name, email, phone, company, address
  - meeting:  title, date, attendees, action_items, decisions

Key concepts:
  - Tool calling as structured output (not free-text generation)
  - Schema-driven extraction (any JSON schema works)
  - Confidence scoring by the model itself

Usage:
    python examples/extraction_agent.py --schema invoice --input "NF ACME, R$1200, venc 30/01/2025"
    echo "Call with Ana at 3pm Monday re: budget" | python examples/extraction_agent.py --schema meeting
    python examples/extraction_agent.py --schema-file my_schema.json --input-file document.txt
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Agent, OllamaClient, print_final_output

# ── Built-in schemas ──────────────────────────────────────────────────────────

_INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor":          {"type": ["string", "null"], "description": "Supplier/vendor name."},
        "invoice_number":  {"type": ["string", "null"], "description": "Invoice/NF-e number."},
        "issue_date":      {"type": ["string", "null"], "description": "Issue date in YYYY-MM-DD format."},
        "due_date":        {"type": ["string", "null"], "description": "Payment due date in YYYY-MM-DD format."},
        "currency":        {"type": "string", "enum": ["BRL", "USD", "EUR", "GBP"], "description": "Currency code."},
        "subtotal":        {"type": ["number", "null"], "description": "Subtotal before taxes."},
        "tax_amount":      {"type": ["number", "null"], "description": "Total tax amount."},
        "total":           {"type": "number", "description": "Final total amount due."},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity":    {"type": "number"},
                    "unit_price":  {"type": "number"},
                    "line_total":  {"type": "number"},
                },
                "required": ["description", "quantity", "unit_price", "line_total"],
            },
        },
        "notes":      {"type": ["string", "null"], "description": "Any additional notes or observations."},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"],
                       "description": "Your confidence in the extraction quality."},
    },
    "required": ["total", "confidence"],
}

_CONTACT_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name":  {"type": ["string", "null"], "description": "Person's full name."},
        "email":      {"type": ["string", "null"], "description": "Email address."},
        "phone":      {"type": ["string", "null"], "description": "Phone number, normalized."},
        "company":    {"type": ["string", "null"], "description": "Company or organization."},
        "job_title":  {"type": ["string", "null"], "description": "Job title or role."},
        "address":    {"type": ["string", "null"], "description": "Mailing or office address."},
        "website":    {"type": ["string", "null"], "description": "Website or LinkedIn URL."},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["confidence"],
}

_MEETING_SCHEMA = {
    "type": "object",
    "properties": {
        "title":       {"type": ["string", "null"], "description": "Meeting title or subject."},
        "date":        {"type": ["string", "null"], "description": "Meeting date in YYYY-MM-DD format."},
        "time":        {"type": ["string", "null"], "description": "Meeting time in HH:MM format (24h)."},
        "duration_minutes": {"type": ["integer", "null"], "description": "Duration in minutes."},
        "attendees":   {"type": "array", "items": {"type": "string"}, "description": "List of attendee names."},
        "agenda":      {"type": ["string", "null"], "description": "Meeting agenda or topics."},
        "decisions":   {"type": "array", "items": {"type": "string"}, "description": "Decisions made."},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "owner":    {"type": "string"},
                    "task":     {"type": "string"},
                    "due_date": {"type": ["string", "null"]},
                },
                "required": ["owner", "task"],
            },
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["confidence"],
}

_BUILTIN_SCHEMAS: Dict[str, Dict] = {
    "invoice": _INVOICE_SCHEMA,
    "contact": _CONTACT_SCHEMA,
    "meeting": _MEETING_SCHEMA,
}

# ── Tool builder ──────────────────────────────────────────────────────────────

def _build_tool_schema(schema_name: str, properties: Dict) -> Dict:
    return {
        "type": "function",
        "function": {
            "name": f"extract_{schema_name}",
            "description": (
                f"Extract structured {schema_name} data from the provided text. "
                "Use null for fields not present in the text. Never invent values."
            ),
            "parameters": properties,
        },
    }


def _build_validate_tool() -> Dict:
    return {
        "type": "function",
        "function": {
            "name": "report_unrecognized",
            "description": "Call this when the text does not match the expected document type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why the document was not recognized."},
                },
                "required": ["reason"],
            },
        },
    }


# ── Tool registry ─────────────────────────────────────────────────────────────

_extracted_result: Optional[Dict] = None


def _make_extract_fn(schema_name: str, schema_props: Dict):
    def extract(**kwargs) -> Dict[str, Any]:
        global _extracted_result
        validated = {}
        props = schema_props.get("properties", {})
        for key, value in kwargs.items():
            if key in props:
                if value == "" or value == "N/A" or value == "n/a":
                    validated[key] = None
                else:
                    validated[key] = value
            else:
                validated[key] = value
        _extracted_result = validated
        return {"status": "extracted", "fields_filled": len([v for v in validated.values() if v is not None])}
    extract.__name__ = f"extract_{schema_name}"
    return extract


def _report_unrecognized(reason: str) -> Dict[str, Any]:
    global _extracted_result
    _extracted_result = {"error": "unrecognized", "reason": reason, "confidence": "low"}
    return {"status": "reported"}


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(schema_name: str) -> str:
    return f"""You are a document data extraction specialist.

Your task: extract structured {schema_name} data from the text provided by the user.

RULES:
1. ALWAYS call the extract_{schema_name} tool. Never respond with free text.
2. Use null for any field not present in the text. Do NOT invent or guess values.
3. Normalize dates to YYYY-MM-DD format.
4. Normalize monetary values to plain numbers (remove R$, $, commas as thousand separators).
5. If the document clearly does not match the expected type, call report_unrecognized instead.
6. Set confidence to "low" if you had to make significant assumptions.
7. Set confidence to "high" only if all required fields were clearly present.
"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    global _extracted_result

    parser = argparse.ArgumentParser(
        description="Extract structured JSON from unstructured text using an Ollama agent."
    )
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--timeout", type=int, default=120)

    schema_group = parser.add_mutually_exclusive_group()
    schema_group.add_argument("--schema", choices=list(_BUILTIN_SCHEMAS.keys()))
    schema_group.add_argument("--schema-file", type=Path)

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--input", type=str, help="Input text directly.")
    input_group.add_argument("--input-file", type=Path, help="Path to input text file.")

    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--pretty", action="store_true", default=True)
    parser.add_argument("--compact", dest="pretty", action="store_false")
    args = parser.parse_args()

    # Resolve schema
    if args.schema:
        schema_name = args.schema
        schema_props = _BUILTIN_SCHEMAS[schema_name]
    elif args.schema_file:
        if not args.schema_file.exists():
            print(f"Error: schema file not found: {args.schema_file}", file=sys.stderr)
            sys.exit(1)
        raw = json.loads(args.schema_file.read_text())
        schema_name = args.schema_file.stem
        schema_props = raw
    else:
        parser.error("Provide --schema <name> or --schema-file <path>.")

    # Resolve input text
    if args.input:
        text = args.input
    elif args.input_file:
        if not args.input_file.exists():
            print(f"Error: input file not found: {args.input_file}", file=sys.stderr)
            sys.exit(1)
        text = args.input_file.read_text()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.error("Provide --input <text>, --input-file <path>, or pipe text via stdin.")

    # Build and run agent
    tool_schema = _build_tool_schema(schema_name, schema_props)
    extract_fn = _make_extract_fn(schema_name, schema_props)
    validate_tool = _build_validate_tool()

    client = OllamaClient(model=args.model, base_url=args.base_url, timeout=args.timeout)
    agent = Agent(
        client=client,
        system=_build_system_prompt(schema_name),
        tools=[tool_schema, validate_tool],
        tool_registry={f"extract_{schema_name}": extract_fn, "report_unrecognized": _report_unrecognized},
        trace=args.trace,
    )

    print(f"\n=== Extraction Agent | schema: {schema_name} ===\n")
    agent.execute(f"Extract {schema_name} data from the following text:\n\n{text}")

    # Print result
    if _extracted_result is None:
        print("Warning: agent did not call the extraction tool.", file=sys.stderr)
        sys.exit(1)

    if args.pretty:
        print(json.dumps(_extracted_result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(_extracted_result, ensure_ascii=False))

    confidence = _extracted_result.get("confidence", "unknown")
    confidence_icon = {"high": "✅", "medium": "⚠", "low": "❌"}.get(confidence, "?")
    print(f"\n{confidence_icon} Confidence: {confidence}", file=sys.stderr)


if __name__ == "__main__":
    main()
