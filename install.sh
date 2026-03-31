#!/bin/bash
# Claude Learner - automated installer
# Usage: curl -fsSL https://raw.githubusercontent.com/lapadatbogdan/claude-learner/main/install.sh | bash

set -e

REPO="https://github.com/lapadatbogdan/claude-learner.git"
INSTALL_DIR="$HOME/tools/claude-learner"
SKILLS_DIR="$HOME/.claude/skills"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[x]${NC} $1"; exit 1; }

echo ""
echo "  Claude Learner - Self-learning loop for Claude Code"
echo "  ---------------------------------------------------"
echo ""

# Check prerequisites
command -v git >/dev/null 2>&1 || fail "git is required but not installed"
command -v python3 >/dev/null 2>&1 || fail "python3 is required but not installed"
command -v claude >/dev/null 2>&1 || fail "Claude Code CLI is required. Install: https://docs.anthropic.com/en/docs/claude-code"

# Check Python version
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    fail "Python 3.10+ required, found $PY_VERSION"
fi
info "Python $PY_VERSION found"

# Check Claude auth
if claude auth status >/dev/null 2>&1; then
    info "Claude Code auth working"
else
    warn "Claude Code auth not configured for background use"
    echo "    Run 'claude' and complete auth setup to enable the cron job"
fi

# Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing installation..."
    cd "$INSTALL_DIR" && git pull --quiet
else
    info "Cloning to $INSTALL_DIR..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --quiet "$REPO" "$INSTALL_DIR"
fi

# Install skills
info "Installing skills..."
mkdir -p "$SKILLS_DIR"
cp -r "$INSTALL_DIR/skills/recall" "$SKILLS_DIR/"
cp -r "$INSTALL_DIR/skills/learn" "$SKILLS_DIR/"

# Run initial index
info "Indexing existing sessions..."
cd "$INSTALL_DIR" && python3 indexer.py 2>/dev/null

# Detect OS and set up scheduled task
OS="$(uname -s)"
case "$OS" in
    Darwin)
        info "Detected macOS - setting up launchd..."
        sed "s/YOUR_USERNAME/$(whoami)/g" "$INSTALL_DIR/com.claude.learner.plist" > "$HOME/Library/LaunchAgents/com.claude.learner.plist"
        launchctl unload "$HOME/Library/LaunchAgents/com.claude.learner.plist" 2>/dev/null || true
        launchctl load "$HOME/Library/LaunchAgents/com.claude.learner.plist"
        info "Cron installed (every 4 hours)"
        ;;
    Linux)
        info "Detected Linux - setting up crontab..."
        CRON_LINE="0 */4 * * * PATH=/usr/local/bin:/usr/bin:/bin HOME=$HOME bash $INSTALL_DIR/run-learner.sh"
        (crontab -l 2>/dev/null | grep -v "claude-learner"; echo "$CRON_LINE") | crontab -
        info "Cron installed (every 4 hours)"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        warn "Windows detected - automatic cron setup not supported from bash"
        echo "    Run this in PowerShell as Administrator:"
        echo ""
        echo '    $action = New-ScheduledTaskAction -Execute "python3" -Argument "analyzer.py 6" -WorkingDirectory "'$INSTALL_DIR'"'
        echo '    $trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 4) -Once -At (Get-Date)'
        echo '    Register-ScheduledTask -TaskName "ClaudeLearner" -Action $action -Trigger $trigger'
        echo ""
        ;;
    *)
        warn "Unknown OS ($OS) - skipping cron setup"
        echo "    Run manually: cd $INSTALL_DIR && python3 analyzer.py 6"
        ;;
esac

echo ""
info "Installation complete!"
echo ""
echo "  Usage:"
echo "    /recall <query>  - search past sessions"
echo "    /learn           - trigger analysis manually"
echo ""
echo "  The learner runs automatically every 4 hours."
echo "  Logs: /tmp/claude-learner.log"
echo ""
