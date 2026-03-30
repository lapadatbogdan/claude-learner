#!/usr/bin/env python3
"""Index Claude Code sessions into SQLite FTS5 for search."""

import json
import sqlite3
import os
import glob
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path.home() / "tools" / "claude-learner" / "sessions.db"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
SESSIONS_DIR = Path.home() / ".claude" / "sessions"


def init_db():
    """Create database and FTS5 tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            project_path TEXT,
            cwd TEXT,
            started_at TEXT,
            indexed_at TEXT,
            message_count INTEGER,
            tool_count INTEGER,
            error_count INTEGER,
            file_path TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            uuid TEXT UNIQUE,
            type TEXT,
            timestamp TEXT,
            content TEXT,
            tools_used TEXT,
            has_error INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    """)

    # FTS5 virtual table for full-text search
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            session_id,
            content,
            tools_used,
            content=messages,
            content_rowid=id
        )
    """)

    # Triggers to keep FTS in sync
    c.execute("""
        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, session_id, content, tools_used)
            VALUES (new.id, new.session_id, new.content, new.tools_used);
        END
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS index_state (
            file_path TEXT PRIMARY KEY,
            last_size INTEGER,
            last_indexed TEXT
        )
    """)

    conn.commit()
    return conn


def extract_content(message_data):
    """Extract readable content from a message."""
    msg = message_data.get("message", {})
    content = msg.get("content", "")

    if isinstance(content, str):
        return content, [], False

    if isinstance(content, list):
        texts = []
        tools = []
        has_error = False

        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "text":
                    texts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tool_name = block.get("name", "")
                    tools.append(tool_name)
                elif btype == "tool_result":
                    if block.get("is_error"):
                        has_error = True
                    # Extract text from tool results
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        texts.append(result_content[:500])  # Truncate large results
                    elif isinstance(result_content, list):
                        for rc in result_content:
                            if isinstance(rc, dict) and rc.get("type") == "text":
                                texts.append(rc.get("text", "")[:500])

        return "\n".join(texts), tools, has_error

    return str(content)[:1000], [], False


def index_session_file(conn, file_path):
    """Index a single JSONL session file."""
    c = conn.cursor()

    # Check if already indexed at this size
    file_size = os.path.getsize(file_path)
    c.execute("SELECT last_size FROM index_state WHERE file_path = ?", (file_path,))
    row = c.fetchone()
    if row and row[0] == file_size:
        return 0  # Already indexed, no changes

    session_id = None
    cwd = None
    message_count = 0
    tool_count = 0
    error_count = 0
    messages_to_insert = []

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")
            if msg_type not in ("user", "assistant"):
                continue

            if not session_id:
                session_id = data.get("sessionId", Path(file_path).stem)
                cwd = data.get("cwd", "")

            uuid = data.get("uuid", "")
            timestamp = data.get("timestamp", "")
            content, tools, has_error = extract_content(data)

            if not content.strip():
                continue

            message_count += 1
            tool_count += len(tools)
            if has_error:
                error_count += 1

            messages_to_insert.append((
                session_id, uuid, msg_type, timestamp,
                content[:5000],  # Truncate very long content
                ",".join(tools) if tools else "",
                1 if has_error else 0
            ))

    if not session_id or not messages_to_insert:
        return 0

    # Get project path from file location
    project_path = str(Path(file_path).parent.name)

    # Upsert session
    c.execute("""
        INSERT INTO sessions (session_id, project_path, cwd, started_at, indexed_at, message_count, tool_count, error_count, file_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            indexed_at = excluded.indexed_at,
            message_count = excluded.message_count,
            tool_count = excluded.tool_count,
            error_count = excluded.error_count
    """, (
        session_id, project_path, cwd,
        messages_to_insert[0][3] if messages_to_insert else "",
        datetime.now(timezone.utc).isoformat(),
        message_count, tool_count, error_count, file_path
    ))

    # Insert messages (skip duplicates)
    for msg in messages_to_insert:
        try:
            c.execute("""
                INSERT OR IGNORE INTO messages (session_id, uuid, type, timestamp, content, tools_used, has_error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, msg)
        except sqlite3.IntegrityError:
            pass

    # Update index state
    c.execute("""
        INSERT INTO index_state (file_path, last_size, last_indexed)
        VALUES (?, ?, ?)
        ON CONFLICT(file_path) DO UPDATE SET
            last_size = excluded.last_size,
            last_indexed = excluded.last_indexed
    """, (file_path, file_size, datetime.now(timezone.utc).isoformat()))

    conn.commit()
    return len(messages_to_insert)


def index_all():
    """Index all session files."""
    conn = init_db()
    total_new = 0

    # Find all JSONL files in projects
    for jsonl_file in glob.glob(str(PROJECTS_DIR / "**" / "*.jsonl"), recursive=True):
        # Skip subagent files (too noisy)
        if "/subagents/" in jsonl_file:
            continue
        # Skip very small files
        if os.path.getsize(jsonl_file) < 100:
            continue

        try:
            new_msgs = index_session_file(conn, jsonl_file)
            if new_msgs > 0:
                total_new += new_msgs
        except Exception as e:
            print(f"Error indexing {jsonl_file}: {e}")

    conn.close()
    return total_new


def get_stats():
    """Get index statistics."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sessions")
    sessions = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages")
    messages = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE has_error = 1")
    errors = c.fetchone()[0]
    conn.close()
    return {"sessions": sessions, "messages": messages, "errors": errors}


if __name__ == "__main__":
    new = index_all()
    stats = get_stats()
    print(f"Indexed {new} new messages. Total: {stats['sessions']} sessions, {stats['messages']} messages, {stats['errors']} errors.")
