#!/usr/bin/env python3
"""Analyze recent Claude Code sessions and extract learnings.

Runs periodically via cron. Identifies:
- Complex problems solved (many tool calls, errors overcome)
- User corrections (patterns to remember)
- Repeated workflows (candidates for skills)
- Knowledge gaps (things looked up multiple times)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from indexer import index_all, get_stats
from search import recent_sessions, get_session_transcript

LEARNER_DIR = Path.home() / "tools" / "claude-learner"
PENDING_FILE = LEARNER_DIR / "pending_learnings.json"

def _find_memory_dir():
    """Find the memory directory for the current user's default project."""
    projects_dir = Path.home() / ".claude" / "projects"
    if projects_dir.exists():
        # Find project dir matching home path
        home_slug = "-" + str(Path.home()).replace("/", "-")
        candidate = projects_dir / home_slug / "memory"
        if candidate.exists():
            return candidate
        # Fallback: first project with a memory dir
        for d in projects_dir.iterdir():
            mem = d / "memory"
            if mem.exists():
                return mem
    return projects_dir / "memory"

MEMORY_DIR = _find_memory_dir()
STATE_FILE = LEARNER_DIR / "analyzer_state.json"
ANALYSIS_LOG = LEARNER_DIR / "analysis_log.jsonl"


def load_state():
    """Load last analysis state."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_run": None}


def save_state(state):
    """Save analysis state."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def build_session_summary(session_id, messages):
    """Build a compact summary of a session for LLM analysis."""
    lines = []
    for msg in messages:
        prefix = "USER" if msg["type"] == "user" else "CLAUDE"
        tools = f" [tools: {msg['tools_used']}]" if msg["tools_used"] else ""
        error = " [ERROR]" if msg["has_error"] else ""
        content = msg["content"][:300]
        lines.append(f"{prefix}{tools}{error}: {content}")
    return "\n".join(lines)


def get_existing_context():
    """Get list of existing skills and memories for improvement context."""
    skills = []
    skills_dir = Path.home() / ".claude" / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                with open(skill_file) as f:
                    content = f.read()
                # Extract description from frontmatter
                desc = ""
                if "---" in content:
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        for line in parts[1].strip().split("\n"):
                            if line.startswith("description:"):
                                desc = line[12:].strip()
                skills.append(f"  - {skill_dir.name}: {desc[:200]}")

    memories = []
    if MEMORY_DIR.exists():
        for md_file in sorted(MEMORY_DIR.glob("*.md")):
            if md_file.name == "MEMORY.md":
                continue
            memories.append(f"  - {md_file.name}")

    return "\n".join(skills[:30]), "\n".join(memories[:40])


def analyze_with_claude(sessions_summaries):
    """Send session summaries to Claude for analysis."""
    skills_ctx, memories_ctx = get_existing_context()

    prompt = f"""Analyze these recent Claude Code session transcripts. For each interesting finding, output a JSON object on its own line.

Types of findings:
1. "skill_proposal" - a workflow that was done manually but could be automated as a skill
2. "memory_update" - something learned that should be remembered for future sessions
3. "pattern" - a repeated behavior pattern (good or bad)
4. "improvement" - an existing skill or memory that needs to be updated/fixed based on what happened in the session (e.g. a skill was used but missed a step, a memory is outdated, a pattern workaround should be added)

Output format (one JSON per line, no other text):
{{"type": "skill_proposal", "name": "skill-name", "description": "what it does", "trigger": "when to use it", "steps": ["step1", "step2"]}}
{{"type": "memory_update", "category": "feedback|project|user|reference", "title": "short title", "content": "what to remember", "why": "why this matters"}}
{{"type": "pattern", "description": "what pattern was observed", "frequency": "how often", "recommendation": "what to do about it"}}
{{"type": "improvement", "target_type": "skill|memory", "target_name": "exact filename or skill name", "problem": "what went wrong or is missing", "fix": "what to add/change/remove", "new_content": "the improved full content to replace the file (optional, for small files)"}}

IMPORTANT for improvements:
- Look for sessions where a skill was invoked but errors followed, or user had to correct the approach
- Look for memories that were relevant but incomplete or wrong
- Look for workarounds that should be baked into existing skills
- Prefer improving existing skills/memories over creating new ones

SKILL ROUTING - pay special attention to:
- MISSED SKILL: user asked for something and Claude did it manually, but a relevant skill existed. The skill's description/triggers need better keywords. Output an improvement to add the user's phrasing as a trigger.
- WRONG SKILL: a skill was invoked but it was the wrong one. The description needs to be more specific to avoid false matches.
- AMBIGUOUS: two skills could match. Add disambiguation keywords to both descriptions.
- LANGUAGE MISMATCH: user spoke Romanian but triggers are in English (or vice versa). Add bilingual triggers.
When fixing skill routing, output an improvement with target_type="skill" and include the full updated SKILL.md frontmatter in new_content (keep the body, just fix the description/triggers line).

Existing skills:
{skills_ctx}

Existing memories:
{memories_ctx}

Only output findings that are genuinely useful. Skip trivial things. Prefer improvements over new entries when possible.
If there's nothing interesting, output: {{"type": "none"}}

Sessions:
{sessions_summaries}"""

    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "haiku", prompt],
            capture_output=True, text=True, timeout=120,
            env={k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
        )
        output = result.stdout.strip()
        # Debug: save raw output
        debug_file = LEARNER_DIR / "last_analysis_raw.txt"
        with open(debug_file, "w") as df:
            df.write(output)
        return output
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"Error running Claude analysis: {e}")
        return None


