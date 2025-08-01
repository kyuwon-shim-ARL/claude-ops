#!/bin/bash

# Claude Code Bash Command Feedback Hook
# Provides better feedback for long-running bash commands

# This script runs before each bash command to provide feedback
# Usage: Called automatically by Claude Code when bash commands are executed

echo "🔄 Executing command: ${CLAUDE_BASH_COMMAND:0:80}..."
echo "⏱️  Started at: $(date '+%H:%M:%S')"
echo "💡 Press Ctrl+C if you need to interrupt"
echo "---"