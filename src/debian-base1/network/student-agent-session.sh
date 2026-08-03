#!/bin/bash
# Session-scoped student sync agent. Started by i3 (students only) and by
# Join Classroom after a successful join. Safe to call twice: dedupes itself.
if pgrep -u "$(id -un)" -f "network\.agent" >/dev/null 2>&1; then
    exit 0
fi
JOIN="$HOME/.config/cis4900/join.json"
if [ -z "${TEACHER_IP:-}" ] && [ ! -f "$JOIN" ]; then
    exit 0   # not joined yet and no override — nothing to sync against
fi
# Docker keeps the network package at /opt/cis4900; the ISO keeps it where
# the systemd units run from. Use whichever exists.
for root in /opt/cis4900 /usr/local/share/cis4900-src/src/debian-base1; do
    if [ -d "$root/network" ]; then
        cd "$root" && exec python3 -m network.agent --student-id="$(id -un)"
    fi
done
exit 0
