# Changelog

All notable changes to Claude-Ops will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.2] - 2025-09-09

### 🎯 Enhanced Notification Detection System

Major improvements to Claude session monitoring with advanced completion detection and comprehensive debugging tools.

### ✨ Added
- **Quiet Completion Detection**: Now detects commands like `ls`, `git log`, `docker images` that complete without explicit working indicators
- **Completion Message Recognition**: Automatically detects "Done", "Successfully", "Completed", "✅" patterns in output
- **Comprehensive Debugging Tools**: Added `notification_debugger.py` with state tracking, missed notification analysis, and debug reports
- **Enhanced Prompt Patterns**: Support for 12 different shell prompt patterns (Bash, Zsh, Python, IPython, etc.)
- **4-Way Notification Triggers**: Traditional work completion + input waiting + quiet completion + completion messages

### 🔧 Enhanced  
- **Multi-Monitor Logic**: Enhanced `multi_monitor.py` with improved state transition handling and debug logging
- **Session State Analysis**: More robust pattern matching with screen stability checking (2+ cycles)
- **Screen Content Caching**: Optimized tmux capture with 1-second caching and 500ms state caching
- **Notification Cooldown**: 30-second cooldown prevents duplicate notifications

### 📊 Performance Improvements
- **Detection Rate**: Improved from ~70% to ~85% (target: 95%)
- **Response Time**: 2-6 seconds for quiet completions, immediate for explicit messages
- **False Positive Rate**: <10% with enhanced stability checking
- **Test Coverage**: 96.4% pass rate (108/112 tests)

### 🧪 Testing & Validation
- **Comprehensive Test Suite**: 12 new test cases covering quiet completion scenarios
- **Real Scenario Validation**: Tested with actual tmux sessions and commands
- **Live Monitoring**: Validated with 8 active Claude sessions over 20 seconds
- **Integration Tests**: End-to-end workflow testing with state transitions

### 📝 Documentation & Analysis
- **Improvement Plan**: Detailed technical specification and implementation roadmap
- **Test Results Report**: Comprehensive validation results with real scenarios
- **Analysis Reports**: In-depth analysis of detection gaps and solutions
- **Weekly Report**: Progress tracking and metrics documentation

### 🔍 Debug & Troubleshooting
- **State History Tracking**: Complete timeline of session state changes
- **Missed Notification Analysis**: Automatic detection of missed notification opportunities  
- **Debug Reports**: Structured analysis with session context and patterns
- **JSON Session Export**: Exportable debug sessions for analysis

### 💡 Usage Examples
```python
# Enable debug mode for troubleshooting
from claude_ops.utils.notification_debugger import enable_debug_mode
enable_debug_mode(verbose=True)

# Generate debug report for specific session
from claude_ops.utils.notification_debugger import generate_report
print(generate_report("claude_session_name"))
```

### 🚀 Implementation Details
- Enhanced `SessionStateAnalyzer.detect_quiet_completion()` method
- Added `NotificationDebugger` class with comprehensive logging
- Improved regex patterns for various shell prompts and completion messages
- Better screen content analysis with stability tracking

## [2.0.1] - 2025-08-27

### 🐛 Fixed
- **Session Log Capture**: Improved reliability for attached sessions with retry logic
- **Markdown Escaping**: Fixed `/summary` command parsing errors with proper character escaping
- **Board Access**: Resolved intermittent connection issues with urban-microbiome-toolkit session
- **Error Handling**: Added timeout and fallback messages for better UX

### 🔧 Improved
- **Capture Resilience**: 3-attempt retry logic with 0.2s intervals
- **Timeout Protection**: 2-second timeout prevents hanging on unresponsive sessions
- **User Feedback**: Clear error messages indicating when sessions are attached elsewhere

## [2.1.1] - 2025-08-20

### 🚀 Pure Bridge Architecture Completion

Complete transformation to pure Telegram bridge with all workflow commands delegated to claude-dev-kit.

### ✨ Added
- **Scale-Based Documentation**: Commands now support strategic/tactical/operational work classification
- **Smart Session Archiving**: Intelligent document management with persistence and archiving
- **PRD Template**: Standardized Product Requirements Document template

### 🔄 Changed
- **Pure Bridge Mode**: Removed 372+ lines of duplicate workflow command code
- **Command Updates**: All slash commands updated with latest claude-dev-kit prompts
- **Documentation Structure**: Aligned with claude-dev-kit ZEDS (Zero-Effort Documentation System)

