# Claude-Telegram Bridge

[![PyPI version](https://badge.fury.io/py/claude-telegram-bridge.svg)](https://badge.fury.io/py/claude-telegram-bridge)
[![Python Versions](https://img.shields.io/pypi/pyversions/claude-telegram-bridge.svg)](https://pypi.org/project/claude-telegram-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modular bridge system for connecting Claude Code with Telegram for real-time monitoring and interactive control.

## Features

- **Real-time monitoring**: Tracks Claude session state changes and sends smart notifications
- **Interactive Telegram bot**: Full-featured bot with inline keyboard controls
- **Smart notifications**: Context-aware notifications with duplicate filtering
- **Multi-directory support**: Dynamic session naming based on working directory
- **Security**: User authorization, input validation, and comprehensive logging
- **Easy installation**: One-command setup in any project

## Installation

### Option 1: Install from PyPI (Recommended)

```bash
pip install claude-telegram-bridge
```

### Option 2: Install from Source

```bash
git clone https://github.com/kyuwon-shim-ARL/claude-ops.git
cd claude-ops/claude-telegram-bridge-package
pip install -e .
```

## Quick Start

### 1. Configuration

Create a `.env` file in your project directory:

```bash
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USER_IDS=123456789,987654321

# Optional
TELEGRAM_CHAT_ID=your_chat_id_here
TMUX_SESSION_PREFIX=claude
CHECK_INTERVAL=3
LOG_LEVEL=INFO
```

**Getting your credentials:**
- **Bot Token**: Message [@BotFather](https://t.me/botfather) on Telegram to create a bot
- **User IDs**: Message your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
- **Chat ID**: Optional, auto-detected when you first message the bot

### 2. Usage

#### Command Line Interface

```bash
# Start both bot and monitor (recommended)
claude-bridge start

# Start only the bot
claude-bridge bot

# Start only the monitor  
claude-bridge monitor

# Check configuration
claude-bridge config

# Get help
claude-bridge --help
```

#### Programmatic Usage

```python
from claude_telegram_bridge import BridgeConfig, ClaudeTelegramBot, ClaudeMonitor

# Initialize with default config
config = BridgeConfig()
bot = ClaudeTelegramBot(config)
monitor = ClaudeMonitor(config)

# Start bot
bot.run()

# Start monitoring (in separate thread/process)
monitor.monitor_loop()
```

## Bot Commands

Once your bot is running, you can use these Telegram commands:

- `/start` - Start Claude session and show control panel
- `/status` - Check bot and tmux session status  
- `/log` - View current Claude screen output
- `/stop` - Send ESC key to interrupt Claude
- `/help` - Show help message
- `/clear` - Clear Claude screen
- `/menu` - Show inline keyboard menu

## How It Works

### Session Management

The bridge automatically creates tmux session names based on your current directory:

- Working directory: `/home/user/my-project`
- Session name: `claude_my-project`

This allows you to run multiple Claude instances in different projects simultaneously.

### Smart Monitoring

The monitor watches your Claude session and sends notifications for:

- ✅ **Work completion**: When Claude finishes processing
- 💬 **Response completion**: When Claude finishes responding  
- ❌ **Errors**: When issues are detected

### Security Features

- **User authorization**: Only configured user IDs can interact
- **Input validation**: Dangerous command patterns are blocked
- **Rate limiting**: Built-in protection against spam
- **Audit logging**: All activities are logged for security

## Configuration Options

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | - | Your Telegram bot token |
| `ALLOWED_USER_IDS` | ✅ | - | Comma-separated list of user IDs |
| `TELEGRAM_CHAT_ID` | ❌ | auto-detect | Chat ID for notifications |
| `TMUX_SESSION_PREFIX` | ❌ | `claude` | Prefix for session names |
| `CHECK_INTERVAL` | ❌ | `3` | Monitor check interval (seconds) |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level |

## Advanced Usage

### Using in Existing Projects

```bash
# Navigate to your project
cd /path/to/your/project

# Install and configure
pip install claude-telegram-bridge
echo "TELEGRAM_BOT_TOKEN=your_token" > .env
echo "ALLOWED_USER_IDS=your_user_id" >> .env

# Start the bridge
claude-bridge start
```

### Integration with CI/CD

```yaml
# GitHub Actions example
- name: Setup Claude Bridge
  run: |
    pip install claude-telegram-bridge
    echo "TELEGRAM_BOT_TOKEN=${{ secrets.TELEGRAM_BOT_TOKEN }}" > .env
    echo "ALLOWED_USER_IDS=${{ secrets.ALLOWED_USER_IDS }}" >> .env
    
- name: Start monitoring
  run: claude-bridge monitor &
```

### Custom Configuration

```python
from claude_telegram_bridge import BridgeConfig

# Custom configuration
config = BridgeConfig(env_file="/custom/path/.env")
print(f"Session: {config.session_name}")
print(f"Users: {config.allowed_user_ids}")
```

## Troubleshooting

### Common Issues

**1. "Module not found" errors**
```bash
pip install --upgrade claude-telegram-bridge
```

**2. Bot not responding**
- Check your bot token is correct
- Verify you've messaged the bot with `/start`
- Ensure your user ID is in `ALLOWED_USER_IDS`

**3. Notifications not working**
- Set `TELEGRAM_CHAT_ID` in your `.env` file
- Check the bot has permission to send messages

**4. Session not found**
- Ensure tmux is installed: `sudo apt install tmux`
- Verify Claude Code is running in a tmux session

### Debug Mode

Enable detailed logging:

```bash
export LOG_LEVEL=DEBUG
claude-bridge start
```

### Getting Help

- **Documentation**: [GitHub Repository](https://github.com/kyuwon-shim-ARL/claude-ops)
- **Issues**: [Report bugs](https://github.com/kyuwon-shim-ARL/claude-ops/issues)
- **Discussions**: [Community support](https://github.com/kyuwon-shim-ARL/claude-ops/discussions)

## Contributing

Contributions are welcome! Please feel free to:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

### v1.0.0 (2025-01-XX)
- Initial PyPI release
- Complete modular architecture
- CLI interface with `claude-bridge` command
- Smart monitoring and notifications
- Multi-directory support
- Comprehensive documentation

---

**Built with ❤️ for the Claude Code community**