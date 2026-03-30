#!/bin/bash
# Claude Learner - uninstaller

set -e

INSTALL_DIR="$HOME/tools/claude-learner"
SKILLS_DIR="$HOME/.claude/skills"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

info() { echo -e "${GREEN}[+]${NC} $1"; }

echo ""
echo "  Claude Learner - Uninstaller"
echo "  ----------------------------"
echo ""

# Remove scheduled task
OS="$(uname -s)"
case "$OS" in
    Darwin)
        if [ -f "$HOME/Library/LaunchAgents/com.claude.learner.plist" ]; then
            launchctl unload "$HOME/Library/LaunchAgents/com.claude.learner.plist" 2>/dev/null || true
            rm "$HOME/Library/LaunchAgents/com.claude.learner.plist"
            info "Removed launchd job"
        fi
        ;;
    Linux)
        if crontab -l 2>/dev/null | grep -q "claude-learner"; then
            crontab -l 2>/dev/null | grep -v "claude-learner" | crontab -
            info "Removed crontab entry"
        fi
        ;;
esac

# Remove skills
if [ -d "$SKILLS_DIR/recall" ]; then
    rm -rf "$SKILLS_DIR/recall"
    info "Removed /recall skill"
fi
if [ -d "$SKILLS_DIR/learn" ]; then
    rm -rf "$SKILLS_DIR/learn"
    info "Removed /learn skill"
fi

# Remove installation
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    info "Removed $INSTALL_DIR"
fi

echo ""
info "Uninstall complete. Memories and skills created by the learner are kept in ~/.claude/"
echo ""