def process_findings(findings_text):
    """Parse and process LLM findings."""
    if not findings_text:
        return []

    findings = []
    # Try to extract JSON objects from the text, even if surrounded by markdown
    import re
    # Find all JSON-like objects in the text
    json_pattern = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}')
    matches = json_pattern.findall(findings_text)

    for match in matches:
        try:
            finding = json.loads(match)
            if finding.get("type") and finding.get("type") != "none":
                findings.append(finding)
        except json.JSONDecodeError:
            continue

    # Also try line-by-line for clean JSONL output
    if not findings:
        for line in findings_text.strip().split("\n"):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                finding = json.loads(line)
                if finding.get("type") != "none":
                    findings.append(finding)
            except json.JSONDecodeError:
                continue

    return findings


def log_analysis(findings, session_ids):
    """Log analysis results."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sessions_analyzed": session_ids,
        "findings_count": len(findings),
        "findings": findings
    }
    with open(ANALYSIS_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def slugify(text):
    """Create a filesystem-safe slug from text."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    slug = slug.strip('_')
    return slug[:60]


def apply_memory_update(finding):
    """Write a memory file and update MEMORY.md index."""
    category = finding.get("category", "project")
    title = finding.get("title", "untitled")
    content = finding.get("content", "")
    why = finding.get("why", "")

    slug = f"{category}_{slugify(title)}"
    filename = f"{slug}.md"
    filepath = MEMORY_DIR / filename

    # Don't overwrite existing memories
    if filepath.exists():
        print(f"  Memory already exists: {filename}, skipping")
        return None

    # Write memory file
    body = content
    if why:
        body += f"\n\n**Why:** {why}"
    if category in ("feedback", "project"):
        body += f"\n\n**How to apply:** Use this context when relevant tasks arise."

    memory_content = f"""---
name: {slug}
description: {title}
type: {category}
---

{body}
"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(memory_content)

    # Append to MEMORY.md
    memory_index = MEMORY_DIR / "MEMORY.md"
    one_liner = f"- [{filename}]({filename}) — {title}"
    with open(memory_index, "r") as f:
        existing = f.read()

    # Don't add duplicate entries
    if filename in existing:
        print(f"  Already in MEMORY.md: {filename}")
        return filename

    with open(memory_index, "a") as f:
        f.write(f"\n{one_liner}")

    print(f"  Saved memory: {filename}")
    return filename


def apply_skill_proposal(finding):
    """Create a new skill from a proposal."""
    name = finding.get("name", "")
    if not name:
        return None

    safe_name = slugify(name)
    skill_dir = Path.home() / ".claude" / "skills" / safe_name
    skill_file = skill_dir / "SKILL.md"

    # Don't overwrite existing skills
    if skill_file.exists():
        print(f"  Skill already exists: {safe_name}, skipping")
        return None

    description = finding.get("description", "")
    trigger = finding.get("trigger", "")
    steps = finding.get("steps", [])

    steps_md = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))

    skill_content = f"""---
name: {safe_name}
description: {description}. Triggers on "/{safe_name}" or related keywords.
---

# {safe_name}

{description}

## When to use
{trigger}

