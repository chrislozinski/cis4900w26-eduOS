#!/usr/bin/env bash
# Start the CIS4900 teacher state publisher.
# Live ISO called by systemd service
#   systemctl start teacher-publisher
#
# Docker (host networking required for mDNS/UDP):
#   docker compose up
#   or: docker run --network host ...
#
# Env vars (all optional):
#   CIS4900_STATE_SECRET      shared HMAC fallback (prefer per-classroom secrets)
#   CIS4900_CLASSROOMS_FILE   path to classrooms.json (default /shared/classrooms.json)
#   CIS4900_IFACE             network interface to broadcast on (e.g. wlan0)
#   CIS4900_DEV=1             allow lab use of default secret

: "${CIS4900_CLASSROOMS_FILE:=/shared/classrooms.json}"
: "${CIS4900_STATE_SECRET:=cis4900-dev-secret}"

cd /opt/cis4900
python3 -c "from network.bootstrap import ensureSharedClassrooms; ensureSharedClassrooms()" || true
exec python3 -m network.publisher "$@"
