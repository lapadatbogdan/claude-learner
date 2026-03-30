# Claude Learner

Self-learning loop for Claude Code. Analyzes past sessions, extracts learnings, creates/improves skills and memories automatically.

## What it does

1. **Indexes** all Claude Code session transcripts into SQLite FTS5
2. **Analyzes** recent sessions using Claude (via `claude -p`)
3. **Creates** new skills, memories, and patterns from findings
4. **Improves** existing skills when issues are detected (routing, missing steps, workarounds)
5. **Searches** past sessions for context (`/recall`)

## Architecture

```
Cron (every 4h)
    |
    v
indexer.py --> SQLite FTS5 (sessions.db)
    |
    v
analyzer.py --> claude -p --model haiku
    |
    v
Apply findings:
  - memory_update --> ~/.claude/projects/.../memory/*.md
  - skill_proposal --> ~/.claude/skills/<name>/SKILL.md
  - pattern --> feedback memory
  - improvement --> patch existing skill/memory
```

## Components

| File | Purpose |
|------|---------|
| `indexer.py` | Parse JSONL session files, index into SQLite FTS5 |
| `search.py` | Full-text search across indexed sessions |
| `analyzer.py` | Analyze sessions with LLM, apply findings automatically |
| `run-learner.sh` | Cron wrapper script |

## Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/recall` | "search sessions", "am mai facut asta" | Search past sessions |
| `/learn` | "ce ai invatat", "self-improve" | Trigger analysis manually |

## Setup

1. Clone this repo to `~/tools/claude-learner/`
2. Copy skills to `~/.claude/skills/recall/` and `~/.claude/skills/learn/`
3. Run `claude setup-token` for persistent auth
4. Install the launchd plist:
   ```bash
   cp com.claude.learner.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.claude.learner.plist
   ```

## Self-improvement loop

The analyzer detects:
- **Missed skills** - user did something manually that a skill could handle
- **Wrong skills** - skill triggered but was incorrect
- **Language mismatch** - Romanian prompts not matching English triggers
- **Failed workflows** - skill used but errors followed

When detected, it patches the skill's description/triggers automatically, improving routing over time.

## Requirements

- Claude Code CLI with `setup-token` configured
- Python 3.10+
- macOS (for launchd cron)
