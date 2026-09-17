#!/bin/bash
# Start the Claude-CTB bridge: the session monitor and the Telegram bot.
#
# Both live in ONE process. `claude_ctb.monitoring.multi_monitor`'s main()
# starts the monitoring thread and then runs the bot, and `claude_ctb.telegram.bot`
# is the bot on its own -- run both and you get two pollers fighting over
# getUpdates, which the Telegram API answers with 409 Conflict. Whichever poll
# wins receives the message; the other loses it.
#
# systemd owns it now, so it comes back after a reboot and after a crash
# (Restart=on-failure). This script is the reminder of where it lives, not a
# second way to start it: what it used to do -- launch a tmux session running a
# module path that no longer exists -- would have started a SECOND bridge
# beside the service.

set -e

UNIT=claude-telegram-bridge

case "${1:-status}" in
  start|restart)
    systemctl --user restart "$UNIT"
    sleep 2
    systemctl --user status "$UNIT" --no-pager | head -5
    ;;
  stop)
    systemctl --user stop "$UNIT"
    ;;
  status)
    systemctl --user status "$UNIT" --no-pager | head -12
    echo
    echo "logs:  tail -f logs/multi_monitor.log"
    echo "start: $0 start    (or: systemctl --user restart $UNIT)"
    ;;
  logs)
    tail -f logs/multi_monitor.log
    ;;
  *)
    echo "usage: $0 [start|restart|stop|status|logs]" >&2
    exit 2
    ;;
esac
