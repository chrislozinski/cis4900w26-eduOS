#!/usr/bin/env bash
# Start the CIS4900 teacher state publisher.
# Live ISO called by systemd service
#   systemctl start teacher-publisher
#
# Docker (run this after the container is up):
#   docker exec <container> /opt/cis4900/network.sh
#   docker run --network host <image> /opt/cis4900/network.sh
#
# Env vars (all optional):
#   CIS4900_STATE_SECRET      shared HMAC secret (default: cis4900-dev-secret)
#   CIS4900_CLASSROOMS_FILE   path to classrooms.json
#   CIS4900_IFACE             network interface to broadcast on (e.g. wlan0)

: "${CIS4900_CLASSROOMS_FILE:=/opt/cis4900/classrooms.json}"
: "${CIS4900_STATE_SECRET:=cis4900-dev-secret}"

cd /opt/cis4900
exec python3 -m network.publisher "$@"