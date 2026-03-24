# ctb-dashboard

Real-time Claude Code session monitoring dashboard. Standalone PyPI package extracted from [Claude-Telegram-Bridge](https://github.com/user/claude-ops).

## Requirements

- Python 3.10+
- tmux (sessions must follow `claude*` naming convention)
- Active Claude Code tmux sessions to monitor

## Installation

```bash
pip install ctb-dashboard
```

Or install from source:

```bash
git clone <repo-url>
cd ctb-dashboard
pip install -e .
```

## Usage

```bash
# Start the dashboard server (default: http://0.0.0.0:8420)
ctb-dashboard
```

Open `http://<host>:8420` in your browser. The dashboard auto-discovers all `claude*` tmux sessions and displays their state in real-time via SSE.

### Features

- **Real-time monitoring**: Polls tmux sessions every 3 seconds
- **State detection**: Detects WORKING, IDLE, WAITING_INPUT, ERROR, CONTEXT_LIMIT states
- **Fresh completion glow**: Amber pulse animation when a session finishes work
- **Pin sessions**: Pin important sessions to the top of the grid
- **Browser notifications**: Optional alerts when pinned sessions complete work
- **PWA support**: Installable as a Progressive Web App on mobile/desktop

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /api/sessions` | JSON snapshot of all session states |
| `GET /api/sessions/stream` | SSE stream of state changes |
| `GET /api/health` | Health check |

## License

MIT
