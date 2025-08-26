#!/bin/bash

# Create new Claude project using unified ProjectCreator
# Usage: ./new-project.sh project-name [custom-directory]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_OPS_DIR="$(dirname "$SCRIPT_DIR")"

# Check arguments
if [ $# -eq 0 ]; then
    echo -e "${RED}Usage: $0 project-name [custom-directory]${NC}"
    echo ""
    echo "Examples:"
    echo "  $0 my-ai-app                    # Creates ~/projects/my-ai-app"
    echo "  $0 web-scraper ~/work/client   # Creates ~/work/client/web-scraper"
    echo "  $0 data-analysis /tmp/test     # Creates /tmp/test/data-analysis"
    exit 1
fi

PROJECT_NAME="$1"
PROJECT_PATH=""

# Determine custom path if provided
if [ $# -ge 2 ]; then
    CUSTOM_DIR="$2"
    if [[ "$CUSTOM_DIR" == /* ]]; then
        # Absolute path
        PROJECT_PATH="$CUSTOM_DIR/$PROJECT_NAME"
    else
        # Relative path - make it absolute
        PROJECT_PATH="$(pwd)/$CUSTOM_DIR/$PROJECT_NAME"
    fi
fi

echo -e "${BLUE}🚀 Creating new Claude project using unified ProjectCreator...${NC}"
echo -e "📁 Project: ${YELLOW}$PROJECT_NAME${NC}"
echo ""

# Change to claude-ops directory to use the Python module
cd "$CLAUDE_OPS_DIR"

# Use Python ProjectCreator with uv environment
uv run python -c "
import sys
sys.path.insert(0, '.')
from claude_ops.project_creator import ProjectCreator

try:
    project_path = '$PROJECT_PATH' if '$PROJECT_PATH' else None
    result = ProjectCreator.create_project_simple('$PROJECT_NAME', project_path)
    
    if result['status'] == 'success':
        print(f\"✅ {result['message']}\")
        print(f\"📁 Path: {result['project_path']}\")  
        print(f\"🎯 Session: {result['session_name']}\")
        if result.get('git_initialized'):
            print('📦 Git repository initialized with comprehensive .gitignore')
        print('')
        print('${BLUE}Next steps:${NC}')
        print(f\"  1. Connect: ${YELLOW}tmux attach -t {result['session_name']}${NC}\")
        print(f\"  2. Or use Telegram: ${YELLOW}/sessions${NC} to switch to this project\")
        print('')
        print('${GREEN}🎉 Happy coding!${NC}')
        exit(0)
    else:
        print(f\"❌ Error: {result['error']}\")
        exit(1)
        
except Exception as e:
    print(f'❌ Python error: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
"

# Check the exit code from Python
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Project creation completed successfully!${NC}"
else
    echo -e "${RED}❌ Project creation failed!${NC}"
    exit 1
fi