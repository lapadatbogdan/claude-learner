---
name: learn
description: Analyze recent sessions and extract learnings (skills, memories, patterns). Triggers on "/learn", "ce ai invatat", "analizeaza sesiunile", "self-improve", "learn from sessions".
---

# Learn - Session Analysis

Analyze recent Claude Code sessions and extract actionable learnings.

## Step 1: Index new sessions
```bash
cd ~/tools/claude-learner && python3 indexer.py
```

## Step 2: Run analysis
```bash
cd ~/tools/claude-learner && python3 analyzer.py 48
```
The argument is hours to look back (default 24, use 48 for broader analysis).

## Step 3: Review pending learnings
Read `~/tools/claude-learner/pending_learnings.json` if it exists.

For each finding:
- **skill_proposal**: Ask the user if they want to create the skill. If yes, create SKILL.md in `~/.claude/skills/<name>/`
- **memory_update**: Create or update the appropriate memory file in the memory system
- **pattern**: Report to user, suggest action

## Step 4: Clean up
After processing, clear the pending file:
```bash
rm ~/tools/claude-learner/pending_learnings.json 2>/dev/null
```

## Step 5: Report
Summarize what was found and what actions were taken.