### 🗑️ Removed
- **prompt_loader.py**: Eliminated unnecessary prompt loading module
- **Workflow Commands**: Removed /fullcycle, /plan, /implement, /stabilize, /deploy duplicates
- **Project Directories**: Removed src/, core_features/, tools/ (not needed for bridge)

## [2.0.0] - 2025-01-18

### 🎯 Major Release: Telegram-First Architecture

This is a major refactoring that transforms Claude-Ops into a focused Telegram-Claude bridge system, removing complexity and improving reliability.

### ✨ Added
- **Streamlined Telegram Bot**: Complete rewrite focused on core Claude session control
- **Reply-Based Session Targeting**: Reply to session messages to send commands directly to specific sessions
- **Workflow Integration**: Seamless integration with claude-dev-kit slash commands (`/기획`, `/구현`, `/안정화`, `/배포`)
- **Session State Detection**: Real-time monitoring of Claude session states (working/idle/error)
- **Comprehensive Test Suite**: 128 tests covering all core functionality
- **Configuration Management**: Unified config system with environment variable support
- **Multi-Session Support**: Monitor and control multiple Claude sessions simultaneously

### 🔄 Changed
- **Simplified Architecture**: Removed Notion and Git integrations for focused functionality
- **Telegram-First Design**: All interactions now happen through Telegram interface
- **Improved Session Management**: Better tmux session discovery and control
- **Enhanced Documentation**: Complete rewrite of README.md and CLAUDE.md
- **Modernized Dependencies**: Updated to latest python-telegram-bot (v22.3)

### 🗑️ Removed
- **Notion Integration**: Removed complex Notion workflow management
- **Git Automation**: Removed automatic git operations and PR creation
- **CLI Tools**: Removed command-line interfaces in favor of Telegram control
- **Legacy Monitoring**: Removed outdated monitoring and notification systems

### 🔧 Technical Improvements
- **MECE Architecture**: Mutually exclusive and collectively exhaustive module design
- **Test Coverage**: Comprehensive test suite with 100% core functionality coverage
- **Type Safety**: Improved type hints and validation throughout codebase
- **Error Handling**: Robust error handling and recovery mechanisms
- **Performance**: Optimized session detection and state management

### 📚 Documentation
- **Complete README Rewrite**: Clear setup and usage instructions
- **Enhanced CLAUDE.md**: Comprehensive Claude Code integration guide
- **Environment Configuration**: Detailed .env.example with all options
- **Usage Examples**: Real-world scenarios and best practices

### 🏗️ Infrastructure
- **Minimal Dependencies**: Reduced to 3 core dependencies for reliability
- **Python 3.11+**: Modern Python support with latest features
- **UV Package Management**: Fast and reliable dependency management
- **Automated Testing**: GitHub Actions ready test suite

### 📊 Metrics
- **Lines of Code**: 7,980 total (focused and maintainable)
- **Test Coverage**: 128 tests passing (comprehensive coverage)
- **Modules**: 21 Python modules (well-structured architecture)
- **Dependencies**: 3 core dependencies (minimal and stable)

### 🎉 Migration Notes
This is a breaking change from v1.x. The system is now focused exclusively on Telegram-Claude integration:

1. **Setup**: Copy `.env.example` to `.env` and configure Telegram bot settings
2. **Start**: Run `python -m claude_ops.telegram.bot` to start monitoring
3. **Use**: Control Claude sessions directly from Telegram using reply-based targeting

### 🔗 Compatibility
- **Python**: Requires Python 3.11 or higher
- **Claude Code**: Compatible with latest Claude Code versions
- **Tmux**: Requires tmux for session management
- **Telegram**: Requires Telegram bot token from @BotFather

---

## [1.x] - Legacy Versions

Previous versions focused on complex multi-system integration. See git history for details.

### Migration from 1.x to 2.0.0

**Breaking Changes:**
- Notion integration removed
- Git automation removed
- CLI tools removed
- Configuration format changed

**Migration Path:**
1. Back up your existing configuration
2. Set up new `.env` file with Telegram bot settings
3. Start the new Telegram bot system
4. Use Telegram interface instead of CLI tools

**Benefits:**
- Simpler setup (1 minute vs 10+ minutes)
- More reliable (fewer dependencies)
- Better user experience (Telegram-first)
- Easier maintenance (focused codebase)