# Multi-User Deployment Guide for Claude-Ops

## Overview

This guide explains how to deploy Claude-Ops for multiple users (~10 people) in your organization. Each user will have their own independent instance with personal Telegram bot configuration.

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│                 Git Repository                    │
│           (Central Claude-Ops Source)             │
└──────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   User 1    │ │   User 2    │ │   User N    │
│   Instance  │ │   Instance  │ │   Instance  │
├─────────────┤ ├─────────────┤ ├─────────────┤
│ Personal    │ │ Personal    │ │ Personal    │
│ Telegram    │ │ Telegram    │ │ Telegram    │
│    Bot      │ │    Bot      │ │    Bot      │
└─────────────┘ └─────────────┘ └─────────────┘
```

## 📋 Prerequisites

Each user needs:
1. **Telegram Account** - Personal Telegram account
2. **Terminal Access** - Linux/macOS terminal or WSL on Windows
3. **Python 3.9+** - Python runtime installed
4. **Git** - For cloning and updates
5. **tmux** - Terminal multiplexer for session management

## 🚀 Quick Setup (For Each User)

### Step 1: Clone Repository

```bash
# Clone the Claude-Ops repository
git clone https://github.com/your-org/claude-ops.git
cd claude-ops
```

### Step 2: Create Personal Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Follow prompts to create your bot:
   - Choose a name (e.g., "John's Claude Ops")
   - Choose a username (must end with 'bot', e.g., "johns_claude_ops_bot")
4. Save the **Bot Token** provided by BotFather

### Step 3: Get Your Telegram IDs

1. Message your new bot with any text
2. Visit this URL in your browser (replace YOUR_BOT_TOKEN):
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
3. Find your **user ID** and **chat ID** in the JSON response:
   ```json
   {
     "message": {
       "from": {
         "id": 123456789,  // This is your user ID
       },
       "chat": {
         "id": 123456789,  // This is your chat ID
       }
     }
   }
   ```

### Step 4: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your personal values
nano .env  # or use your preferred editor
```

Update these values in `.env`:
```bash
TELEGRAM_BOT_TOKEN=your_personal_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
ALLOWED_USER_IDS=your_user_id_here

# Optional: Set your preferred working directory
CLAUDE_WORKING_DIR=/home/yourname/projects
```

### Step 5: Install Dependencies

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Python dependencies
uv sync
```

### Step 6: Setup Claude Code Hooks (IMPORTANT!)

```bash
# Automated setup
./scripts/setup-hooks.sh

# Or manual setup
uv run python -m claude_ops.hook_manager setup
```

### Step 7: Start Your Bot

```bash
# Run the bot
uv run python -m claude_ops.telegram.bot

# Or run in background with tmux
tmux new -d -s claude-ops-bot 'uv run python -m claude_ops.telegram.bot'
```

### Step 8: Verify Setup

1. Open Telegram and message your bot
2. Send `/help` to see available commands
3. Send `/status` to verify bot is running
4. Create a test project with `/new-project test-app`

## 📁 File Structure

Each user's instance will have:
```
claude-ops/
├── .env                  # Personal configuration (NOT shared)
├── .env.example          # Template for new users
├── claude_ops/           # Core code (shared via Git)
├── scripts/              # Utility scripts
├── tests/                # Test files
└── README.md             # Documentation
```

## 🔒 Security Best Practices

### DO:
- ✅ Keep your `.env` file private (it contains your bot token)
- ✅ Use unique bot tokens for each user
- ✅ Regularly update from main repository
- ✅ Set `ALLOWED_USER_IDS` to only your Telegram ID

### DON'T:
- ❌ Share your bot token with others
- ❌ Commit `.env` file to Git
- ❌ Use the same bot for multiple users
- ❌ Allow unauthorized user IDs

## 🔄 Updating Your Instance

### Regular Updates (Weekly Recommended)

```bash
# Fetch latest changes
git fetch origin

# Review changes
git log HEAD..origin/main --oneline

# Apply updates
git pull origin main

# Update dependencies if needed
uv sync

