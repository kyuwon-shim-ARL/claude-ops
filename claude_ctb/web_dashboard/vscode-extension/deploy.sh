#!/bin/bash
# Compile TypeScript and deploy to installed VSCode extension
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.vscode-server/extensions/claude-ctb.claude-ctb-dashboard-0.1.0"

cd "$SCRIPT_DIR"
./node_modules/.bin/tsc -p ./
cp out/extension.js "$INSTALL_DIR/out/extension.js"
cp static/index.html "$INSTALL_DIR/static/index.html"
echo "✓ Deployed to $INSTALL_DIR"
echo "→ VSCode: Developer: Reload Window"
