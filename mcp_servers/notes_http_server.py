"""
notes_http_server.py — MCP server with Streamable HTTP transport.

A simple notes management server that persists notes to a local JSON file.
Demonstrates how to expose MCP tools over HTTP instead of stdio.

Tools:
  - create_note: Create a new note with title and content
  - list_notes: List all notes (title + id)
  - get_note: Get full content of a note by ID
  - delete_note: Delete a note by ID

Usage:
    python mcp_servers/notes_http_server.py
    python mcp_servers/notes_http_server.py --port 9000
    python mcp_servers/notes_http_server.py --file my_notes.json

The server listens on http://localhost:8000/mcp by default.
Connect an agent using the Streamable HTTP transport.
"""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# --- Storage ---

NOTES_FILE = Path("notes.json")


def _load_notes() -> dict:
    """Load notes from the JSON file."""
    if NOTES_FILE.exists():
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    return {}


def _save_notes(notes: dict) -> None:
    """Save notes to the JSON file."""
    NOTES_FILE.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")


# --- MCP Server ---

mcp = FastMCP("Notes Server")


@mcp.tool()
def create_note(title: str, content: str) -> str:
    """Create a new note. Returns the note ID."""
    notes = _load_notes()
    note_id = str(uuid.uuid4())[:8]
    notes[note_id] = {
        "title": title,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_notes(notes)
    return f"Note created with ID: {note_id}"


@mcp.tool()
def list_notes() -> str:
    """List all notes showing their ID and title."""
    notes = _load_notes()
    if not notes:
        return "No notes found."
    lines = [f"  [{nid}] {data['title']}" for nid, data in notes.items()]
    return f"Notes ({len(notes)}):\n" + "\n".join(lines)


@mcp.tool()
def get_note(note_id: str) -> str:
    """Get the full content of a note by its ID."""
    notes = _load_notes()
    if note_id not in notes:
        return f"Error: Note '{note_id}' not found."
    note = notes[note_id]
    return f"Title: {note['title']}\nCreated: {note['created_at']}\n\n{note['content']}"


@mcp.tool()
def delete_note(note_id: str) -> str:
    """Delete a note by its ID."""
    notes = _load_notes()
    if note_id not in notes:
        return f"Error: Note '{note_id}' not found."
    title = notes[note_id]["title"]
    del notes[note_id]
    _save_notes(notes)
    return f"Deleted note '{title}' (ID: {note_id})"


# --- Entry point ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notes MCP Server (HTTP transport)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--file", type=str, default="notes.json", help="JSON file for note storage")
    args = parser.parse_args()

    NOTES_FILE = Path(args.file)
    print(f"📝 Notes MCP Server starting on http://localhost:{args.port}/mcp")
    print(f"   Storage: {NOTES_FILE.resolve()}")

    mcp.settings.port = args.port
    mcp.run(transport="streamable-http")
