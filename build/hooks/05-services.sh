#!/usr/bin/env bash
set -euo pipefail

mkdir -p /etc/systemd/system/multi-user.target.wants

ln -sf /lib/systemd/system/NetworkManager.service \
    /etc/systemd/system/multi-user.target.wants/NetworkManager.service

if [ -f /etc/systemd/system/student-state-agent.service ]; then
  ln -sf /etc/systemd/system/student-state-agent.service /etc/systemd/system/multi-user.target.wants/student-state-agent.service
fi

if [ -f /etc/systemd/system/teacher-state-publisher.service ]; then
  ln -sf /etc/systemd/system/teacher-state-publisher.service /etc/systemd/system/multi-user.target.wants/teacher-state-publisher.service
fi
