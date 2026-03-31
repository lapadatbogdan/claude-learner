#!/bin/bash
# Claude Learner - periodic session analysis
# Runs analyzer (which handles indexing internally), logs output

LOG_FILE="/tmp/claude-learner.log"
LEARNER_DIR="$HOME/tools/claude-learner"

# Prevent concurrent runs
exec 9>/tmp/claude-learner.lock
flock -n 9 || {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Another instance running, skipping" >> "$LOG_FILE"
    exit 0
}

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting learner run" >> "$LOG_FILE"

cd "$LEARNER_DIR" || exit 1

# Analyze last 6 hours of sessions (indexer runs internally)
python3 analyzer.py 6 >> "$LOG_FILE" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') - Learner run complete" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"
