#!/bin/bash
# Claude Learner - periodic session analysis
# Runs indexer + analyzer, logs output

LOG_FILE="/tmp/claude-learner.log"
LEARNER_DIR="$HOME/tools/claude-learner"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting learner run" >> "$LOG_FILE"

cd "$LEARNER_DIR" || exit 1

# Index new sessions
python3 indexer.py >> "$LOG_FILE" 2>&1

# Analyze last 6 hours of sessions
python3 analyzer.py 6 >> "$LOG_FILE" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') - Learner run complete" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"
