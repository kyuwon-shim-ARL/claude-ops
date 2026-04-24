# Phase 1 Smoke Test Checklist

Manual verification steps before promoting to production.
All items must pass before merging `worktree-ctb-dashboard` → `main`.

## Environment

```bash
export CTB_REVIEW_SECRET="$(openssl rand -hex 32)"
export CTB_REVIEW_OVERLAY_DIR="$HOME/.claude-ops"
export SESSION_SECRET_KEY="$(openssl rand -hex 32)"
mkdir -p "$CTB_REVIEW_OVERLAY_DIR"
cp .env.example .env  # fill in TELEGRAM_BOT_TOKEN if escalation test needed
uv run uvicorn ctb_dashboard.server:app --port 8765
```

## Checklist

### S1 – Dashboard loads with CSP nonce

- [ ] `curl -si http://localhost:8765/ | grep content-security-policy` → header present, contains `nonce-`
- [ ] Browser devtools: no CSP violations in console

### S2 – Card template renders

- [ ] `GET /dev/cards` returns 200 with at least one card skeleton

### S3 – Ticket enrichment + lifespan DI

- [ ] `GET /healthz` returns `{"status":"ok"}` within 5s of startup
- [ ] `GET /api/sessions/stream` opens SSE connection (no 500)

### S4 – ReviewController state transitions

- [ ] Python REPL: create `ReviewController`, call `mark_needs_review("smoke-1")`, confirm overlay written
- [ ] `approve("smoke-1", "kyuwon-shim")` transitions to `in_progress`
- [ ] `InvalidReviewTransition` raised on illegal transition (e.g., approve from `planned`)

### S5 – Reject draft (Haiku)

- [ ] `reject("smoke-1", "kyuwon-shim", verdict_choice="needs_work")` succeeds
- [ ] After ~5s, overlay shows `reject_draft` field populated (or `null` on timeout)

### S6 – `/review` HMAC gate

- [ ] Unsigned request → 403
- [ ] Expired link (exp in past) → 403
- [ ] Valid HMAC link → 200, reviewer session cookie set
- [ ] Replay same link → 403
- [ ] Link issued before `needs_review_since` (old cycle) → 403

### S7 – Email dispatch (reviewers.yaml)

```bash
cat > "$CTB_REVIEW_OVERLAY_DIR/reviewers.yaml" <<EOF
kyuwon-shim:
  email: kyuwon.shim@ip-korea.org
  name: Kyuwon Shim
EOF
```

- [ ] `dispatch_review_notification("smoke-1", ["kyuwon-shim"], "http://localhost:8765/review?...")` returns `{"kyuwon-shim": "sent"}`
- [ ] Email received at `kyuwon.shim@ip-korea.org` with correct review link

### S8 – Escalation loop skips non-failing tickets

- [ ] Ticket with `reviewer_statuses: {"kyuwon-shim": "sent"}` is NOT escalated after 24h
- [ ] Ticket with `reviewer_statuses: {"kyuwon-shim": "failed"}` IS escalated (Telegram message received)

### S9 – Purge loop cleans old consumed links

- [ ] Manually insert entry with `consumed_at` > 7 days ago into `consumed-links.json`
- [ ] After purge loop fires (or call `_purge_consumed_loop` directly), old entry removed

### S10 – Rollback on overlay write failure (H11)

- [ ] Temporarily make overlay unwritable: `chmod 000 "$CTB_REVIEW_OVERLAY_DIR/ticket-overlay.json"`
- [ ] Hit `/review` with valid link → 503
- [ ] `consumed-links.json` shows `write-failed` for that sig (not `consumed`)
- [ ] Restore permissions, retry same link → 200
- [ ] `chmod 644 "$CTB_REVIEW_OVERLAY_DIR/ticket-overlay.json"`

### S11 – Full review cycle (approve path)

- [ ] Ticket starts in `planned`
- [ ] `mark_needs_review` → email sent → reviewer clicks HMAC link → `/review` renders ticket
- [ ] Reviewer approves → ticket moves to `in_progress`
- [ ] History contains `approved` + `in_progress` entries with correct timestamps