## Steps
{steps_md}
"""
    skill_dir.mkdir(parents=True, exist_ok=True)
    with open(skill_file, "w") as f:
        f.write(skill_content)

    print(f"  Created skill: {safe_name}")
    return safe_name


def apply_pattern(finding):
    """Save a pattern as a feedback memory."""
    desc = finding.get("description", "")
    recommendation = finding.get("recommendation", "")
    slug = f"pattern_{slugify(desc)}"
    filename = f"{slug}.md"
    filepath = MEMORY_DIR / filename

    if filepath.exists():
        print(f"  Pattern already saved: {filename}, skipping")
        return None

    memory_content = f"""---
name: {slug}
description: Observed pattern - {desc[:80]}
type: feedback
---

{desc}

**Frequency:** {finding.get('frequency', 'observed')}

**How to apply:** {recommendation}
"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(memory_content)

    # Append to MEMORY.md
    memory_index = MEMORY_DIR / "MEMORY.md"
    with open(memory_index, "r") as f:
        existing = f.read()
    if filename not in existing:
        with open(memory_index, "a") as f:
            f.write(f"\n- [{filename}]({filename}) — Pattern: {desc[:60]}")

    print(f"  Saved pattern: {filename}")
    return filename


def apply_improvement(finding):
    """Improve an existing skill or memory."""
    target_type = finding.get("target_type", "")
    target_name = finding.get("target_name", "")
    problem = finding.get("problem", "")
    fix = finding.get("fix", "")
    new_content = finding.get("new_content", "")

    if not target_name or not fix:
        return None

    if target_type == "skill":
        skill_file = Path.home() / ".claude" / "skills" / target_name / "SKILL.md"
        if not skill_file.exists():
            print(f"  Skill not found: {target_name}, skipping improvement")
            return None

        if new_content:
            # Full replacement
            with open(skill_file, "w") as f:
                f.write(new_content)
            print(f"  Improved skill (full rewrite): {target_name}")
        else:
            # Append fix as a new section
            with open(skill_file, "a") as f:
                f.write(f"\n\n## Known Issues & Fixes (auto-learned)\n")
                f.write(f"**Problem:** {problem}\n")
                f.write(f"**Fix:** {fix}\n")
            print(f"  Improved skill (appended fix): {target_name}")

        # Log the improvement
        improvements_log = LEARNER_DIR / "improvements_log.jsonl"
        with open(improvements_log, "a") as f:
            f.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "target_type": target_type,
                "target_name": target_name,
                "problem": problem,
                "fix": fix
            }) + "\n")

        return target_name

    elif target_type == "memory":
        # Find memory file
        memory_file = MEMORY_DIR / target_name
        if not memory_file.exists():
            # Try matching by partial name
            matches = list(MEMORY_DIR.glob(f"*{target_name}*"))
            if matches:
                memory_file = matches[0]
            else:
                print(f"  Memory not found: {target_name}, skipping improvement")
                return None

        if new_content:
            with open(memory_file, "w") as f:
                f.write(new_content)
            print(f"  Improved memory (full rewrite): {memory_file.name}")
        else:
            # Append update
            with open(memory_file, "a") as f:
                f.write(f"\n\n## Update (auto-learned {datetime.now(timezone.utc).strftime('%Y-%m-%d')})\n")
                f.write(f"**Issue:** {problem}\n")
                f.write(f"**Update:** {fix}\n")
            print(f"  Improved memory (appended): {memory_file.name}")

        # Log
        improvements_log = LEARNER_DIR / "improvements_log.jsonl"
        with open(improvements_log, "a") as f:
            f.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "target_type": target_type,
                "target_name": str(memory_file.name),
                "problem": problem,
                "fix": fix
            }) + "\n")

        return str(memory_file.name)

    return None


def apply_findings(findings):
    """Apply all findings automatically."""
    applied = {"memories": 0, "skills": 0, "patterns": 0, "improvements": 0}

    for finding in findings:
        ftype = finding.get("type", "")
        try:
            if ftype == "memory_update":
                if apply_memory_update(finding):
                    applied["memories"] += 1
            elif ftype == "skill_proposal":
                if apply_skill_proposal(finding):
                    applied["skills"] += 1
            elif ftype == "pattern":
                if apply_pattern(finding):
                    applied["patterns"] += 1
            elif ftype == "improvement":
                if apply_improvement(finding):
                    applied["improvements"] += 1
            elif ftype == "feedback":
                finding["category"] = "feedback"
                if apply_memory_update(finding):
                    applied["memories"] += 1
        except Exception as e:
            print(f"  Error applying {ftype}: {e}")

    return applied


