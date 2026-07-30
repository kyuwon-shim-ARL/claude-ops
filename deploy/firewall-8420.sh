#!/usr/bin/env bash
# Verify the network posture of the ctb-dashboard port (8420).
#
# The dashboard listens on 0.0.0.0 (see BIND_HOST in server.py -- narrowing it
# is deliberately opt-in, because hard-binding an interface that is down at
# boot would loop forever under systemd Restart=always). What actually keeps
# 8420 off the LAN is firewalld, not the bind address:
#
#   trusted zone  <- tailscale0        : 8420 reachable (intended)
#   public  zone  <- eno* (LAN)        : 8420 NOT listed => dropped (intended)
#
# This script only READS the firewall configuration and reports drift. It
# changes nothing: the remediation commands are printed for a human to run,
# because opening or closing host-wide ports affects every service on the box.
#
# Exit codes: 0 = posture as intended, 1 = drift detected, 2 = cannot inspect.

set -uo pipefail

PORT="${CTB_DASHBOARD_PORT:-8420}"
TAILSCALE_IF="${CTB_TAILSCALE_IF:-tailscale0}"

if ! command -v firewall-cmd >/dev/null 2>&1; then
  echo "SKIP: firewall-cmd not found -- this host does not use firewalld."
  echo "      Verify by other means that ${PORT} is not reachable from the LAN."
  exit 2
fi

if ! sudo -n firewall-cmd --state >/dev/null 2>&1; then
  echo "CANNOT INSPECT: firewalld query needs privileges (or firewalld is down)."
  echo "  Run: sudo $0"
  exit 2
fi

drift=0

# 1. The LAN-facing zone must NOT expose the dashboard port.
default_zone="$(sudo -n firewall-cmd --get-default-zone 2>/dev/null)"
lan_ports="$(sudo -n firewall-cmd --zone="${default_zone}" --list-ports 2>/dev/null)"
if printf '%s\n' ${lan_ports} | grep -qx "${PORT}/tcp"; then
  echo "DRIFT: ${PORT}/tcp is open in the LAN-facing '${default_zone}' zone."
  echo "  The dashboard has no authentication on read endpoints and controls"
  echo "  live tmux sessions -- it must not be reachable from the LAN."
  echo "  Remediation:"
  echo "    sudo firewall-cmd --zone=${default_zone} --remove-port=${PORT}/tcp --permanent"
  echo "    sudo firewall-cmd --reload"
  drift=1
else
  echo "OK: ${PORT}/tcp is not open in the LAN-facing '${default_zone}' zone."
fi

# 2. The tailscale interface must be in a zone that permits the dashboard.
ts_zone="$(sudo -n firewall-cmd --get-zone-of-interface="${TAILSCALE_IF}" 2>/dev/null)"
if [ -z "${ts_zone}" ] || [ "${ts_zone}" = "no zone" ]; then
  echo "DRIFT: ${TAILSCALE_IF} is not assigned to any firewalld zone."
  echo "  Remote (iPhone) access to the dashboard will be blocked."
  echo "  Remediation:"
  echo "    sudo firewall-cmd --zone=trusted --change-interface=${TAILSCALE_IF} --permanent"
  echo "    sudo firewall-cmd --reload"
  drift=1
else
  # --get-target only works with --permanent, so read the live target out of
  # --list-all instead (built-in zones like 'trusted' report target: ACCEPT).
  ts_target="$(sudo -n firewall-cmd --zone="${ts_zone}" --list-all 2>/dev/null \
    | awk '$1=="target:"{print $2; exit}')"
  ts_ports="$(sudo -n firewall-cmd --zone="${ts_zone}" --list-ports 2>/dev/null)"
  if [ "${ts_target}" = "ACCEPT" ] || printf '%s\n' ${ts_ports} | grep -qx "${PORT}/tcp"; then
    echo "OK: ${TAILSCALE_IF} is in zone '${ts_zone}' which permits ${PORT}/tcp."
  else
    echo "DRIFT: ${TAILSCALE_IF} is in zone '${ts_zone}' (target=${ts_target}) which"
    echo "  does not permit ${PORT}/tcp. Remote access will be blocked."
    echo "  Remediation:"
    echo "    sudo firewall-cmd --zone=${ts_zone} --add-port=${PORT}/tcp --permanent"
    echo "    sudo firewall-cmd --reload"
    drift=1
  fi
fi

if [ "${drift}" -eq 0 ]; then
  echo "Posture as intended: ${PORT} reachable over ${TAILSCALE_IF} only."
fi
exit "${drift}"
