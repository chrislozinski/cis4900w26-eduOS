#!/usr/bin/env bash
set -euo pipefail

# network manager for wifi usage
mkdir -p /etc/systemd/system/multi-user.target.wants

ln -sf /lib/systemd/system/NetworkManager.service \
    /etc/systemd/system/multi-user.target.wants/NetworkManager.service

# installer service; only ever starts when the kernel cmdline has ychitsa.installer=1
ln -sf /etc/systemd/system/ychitsa-installer.service \
    /etc/systemd/system/multi-user.target.wants/ychitsa-installer.service

# GPU fallback tier system, see build/inject/gpu/
mkdir -p /etc/systemd/system/graphical.target.wants

ln -sf /etc/systemd/system/ychitsa-gpu-stage.service \
    /etc/systemd/system/graphical.target.wants/ychitsa-gpu-stage.service
ln -sf /etc/systemd/system/ychitsa-gpu-confirm.service \
    /etc/systemd/system/graphical.target.wants/ychitsa-gpu-confirm.service
ln -sf /etc/systemd/system/ychitsa-gpu-recover.service \
    /etc/systemd/system/graphical.target.wants/ychitsa-gpu-recover.service

# Seed classrooms.json for publisher (same path as Classroom Manager).
# Prefer /opt/cis4900 seed when present; also seed if classrooms list is empty.
mkdir -p /shared /shared/teacher-lessons
SEED_SRC=""
if [ -f /opt/cis4900/classrooms.json ]; then
    SEED_SRC="/opt/cis4900/classrooms.json"
elif [ -f "/usr/local/share/cis4900-src/src/debian-base1/config/launcher/classrooms.json" ]; then
    SEED_SRC="/usr/local/share/cis4900-src/src/debian-base1/config/launcher/classrooms.json"
fi
need_seed=0
if [ ! -f /shared/classrooms.json ]; then
    need_seed=1
elif ! python3 -c "import json; d=json.load(open('/shared/classrooms.json')); raise SystemExit(0 if d.get('classrooms') else 1)" 2>/dev/null; then
    need_seed=1
fi
if [ "$need_seed" = "1" ] && [ -n "${SEED_SRC}" ] && [ -f "${SEED_SRC}" ]; then
    cp "${SEED_SRC}" /shared/classrooms.json.tmp
    mv -f /shared/classrooms.json.tmp /shared/classrooms.json
fi
if [ -f /shared/classrooms.json ]; then
    chown root:teacher /shared/classrooms.json
    chmod 664 /shared/classrooms.json
fi

# Keep a copy under /var/lib for older tooling; prefer /shared.
# group-student so the student agent can write student-state.json here
mkdir -p /var/lib/cis4900
chown root:student /var/lib/cis4900
chmod 775 /var/lib/cis4900
if [ -f /shared/classrooms.json ] && [ ! -f /var/lib/cis4900/classrooms.json ]; then
    cp /shared/classrooms.json /var/lib/cis4900/classrooms.json
    chown root:teacher /var/lib/cis4900/classrooms.json
    chmod 664 /var/lib/cis4900/classrooms.json
fi

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
