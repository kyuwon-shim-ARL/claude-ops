# Changelog

All notable changes to Claude-Ops will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-01-18

### 🎯 Major Release: Telegram-First Architecture

This is a major refactoring that transforms Claude-Ops into a focused Telegram-Claude bridge system, removing complexity and improving reliability.

### ✨ Added
- **Streamlined Telegram Bot**: Complete rewrite focused on core Claude session control
- **Reply-Based Session Targeting**: Reply to session messages to send commands directly to specific sessions
- **Workflow Macros**: `@기획`, `@구현`, `@안정화`, `@배포` for structured development prompts
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