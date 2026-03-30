---
name: recall
description: Search past Claude Code sessions for context, solutions, and patterns. Triggers on "/recall", "cauta in sesiuni", "am mai facut asta", "remember when", "search sessions".
---

# Recall - Session Search

Search through indexed past Claude Code sessions to find relevant context, solutions, and patterns.

## How it works
Uses SQLite FTS5 full-text search over all indexed session transcripts.

## Step 1: Ensure index is fresh
Run the indexer to pick up any new sessions:
```bash
cd ~/tools/claude-learner && python3 indexer.py
```

## Step 2: Search
Run the search with the user's query:
```bash
cd ~/tools/claude-learner && python3 search.py "<user query>" 5
```

## Step 3: Present results
Show the user:
- Which sessions matched
- Relevant excerpts from conversations
- What tools were used
- When it happened

If the user needs more detail from a specific session, read the full JSONL file directly.

## Step 4: Check pending learnings
If `~/tools/claude-learner/pending_learnings.json` exists, review and apply relevant learnings (create memories/skills as appropriate), then clear the file.