# Used by the manual /learn skill path (not called from the cron run() path).
def notify_results(findings, applied):
    """Print summary and save applied results."""
    if not findings:
        return

    summary_lines = [f"Claude Learner - {len(findings)} findings, applied: {applied['memories']}M {applied['skills']}S {applied['patterns']}P {applied['improvements']}I\n"]
    for f in findings[:8]:
        ftype = f.get("type", "unknown")
        if ftype == "skill_proposal":
            summary_lines.append(f"  +Skill: {f.get('name', '?')} - {f.get('description', '?')[:80]}")
        elif ftype in ("memory_update", "feedback"):
            summary_lines.append(f"  +Memory: {f.get('title', '?')}")
        elif ftype == "pattern":
            summary_lines.append(f"  +Pattern: {f.get('description', '?')[:80]}")
        elif ftype == "improvement":
            summary_lines.append(f"  ~Improved {f.get('target_type', '?')}: {f.get('target_name', '?')} - {f.get('fix', '?')[:60]}")

    print("\n".join(summary_lines))


def run(hours=24):
    """Main analysis loop."""
    # Step 1: Index new sessions
    print("Indexing sessions...")
    new_msgs = index_all()
    stats = get_stats()
    print(f"Index: +{new_msgs} messages. Total: {stats['sessions']} sessions, {stats['messages']} messages.")

    # Step 2: Find sessions since last run
    state = load_state()
    last_run = state.get("last_run")

    if last_run:
        # Convert last_run ISO timestamp to hours-ago for recent_sessions query
        last_run_dt = datetime.fromisoformat(last_run)
        delta = datetime.now(timezone.utc) - last_run_dt
        hours_since = max(1, int(delta.total_seconds() / 3600) + 1)
        recent = recent_sessions(hours=hours_since, min_messages=5)
        # Filter to only sessions started after last_run
        to_analyze = [s for s in recent if s["started_at"] > last_run]
    else:
        recent = recent_sessions(hours=hours, min_messages=5)
        to_analyze = recent

    if not to_analyze:
        print("No new sessions to analyze.")
        save_state({"last_run": datetime.now(timezone.utc).isoformat()})
        return

    print(f"Found {len(to_analyze)} sessions to analyze...")

    # Step 3: Build summaries
    all_summaries = []
    session_ids = []
    for session in to_analyze[:5]:  # Max 5 sessions per run
        sid = session["session_id"]
        transcript = get_session_transcript(sid, max_messages=30)
        if transcript:
            summary = build_session_summary(sid, transcript)
            all_summaries.append(f"\n=== Session {sid[:8]} (cwd: {session['cwd']}, tools: {session['tool_count']}, errors: {session['error_count']}) ===\n{summary}")
            session_ids.append(sid)

    if not all_summaries:
        print("No transcripts to analyze.")
        return

    combined = "\n".join(all_summaries)
    # Truncate to ~15k chars to stay within limits
    if len(combined) > 15000:
        combined = combined[:15000] + "\n... (truncated)"

    # Step 4: Analyze with Claude
    print("Running Claude analysis...")
    findings_text = analyze_with_claude(combined)
    findings = process_findings(findings_text)

    print(f"Found {len(findings)} learnings.")

    # Step 5: Save findings to pending_learnings.json for human review
    if findings:
        existing_pending = []
        if PENDING_FILE.exists():
            try:
                with open(PENDING_FILE) as f:
                    existing_pending = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing_pending = []

        existing_pending.extend(findings)
        PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PENDING_FILE, "w") as f:
            json.dump(existing_pending, f, indent=2)

        # Step 6: Log and notify
        log_analysis(findings, session_ids)
        print(f"Saved {len(findings)} findings to pending_learnings.json.")
        print(f"Run /learn in Claude Code to review and apply.")

    # Step 7: Update state
    save_state({"last_run": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--apply-json":
        if len(sys.argv) < 3:
            print("Usage: analyzer.py --apply-json '<json_string>'")
            sys.exit(1)
        try:
            candidate = json.loads(sys.argv[2])
        except json.JSONDecodeError as e:
            print(f"Invalid JSON argument: {e}")
            sys.exit(1)
        applied = apply_findings([candidate])
        print(f"Applied: {applied}")
        sys.exit(0 if sum(applied.values()) > 0 else 1)
    else:
        hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
        run(hours=hours)
