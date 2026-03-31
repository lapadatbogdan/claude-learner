---
name: learn
description: Review pending learning candidates and approve/skip/delete. Triggers on "/learn", "ce ai invatat", "analizeaza sesiunile", "self-improve", "learn from sessions".
---

# Learn - Review Pending Candidates

Review candidates detected by the background learner and decide which to apply.

## Step 1: Load pending candidates

```bash
cat ~/tools/claude-learner/pending_learnings.json 2>/dev/null || echo "[]"
```

If the result is `[]` or the file was missing, respond with: "Nothing pending." and stop.

## Step 2: For each candidate, display summary and ask [a]pprove / [s]kip / [d]elete

For each candidate, display a human-readable summary based on its `type` field:

- `skill_proposal`:
  ```
  [skill_proposal] Name: <name> | Sessions: <session_count>
  Description: <description>
  ```

- `memory_update`:
  ```
  [memory_update] Category: <category> | Title: <title>
  Content: <first 150 chars of content>
  ```

- `pattern`:
  ```
  [pattern] <description>
  Recommendation: <recommendation>
  ```

- `improvement`:
  ```
  [improvement] Target: <target_type>/<target_name>
  Problem: <problem>
  Fix: <fix>
  ```

After displaying the summary, ask:
```
[a]pprove / [s]kip / [d]elete?
```

Wait for the user's response before moving to the next candidate. Collect decisions:
- `a` or `approve` → approved list
- `s` or `skip` → skipped list
- `d` or `delete` → deleted list

## Step 3: Process approved candidates

Candidates in `pending_learnings.json` are already enriched by Haiku (during detection). For each approved candidate, just apply it directly — no additional API call needed.

1. Write the candidate's full JSON to `/tmp/learner_candidate.json` using the Write tool.

2. Apply it:

```bash
python3 -c "
import json, subprocess
from pathlib import Path
c = json.loads(Path('/tmp/learner_candidate.json').read_text())
r = subprocess.run(
    ['python3', str(Path.home() / 'tools/claude-learner/analyzer.py'), '--apply-json', json.dumps(c)],
    capture_output=True, text=True
)
print(r.stdout)
if r.returncode != 0:
    print('FAILED:', r.stderr)
"
```

If a candidate fails to apply, note the error, continue processing remaining approved candidates, and include the failure in the Step 5 report.

## Step 4: Update pending_learnings.json

Rewrite `~/tools/claude-learner/pending_learnings.json` with only the skipped candidates (empty array if none skipped). Use the Write tool.

## Step 5: Report

Summarize:
- How many **approved** (and whether each succeeded)
- How many **skipped** (kept for next review)
- How many **deleted** (discarded)