# Restart bot
# (Stop current bot with Ctrl+C first)
uv run python -m claude_ops.telegram.bot
```

### Breaking Changes

If updates include breaking changes:
1. Check `CHANGELOG.md` for migration instructions
2. Backup your `.env` file
3. Follow specific migration steps if provided

## 🛠️ Troubleshooting

### Common Issues

#### Bot Not Responding
```bash
# Check if bot is running
ps aux | grep claude_ops

# Check logs
tail -f claude_ops.log  # If logging to file

# Verify token
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

#### Permission Denied
```bash
# Ensure your user ID is in ALLOWED_USER_IDS
grep ALLOWED_USER_IDS .env

# Verify it matches your actual Telegram user ID
```

#### Session Not Found
```bash
# List all tmux sessions
tmux list-sessions

# Check if Claude session exists
tmux has-session -t claude_projectname
```

## 👥 Team Coordination

### Shared Practices

1. **Naming Convention**: Use consistent project naming
   - Format: `teamname-projectname`
   - Example: `backend-auth-service`

2. **Status Updates**: Share progress in team channel
   - Use `/board` command to show active sessions
   - Screenshot and share when needed

3. **Knowledge Sharing**: Document common workflows
   - Create team-specific macros
   - Share useful prompts

### Admin Responsibilities

The team admin should:
1. Maintain central Git repository
2. Test updates before team deployment
3. Provide support for setup issues
4. Manage team-wide configuration updates

## 📊 Monitoring Usage

### Individual Metrics
Each user can monitor their usage:
```bash
# Check active sessions
/sessions

# View session board
/board

# Check bot status
/status
```

### Team Metrics (Optional)
For team-wide monitoring, consider:
- Central logging server
- Shared metrics dashboard
- Regular usage reports

## 🆘 Getting Help

### Resources
1. **Documentation**: Check `CLAUDE.md` for detailed features
2. **README**: Quick reference for commands
3. **Source Code**: Review `claude_ops/` for implementation details

### Support Channels
1. **Team Chat**: Ask in your team's Slack/Discord
2. **GitHub Issues**: Report bugs and request features
3. **Admin Support**: Contact your Claude-Ops admin

## 📝 User Onboarding Checklist

For new users, complete these steps:

- [ ] Clone repository
- [ ] Create personal Telegram bot
- [ ] Get Telegram IDs (user and chat)
- [ ] Configure `.env` file
- [ ] Install dependencies with `uv sync`
- [ ] Setup Claude Code hooks
- [ ] Start bot
- [ ] Test with `/help` command
- [ ] Create test project
- [ ] Join team communication channel

## 🎯 Best Practices for Teams

1. **Regular Sync Meetings**: Weekly sync on Claude-Ops usage
2. **Shared Workflows**: Document and share effective prompts
3. **Version Control**: Always pull latest changes before major work
4. **Backup Strategy**: Keep backups of important session logs
5. **Security Audits**: Regular review of allowed user IDs

## 📈 Scaling Beyond 10 Users

If your team grows beyond 10 users:

1. **Consider Centralization**: 
   - Shared bot with user management
   - Role-based access control
   - Centralized configuration

2. **Infrastructure Options**:
   - Docker containers per user
   - Kubernetes for orchestration
   - Cloud-based deployment

3. **Management Tools**:
   - User provisioning scripts
   - Automated updates
   - Centralized monitoring

---

## Quick Reference Card

### Essential Commands
```bash
# Setup
git clone <repo> && cd claude-ops
cp .env.example .env && nano .env
uv sync
./scripts/setup-hooks.sh

# Daily Use
uv run python -m claude_ops.telegram.bot  # Start bot
git pull origin main                      # Update
tmux attach -t claude_projectname         # Join session

# Telegram Commands
/help         # Show all commands
/new-project  # Create new project
/sessions     # List active sessions
/board        # Session grid view
/status       # Bot status
```

### Environment Variables
```bash
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_CHAT_ID=<your chat ID>
ALLOWED_USER_IDS=<your user ID>
CLAUDE_WORKING_DIR=<optional: project directory>
```

---

*Last Updated: 2024*
*Version: 2.0.0*