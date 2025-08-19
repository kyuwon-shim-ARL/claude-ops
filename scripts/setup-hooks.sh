#!/bin/bash

# Claude-Ops Hook Setup Script
# Automated setup of Claude Code hooks for notification system

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

echo -e "${BLUE}🚀 Claude-Ops Hook Setup${NC}"
echo ""

# Check if Claude Code is installed
check_claude_code() {
    echo -e "${YELLOW}Checking Claude Code installation...${NC}"
    if command -v claude &> /dev/null; then
        echo -e "${GREEN}✅ Claude Code found${NC}"
        return 0
    else
        echo -e "${RED}❌ Claude Code not found${NC}"
        echo "Please install Claude Code first: https://claude.ai/code"
        return 1
    fi
}

# Setup hook configuration
setup_hooks() {
    echo -e "${YELLOW}Setting up Claude Code hooks...${NC}"
    
    cd "$CLAUDE_OPS_DIR"
    
    # Use Python hook manager for setup
    python3 -c "
import sys
sys.path.insert(0, '.')
from claude_ops.hook_manager import HookManager

try:
    hook_manager = HookManager()
    success = hook_manager.setup_hooks()
    
    if success:
        print('✅ Hooks configured successfully')
        
        # Test the setup
        test_success = hook_manager.test_hook_notification()
        if test_success:
            print('✅ Hook test passed')
        else:
            print('⚠️  Hook test failed, but configuration is valid')
    else:
        print('❌ Hook setup failed')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ Error: {e}')
    sys.exit(1)
"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Hook setup completed${NC}"
        return 0
    else
        echo -e "${RED}❌ Hook setup failed${NC}"
        return 1
    fi
}

# Enable hybrid monitoring
enable_hybrid() {
    echo -e "${YELLOW}Enabling hybrid monitoring...${NC}"
    
    cd "$CLAUDE_OPS_DIR"
    
    python3 -c "
import sys
sys.path.insert(0, '.')
from claude_ops.hook_manager import HookManager

try:
    hook_manager = HookManager()
    success = hook_manager.enable_hybrid_mode()
    
    if success:
        print('✅ Hybrid monitoring enabled')
    else:
        print('❌ Hybrid monitoring setup failed')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ Error: {e}')
    sys.exit(1)
"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Hybrid monitoring enabled${NC}"
        return 0
    else
        echo -e "${RED}❌ Hybrid monitoring setup failed${NC}"
        return 1
    fi
}

# Show status
show_status() {
    echo -e "${YELLOW}Hook system status:${NC}"
    
    cd "$CLAUDE_OPS_DIR"
    
    python3 -c "
import sys
sys.path.insert(0, '.')
from claude_ops.hook_manager import HookManager

try:
    hook_manager = HookManager()
    status = hook_manager.get_hook_status()
    
    print(f'Settings file: {status[\"settings_file\"]}')
    print(f'Settings exists: {\"✅\" if status[\"settings_exists\"] else \"❌\"}')
    print(f'Hook script: {status[\"hook_script\"]}')
    print(f'Script exists: {\"✅\" if status[\"script_exists\"] else \"❌\"}')
    print(f'Script executable: {\"✅\" if status[\"script_executable\"] else \"❌\"}')
    print(f'Hooks configured: {\"✅\" if status[\"hooks_configured\"] else \"❌\"}')
    if status['active_hooks']:
        print(f'Active hooks: {', '.join(status[\"active_hooks\"])}')
        
except Exception as e:
    print(f'❌ Error: {e}')
"
}

# Main setup process
main_setup() {
    echo -e "${BLUE}📋 Starting automated hook setup...${NC}"
    echo ""
    
    # Step 1: Check Claude Code
    if ! check_claude_code; then
        exit 1
    fi
    echo ""
    
    # Step 2: Setup hooks
    if ! setup_hooks; then
        exit 1
    fi
    echo ""
    
    # Step 3: Enable hybrid monitoring
    if ! enable_hybrid; then
        exit 1
    fi
    echo ""
    
    # Step 4: Show final status
    show_status
    echo ""
    
    echo -e "${GREEN}🎉 Hook setup completed successfully!${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Claude Code will now send notifications when work completes"
    echo "2. Hybrid monitoring provides backup polling if hooks fail"
    echo "3. Use 'claude-ops status' to check system health"
    echo ""
    echo -e "${BLUE}💡 To test the system:${NC}"
    echo "   python3 -m claude_ops.hook_manager test"
}

# Handle command line arguments
case "${1:-setup}" in
    "setup"|"install")
        main_setup
        ;;
    "status"|"check")
        show_status
        ;;
    "test")
        echo -e "${YELLOW}Testing hook system...${NC}"
        cd "$CLAUDE_OPS_DIR"
        python3 -m claude_ops.hook_manager test
        ;;
    "remove"|"uninstall")
        echo -e "${YELLOW}Removing hooks...${NC}"
        cd "$CLAUDE_OPS_DIR"
        python3 -m claude_ops.hook_manager remove
        echo -e "${GREEN}✅ Hooks removed${NC}"
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  setup    - Setup Claude Code hooks (default)"
        echo "  status   - Show hook system status"
        echo "  test     - Test hook notification"
        echo "  remove   - Remove hook configuration"
        echo "  help     - Show this help"
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac