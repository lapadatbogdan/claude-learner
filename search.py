#!/usr/bin/env python3
"""Search indexed Claude Code sessions."""

import sqlite3
import json
import sys
from pathlib import Path

DB_PATH = Path.home() / "tools" / "claude-learner" / "sessions.db"


def search(query, limit=10):
    """Full-text search across all indexed sessions."""
    if not DB_PATH.exists():
        print("No session index found. Run indexer.py first.")
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT
            m.session_id,
            m.type,
            m.timestamp,
            m.content,
            m.tools_used,
            s.cwd,
            s.project_path,
            rank
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.id
        JOIN sessions s ON m.session_id = s.session_id
        WHERE messages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit))

    results = []
    for row in c.fetchall():
        results.append({
            "session_id": row["session_id"],
            "type": row["type"],
            "timestamp": row["timestamp"],
            "content": row["content"][:500],
            "tools_used": row["tools_used"],
            "cwd": row["cwd"],
            "project": row["project_path"]
        })

    conn.close()
    return results


def search_sessions(query, limit=5):
    """Search and group results by session."""
    results = search(query, limit=50)

    # Group by session
    sessions = {}
    for r in results:
        sid = r["session_id"]
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "cwd": r["cwd"],
                "project": r["project"],
                "messages": []
            }
        sessions[sid]["messages"].append({
            "type": r["type"],
            "timestamp": r["timestamp"],
            "content": r["content"],
            "tools": r["tools_used"]
        })

    # Sort by most recent first
    sorted_sessions = sorted(
        sessions.values(),
        key=lambda s: max(m["timestamp"] for m in s["messages"]),
        reverse=True
    )

    return sorted_sessions[:limit]


def recent_sessions(hours=24, min_messages=3):
    """Get recent sessions with enough activity."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT
            s.session_id,
            s.cwd,
            s.project_path,
            s.message_count,
            s.tool_count,
            s.error_count,
            s.started_at,
            s.file_path
        FROM sessions s
        WHERE s.message_count >= ?
        AND datetime(s.started_at) >= datetime('now', ?)
        ORDER BY s.started_at DESC
    """, (min_messages, f"-{hours} hours"))

    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results


def get_session_transcript(session_id, max_messages=50):
    """Get full transcript of a session."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT type, timestamp, content, tools_used, has_error
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp ASC
        LIMIT ?
    """, (session_id, max_messages))

    messages = [dict(row) for row in c.fetchall()]
    conn.close()
    return messages


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: search.py <query> [limit]")
        sys.exit(1)

    query = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    results = search_sessions(query, limit)
    for session in results:
        print(f"\n--- Session {session['session_id'][:8]} ({session['cwd']}) ---")
        for msg in session["messages"]:
            prefix = "USER" if msg["type"] == "user" else "CLAUDE"
            tools = f" [{msg['tools']}]" if msg["tools"] else ""
            print(f"  [{prefix}]{tools} {msg['content'][:200]}")
