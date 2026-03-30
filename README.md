# Claude Learner

Self-learning loop for Claude Code. Analyzes past sessions, extracts learnings, creates/improves skills and memories automatically.

Inspired by [Hermes Agent](https://github.com/NousResearch/hermes-agent)'s self-learning architecture, adapted to work on top of Claude Code's existing skill/memory system.

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

## Quick install

```bash
curl -fsSL https://raw.githubusercontent.com/lapadatbogdan/claude-learner/main/install.sh | bash
```

This will clone the repo, install skills, index your sessions, and set up the cron job automatically. Works on macOS and Linux. Windows prints PowerShell instructions.

To uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/lapadatbogdan/claude-learner/main/uninstall.sh | bash
```

## Manual installation

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and working
- Python 3.10+
- macOS (for launchd cron) or Linux (adapt to systemd/crontab)
- A Claude Code subscription (Max recommended for heavy use)

### Step 1: Clone the repo

```bash
git clone https://github.com/lapadatbogdan/claude-learner.git ~/tools/claude-learner
```

### Step 2: Set up persistent auth

Claude Learner runs `claude -p` in the background. For this to work outside an active session, you need a persistent token:

```bash
claude setup-token
```

This opens a browser flow - authenticate once and the token is stored in your system keychain.

Verify it works:

```bash
claude -p "say hello"
```

### Step 3: Install skills

Copy the skills so Claude Code can find them:

```bash
cp -r ~/tools/claude-learner/skills/recall ~/.claude/skills/
cp -r ~/tools/claude-learner/skills/learn ~/.claude/skills/
```

Verify they're available - start a Claude Code session and type `/recall` or `/learn`.

### Step 4: Run the initial index

```bash
cd ~/tools/claude-learner && python3 indexer.py
```

This indexes all your existing Claude Code sessions. First run may take a few seconds depending on how many sessions you have.

### Step 5: Test the analyzer

```bash
cd ~/tools/claude-learner && python3 analyzer.py 168
```

The argument is hours to look back (168 = 7 days). This will:
- Index any new sessions
- Send summaries to Claude Haiku for analysis
- Automatically create memories/skills/patterns from findings
- Print what it found and applied

### Step 6: Set up scheduled runs

Pick your platform:

<details>
<summary><strong>macOS (launchd)</strong></summary>

Edit the plist template with your username and install it:

```bash
sed "s/YOUR_USERNAME/$(whoami)/g" ~/tools/claude-learner/com.claude.learner.plist > ~/Library/LaunchAgents/com.claude.learner.plist
launchctl load ~/Library/LaunchAgents/com.claude.learner.plist
```

Verify:

```bash
launchctl list | grep claude.learner
```

To uninstall:

```bash
launchctl unload ~/Library/LaunchAgents/com.claude.learner.plist
rm ~/Library/LaunchAgents/com.claude.learner.plist
```

</details>

<details>
<summary><strong>Linux (crontab)</strong></summary>

```bash
crontab -e
```

Add this line:

```
0 */4 * * * cd ~/tools/claude-learner && python3 analyzer.py 6 >> /tmp/claude-learner.log 2>&1
```

Verify:

```bash
crontab -l | grep claude-learner
```

To uninstall:

```bash
crontab -e
# Remove the claude-learner line
```

</details>

<details>
<summary><strong>Windows (Task Scheduler)</strong></summary>

Open PowerShell as Administrator:

```powershell
$action = New-ScheduledTaskAction -Execute "python3" -Argument "analyzer.py 6" -WorkingDirectory "$env:USERPROFILE\tools\claude-learner"
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 4) -Once -At (Get-Date)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Register-ScheduledTask -TaskName "ClaudeLearner" -Action $action -Trigger $trigger -Settings $settings -Description "Claude Code self-learning loop"
```

Verify:

```powershell
Get-ScheduledTask -TaskName "ClaudeLearner"
```

To uninstall:

```powershell
Unregister-ScheduledTask -TaskName "ClaudeLearner" -Confirm:$false
```

Note: On Windows, Claude Code sessions are stored in `%USERPROFILE%\.claude\projects\`. The indexer handles Windows paths automatically.

</details>

The scheduled task runs every 4 hours and analyzes the last 6 hours of sessions.

### Uninstall

1. Remove the scheduled task (see platform-specific instructions above)
2. Remove skills and learner:

```bash
rm -rf ~/.claude/skills/recall ~/.claude/skills/learn
rm -rf ~/tools/claude-learner
```

## Usage

### Automatic (cron)

Once installed, the learner runs every 4 hours in the background. It:
1. Indexes new sessions
2. Analyzes them with Haiku
3. Creates/improves skills and memories
4. Logs everything to `analysis_log.jsonl` and `improvements_log.jsonl`

### Manual

From any Claude Code session:

- `/learn` - trigger analysis on demand
- `/recall <query>` - search past sessions (e.g., `/recall YouTube upload flow`)

### From terminal

```bash
# Index sessions
cd ~/tools/claude-learner && python3 indexer.py

# Analyze last N hours
cd ~/tools/claude-learner && python3 analyzer.py 48

# Search sessions
cd ~/tools/claude-learner && python3 search.py "your query" 5
```

## Components

| File | Purpose |
|------|---------|
| `indexer.py` | Parse JSONL session files, index into SQLite FTS5 |
| `search.py` | Full-text search across indexed sessions |
| `analyzer.py` | Analyze sessions with LLM, apply findings automatically |
| `run-learner.sh` | Cron wrapper script |

## Self-improvement loop

The analyzer detects and fixes:

- **Missed skills** - user did something manually that a skill could handle. Adds the user's phrasing as a trigger to the relevant skill.
- **Wrong skills** - skill triggered but was incorrect. Makes the description more specific.
- **Language mismatch** - prompts in one language not matching triggers in another. Adds bilingual triggers.
- **Failed workflows** - skill used but errors followed. Appends "Known Issues & Fixes" section to the skill.

All improvements are logged in `improvements_log.jsonl` for traceability.

## How it works under the hood

Claude Code stores every conversation as JSONL files in `~/.claude/projects/`. Each message (user or assistant) is a JSON line with content, timestamps, tool calls, and errors.

The indexer reads these files and builds a SQLite database with FTS5 full-text search. The analyzer picks recent sessions, builds compact summaries, and sends them to Claude Haiku via `claude -p`. Haiku returns structured JSON findings which are automatically applied:

| Finding type | Action |
|---|---|
| `memory_update` | Creates `.md` file in memory dir, updates `MEMORY.md` index |
| `skill_proposal` | Creates `SKILL.md` in `~/.claude/skills/<name>/` |
| `pattern` | Saved as feedback memory |
| `improvement` | Patches existing skill or memory file |

## Cost

Using Claude Code subscription (not API):
- ~1 Haiku call per run (small context, fast)
- 6 runs/day = negligible vs normal Claude Code usage
- On Max plan: effectively free

## License

MIT
