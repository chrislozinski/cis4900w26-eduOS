#!/usr/bin/env bash
set -euo pipefail

# network manager for wifi usage 
mkdir -p /etc/systemd/system/multi-user.target.wants

ln -sf /lib/systemd/system/NetworkManager.service \
    /etc/systemd/system/multi-user.target.wants/NetworkManager.service

mkdir -p /var/lib/cis4900
chown root:teacher /var/lib/cis4900
chmod 775 /var/lib/cis4900

# Seed classrooms.json from the build-time source copy.
# On a live ISO this is the initial state; teachers update it via classroom_manager.
SEED_SRC="/usr/local/share/cis4900-src/src/debian-base1/config/launcher/classrooms.json"
if [ -f "${SEED_SRC}" ] && [ ! -f /var/lib/cis4900/classrooms.json ]; then
    cp "${SEED_SRC}" /var/lib/cis4900/classrooms.json
fi
chown root:teacher /var/lib/cis4900/classrooms.json
chmod 664 /var/lib/cis4900/classrooms.json

# Service files copied to /etc/systemd/system/ by 03-copy-assets.sh
# teacher service
if [ -f /etc/systemd/system/teacher-publisher.service ]; then
    ln -sf /etc/systemd/system/teacher-publisher.service \
        /etc/systemd/system/multi-user.target.wants/teacher-publisher.service
fi

# student service
# Iterates the student group so this works for any number of student accounts.
if [ -f /etc/systemd/system/student-agent@.service ]; then
    for username in $(getent group student | cut -d: -f4 | tr ',' ' '); do
        [ -z "${username}" ] && continue
        ln -sf /etc/systemd/system/student-agent@.service \
            "/etc/systemd/system/multi-user.target.wants/student-agent@${username}.service"
        echo "Enabled student-agent@${username}.service"
    done
fi
