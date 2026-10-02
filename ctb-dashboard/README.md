# ctb-dashboard

Real-time Claude Code session monitoring dashboard. Standalone PyPI package extracted from [Claude-Telegram-Bridge](https://github.com/kyuwon-shim-ARL/claude-ops).

## Requirements

- Python 3.10+
- `tmux`, with Claude Code sessions named `claude*`
- Claude Code itself, running in those tmux sessions

## Installation

```bash
pip install ctb-dashboard
```

From source:

```bash
git clone https://github.com/kyuwon-shim-ARL/claude-ops
cd claude-ops/ctb-dashboard
pip install -e .
```

Or straight from a git subdirectory without cloning:

```bash
pip install "git+https://github.com/kyuwon-shim-ARL/claude-ops#subdirectory=ctb-dashboard"
# or with uv
uv pip install "git+https://github.com/kyuwon-shim-ARL/claude-ops#subdirectory=ctb-dashboard"
```

## Usage

```bash
# Start the dashboard server (default: http://0.0.0.0:8420)
ctb-dashboard
```

Open `http://<host>:8420` in your browser. The dashboard auto-discovers all `claude*` tmux sessions and displays their state in real-time via SSE.

### Features

- **Real-time monitoring**: Polls tmux sessions every few seconds
- **State detection**: Detects WORKING, IDLE, WAITING_INPUT, ERROR, CONTEXT_LIMIT states
- **Fresh completion glow**: Amber pulse animation when a session finishes work
- **Pin sessions**: Pin important sessions to the top of the grid
- **Browser notifications**: Optional alerts when pinned sessions complete work
- **PWA support**: Installable as a Progressive Web App on mobile/desktop
- **Remote control**: Send keys/prompts to sessions from the dashboard, gated by a shared secret (see `CTB_CONTROL_SECRET` below)

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /api/sessions` | JSON snapshot of all session states |
| `GET /api/sessions/stream` | SSE stream of state changes |
| `GET /api/health` | Health check |

## Configuration (environment variables)

Nothing below is required to start the dashboard — every one of these has a
default, and features that depend on an unset one just degrade (reviewed
below). Set them via your shell, a `.env` loaded by systemd's
`EnvironmentFile`, or any process manager.

| Variable | Default | Purpose |
|---|---|---|
| `CTB_CONTROL_SECRET` (alias `CTB_FOCUS_SECRET`) | *(unset)* | **Required for any write.** Every mutating endpoint (send keys, send prompt, delete, create session, etc.) requires this value in the `X-CTB-Secret` header. Unset disables those endpoints entirely rather than leaving them open. |
| `CTB_REVIEW_SECRET` | *(unset)* | Shared secret for the `/review` PI-review-gate route. Unset makes `/review` return 403. |
| `CTB_BIND_HOST` | `0.0.0.0` | Interface to bind. Left at `0.0.0.0` by default because hard-binding to an interface that isn't up yet at boot loops forever under `systemd Restart=always`; use a firewall to restrict LAN access instead (see `deploy/firewall-8420.sh` in the repo root). |
| `CTB_BIND_PORT` | `8420` | Port to listen on. On start the server kills a previous **ctb-dashboard** listening on this port (never any other program); if something else holds it, startup fails with EADDRINUSE. Phone home-screen bookmarks and the VSCode extension expect 8420. |
| `CTB_PROJECTS_ROOT` | `~/projects` | Root directory containing your project folders; used by session creation and the PI review gate. |
| `CTB_PSTATUS_DIR` | `~/projects/project-status` | Optional sibling project providing a `scanner` module used by the PI review gate to find report artifacts. If missing, the gate's report lookup silently returns nothing instead of failing to import. |
| `CTB_STATE_DIR` | `~/.claude-ops` | Where dashboard state (pins, review overlays, audit log, etc.) is persisted. |
| `CTB_REVIEW_OVERLAY_DIR` | `~/.claude-ops` | Where PI review overlay files are written. |
| `CTB_REVIEW_OVERLAY_LOCK_TIMEOUT` | `10` | Seconds to wait for the review overlay file lock. |
| `CTB_CONTROL_AUDIT_LOG` | `~/.claude-ops/control-audit.log` | JSONL audit log of every mutating request. |
| `CTB_CONTROL_RATE_MAX` / `CTB_CONTROL_RATE_WINDOW` | `30` / `60` | Rate limit for control endpoints (max events per window-seconds). |
| `CTB_PROJECT_READ_RATE_MAX` / `CTB_PROJECT_READ_RATE_WINDOW` | `120` / `60` | Rate limit for project-read endpoints. |
| `CTB_UPLOAD_RATE_MAX` / `CTB_UPLOAD_RATE_WINDOW` | `60` / `60` | Rate limit for file uploads. |
| `CTB_UPLOAD_MAX_BYTES` | `25 MiB` | Max size of a single uploaded file. |
| `CTB_UPLOAD_DIR_MAX_BYTES` | `300 MiB` | Max total size of an upload directory. |
| `CTB_UPLOAD_CONCURRENCY` | `4` | Max concurrent uploads. |
| `CTB_UPLOAD_TIMEOUT` | `120` | Seconds before an upload receive times out. |
| `CTB_CLAUDE_BIN` | `claude` | Binary used to launch Claude Code in a new session. |
| `CTB_DASHBOARD_URL` | *(unset)* | Base URL used to build "open in dashboard" deep links in push notifications. |
| `CTB_PUSH_SUBJECT` | *(unset)* | VAPID subject (`mailto:` or `https:`) for web push notifications; push is disabled without a valid one. |
| `CTB_DEFAULT_REVIEWER_ID` | *(unset)* | Default reviewer id used by the PI review gate when none is supplied. |
| `CTB_STT_DAILY_SECONDS` | `1800` | Daily speech-to-text quota, in seconds. |

Two integrations degrade gracefully instead of being required:

- **oh-my-claudecode `.omc/` state** — if a project has it, the dashboard can show task/plan info from it; if not, those UI elements are simply empty.
- **project-status scanner** (`CTB_PSTATUS_DIR`) — if the sibling `project-status` project isn't present, the PI review gate's "latest report" lookup returns nothing instead of crashing on import.

## Running as a systemd user service

Minimal unit, adapted from `deploy/ctb-dashboard.service` in the repo root
(paths genericised):

```ini
[Unit]
Description=ctb-dashboard (port 8420)
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/ctb-dashboard
EnvironmentFile=-/path/to/.env
ExecStart=/path/to/venv/bin/ctb-dashboard
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

> **Warning:** `systemd`'s `EnvironmentFile` does **not** strip inline
> comments. `KEY=value  # comment` puts `  # comment` into the value
> literally. Put comments on their own line.

Enable with:

```bash
systemctl --user enable --now ctb-dashboard.service
```

## Security notes

- The server binds `0.0.0.0` by default (see `CTB_BIND_HOST` above). Put it
  behind a firewall or a private network (e.g. Tailscale) rather than
  exposing it directly — see `deploy/firewall-8420.sh` in the repo root for
  an example of verifying that posture.
- Every endpoint that changes state requires `CTB_CONTROL_SECRET` via the
  `X-CTB-Secret` header. Leaving it unset disables those endpoints rather
  than leaving them open, but you should still set it once you expose the
  dashboard beyond localhost.
- `CTB_REVIEW_SECRET` gates the separate `/review` route the same way.

## License

MIT
