# Claude-Telegram Bridge

A modular bridge system for connecting Claude Code with Telegram for monitoring and control.

## Features

- **Real-time monitoring**: Tracks Claude session state changes
- **Telegram bot interface**: Interactive bot with inline keyboard controls
- **Smart notifications**: Context-aware notifications with duplicate filtering
- **Multi-directory support**: Dynamic session naming based on working directory
- **Security**: User authorization and input validation
- **Modular design**: Clean separation of concerns with proper Python packaging

## Quick Start

1. **Install the bridge:**
   ```bash
   ./install-bridge.sh
   ```

2. **Configure your .env file:**
   ```bash
   # Required
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ALLOWED_USER_IDS=123456789,987654321
   
   # Optional  
   TELEGRAM_CHAT_ID=your_chat_id_here
   TMUX_SESSION_PREFIX=claude
   CHECK_INTERVAL=3
   ```

3. **Start the bridge:**
   ```bash
   ./start-bridge.sh both    # Bot + Monitor (recommended)
   ./start-bridge.sh bot     # Bot only
   ./start-bridge.sh monitor # Monitor only
   ```

## Module Structure

```
claude-bridge/
├── __init__.py          # Package initialization
├── __main__.py          # Main entry point
├── config.py            # Configuration management
├── telegram_bot.py      # Telegram bot with inline controls
├── monitor.py           # Claude session monitoring
├── notifier.py          # Smart notification system
└── requirements.txt     # Python dependencies
```

## Bot Commands

- `/start` - Start Claude session and show control panel
- `/status` - Check bot and tmux session status
- `/log` - View current Claude screen output
- `/stop` - Send ESC key to interrupt Claude
- `/help` - Show help message
- `/clear` - Clear Claude screen
- `/menu` - Show inline keyboard menu

## Configuration

All configuration is managed through environment variables in `.env`:

### Required Variables

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from @BotFather
- `ALLOWED_USER_IDS`: Comma-separated list of authorized Telegram user IDs

### Optional Variables

- `TELEGRAM_CHAT_ID`: Chat ID for notifications (auto-detected if not set)
- `TMUX_SESSION_PREFIX`: Prefix for tmux session names (default: "claude")
- `CHECK_INTERVAL`: Monitoring check interval in seconds (default: 3)
- `LOG_LEVEL`: Logging level (default: "INFO")

## Session Naming

Sessions are automatically named based on the current directory:
- Working directory: `/home/user/my-project`
- Session name: `claude_my-project`

This allows running multiple Claude instances in different projects simultaneously.

## Usage Examples

### Direct Module Usage

```bash
# Start bot
python -m claude_bridge bot

# Start monitor
python -m claude_bridge monitor

# Show configuration
python -m claude_bridge config
```

### Programmatic Usage

```python
from claude_bridge import BridgeConfig, ClaudeTelegramBot, ClaudeMonitor

# Initialize with default config
config = BridgeConfig()
bot = ClaudeTelegramBot(config)
monitor = ClaudeMonitor(config)

# Start bot
bot.run()

# Start monitoring loop  
monitor.monitor_loop()
```

## Installation in Existing Projects

1. Copy the `claude-bridge/` directory to your project
2. Run `./install-bridge.sh` from your project root
3. Configure `.env` with your Telegram credentials
4. Start with `./start-bridge.sh`

The bridge will automatically adapt to your project's directory name for session management.

## Dependencies

- `python-telegram-bot>=20.0`: Telegram Bot API wrapper
- `python-dotenv>=1.0.0`: Environment variable management
- `requests>=2.25.0`: HTTP requests for notifications

## Security Features

- **User authorization**: Only configured user IDs can interact with the bot
- **Input validation**: Dangerous command patterns are automatically blocked
- **Input limits**: Maximum 500 characters per message
- **Logging**: All activities are logged for audit purposes

## Troubleshooting

### Common Issues

1. **"Module not found" errors**: Make sure you're running from the correct directory and Python path is set
2. **Bot not responding**: Check your bot token and that the bot is started with `/start`
3. **Notifications not working**: Verify `TELEGRAM_CHAT_ID` is set or message the bot first
4. **Session not found**: Ensure tmux is installed and Claude Code is running

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
./start-bridge.sh
```

### Manual Testing

Test configuration:
```bash
python -m claude_bridge config
```

Test notification:
```bash
python -m claude_bridge.notifier "Test message" --force
```