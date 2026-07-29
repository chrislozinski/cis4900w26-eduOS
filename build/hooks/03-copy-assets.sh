#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="/usr/local/share/cis4900-src/src/debian-base1"

mkdir -p /etc/skel/.config/i3 /etc/skel/.config/i3status /etc/skel/.config/vifm
mkdir -p /etc/skel/.config/polybar
mkdir -p /etc/skel/.config/launcher/icons /etc/skel/.config/launcher/network
mkdir -p /etc/skel/.config/rofi

cp "${SRC_ROOT}/config/i3/i3-config" /etc/skel/.config/i3/config
cp "${SRC_ROOT}/config/i3/i3status-config" /etc/skel/.config/i3status/config
cp "${SRC_ROOT}/config/i3/layout.json" /etc/skel/.config/i3/layout.json
cp "${SRC_ROOT}/config/i3/polybar-config" /etc/skel/.config/polybar/config.ini
cp "${SRC_ROOT}/config/interface/vifmrc" /etc/skel/.config/vifm/vifmrc
cp "${SRC_ROOT}/config/interface/picom.conf" /etc/skel/.config/picom.conf

cp "${SRC_ROOT}/config/launcher/launcher.py" /etc/skel/.config/launcher/launcher.py
cp "${SRC_ROOT}/config/launcher/folder_viewer.py" /etc/skel/.config/launcher/folder_viewer.py
cp "${SRC_ROOT}/config/launcher/app-window.py" /etc/skel/.config/launcher/app-window.py
cp "${SRC_ROOT}/config/launcher/classroom_manager.py" /etc/skel/.config/launcher/classroom_manager.py
cp "${SRC_ROOT}/widgets/joinClassroom/join-classroom.py" /etc/skel/.config/launcher/join-classroom.py
cp "${SRC_ROOT}/widgets/makecode/makecode-app.py" /etc/skel/.config/launcher/makecode-app.py
cp "${SRC_ROOT}/widgets/fileNav/fileViewer.py" /etc/skel/.config/launcher/fileViewer.py
cp "${SRC_ROOT}/widgets/library/library.py" /etc/skel/.config/launcher/library.py
cp "${SRC_ROOT}/config/launcher/lesson-config.py" /etc/skel/.config/launcher/lesson-config.py
cp "${SRC_ROOT}/config/launcher/waterfox-launcher.sh" /etc/skel/.config/launcher/waterfox-launcher.sh
cp "${SRC_ROOT}/config/launcher/start-audio.sh" /etc/skel/.config/launcher/start-audio.sh
cp "${SRC_ROOT}/config/launcher/webapp-viewer.py" /etc/skel/.config/launcher/webapp-viewer.py
cp "${SRC_ROOT}/config/interface/polybar-hover.py"   /etc/skel/.config/polybar/polybar-hover.py

cp "${SRC_ROOT}/config/launcher/appbar-config.json" /etc/skel/.config/launcher/appbar-config.json
cp "${SRC_ROOT}/config/launcher/appbar-config-teacher.json" /etc/skel/.config/launcher/appbar-config-teacher.json
cp "${SRC_ROOT}/config/launcher/appbar-config-student.json" /etc/skel/.config/launcher/appbar-config-student.json
cp "${SRC_ROOT}/config/launcher/classrooms.json" /etc/skel/.config/launcher/classrooms.json
cp "${SRC_ROOT}/config/launcher/available-apps.json" /etc/skel/.config/launcher/available-apps.json

cp -r "${SRC_ROOT}/icons/stylized" /etc/skel/.config/launcher/icons/
cp -r "${SRC_ROOT}/icons/light" /etc/skel/.config/launcher/icons/
cp -r "${SRC_ROOT}/icons/dark" /etc/skel/.config/launcher/icons/

cp "${SRC_ROOT}/network/"*.py /etc/skel/.config/launcher/network/
mkdir -p /etc/skel/.config/launcher/network/docs
cp "${SRC_ROOT}/network/docs/"*.md /etc/skel/.config/launcher/network/docs/ 2>/dev/null || true
# Also install network package for systemd WorkingDirectory imports
mkdir -p /usr/local/share/cis4900-src/src/debian-base1/network/docs
cp "${SRC_ROOT}/network/"*.py /usr/local/share/cis4900-src/src/debian-base1/network/ 2>/dev/null || true
cp "${SRC_ROOT}/network/docs/"*.md /usr/local/share/cis4900-src/src/debian-base1/network/docs/ 2>/dev/null || true

cp "${SRC_ROOT}/config/users/create-users.sh" /usr/local/bin/create-users.sh
cp "${SRC_ROOT}/config/users/user-roles.sh" /usr/local/bin/user-roles.sh
cp "${SRC_ROOT}/config/users/config-user-i3.sh" /usr/local/bin/config-user-i3.sh
cp "${SRC_ROOT}/config/interface/config-vifm.sh" /usr/local/bin/config-vifm.sh
cp "${SRC_ROOT}/config/interface/config-gtk.sh" /usr/local/bin/config-gtk.sh
cp "${SRC_ROOT}/config/launcher/config-launcher.sh" /usr/local/bin/config-launcher.sh
cp "${SRC_ROOT}/config/launcher/wifi-connect.sh"   /usr/local/bin/wifi-connect.sh

mkdir -p /etc/skel/.config/dunst
cp "${SRC_ROOT}/config/interface/notifications.conf" /etc/skel/.config/dunst/dunstrc
cp "${SRC_ROOT}/config/interface/rofi-config.rasi" /etc/skel/.config/rofi/config.rasi

mkdir -p /opt/makecode
cp -r "${SRC_ROOT}/widgets/makecode/makecode-static" /opt/makecode/static

mkdir -p /opt/cis4900/widgets/lessonBuilder
cp -r "${SRC_ROOT}/widgets/lessonBuilder/." /opt/cis4900/widgets/lessonBuilder/
chmod +x /opt/cis4900/widgets/lessonBuilder/*.py

mkdir -p /etc/systemd/system
if [ -d "${SRC_ROOT}/config/systemd" ]; then
  cp "${SRC_ROOT}/config/systemd/"*.service /etc/systemd/system/ 2>/dev/null || true
fi

if [ -d "${SRC_ROOT}/network/services" ]; then
  cp "${SRC_ROOT}/network/services/"*.service /etc/systemd/system/ 2>/dev/null || true
fi

cp "${SRC_ROOT}/config/updateManager/ychitsa-update" /usr/local/bin/ychitsa-update
cp "${SRC_ROOT}/network/student-agent-session.sh" /usr/local/bin/student-agent-session.sh

chmod +x /usr/local/bin/create-users.sh /usr/local/bin/user-roles.sh /usr/local/bin/config-user-i3.sh
chmod +x /usr/local/bin/config-vifm.sh /usr/local/bin/config-gtk.sh /usr/local/bin/config-launcher.sh
chmod +x /usr/local/bin/wifi-connect.sh /usr/local/bin/ychitsa-update /usr/local/bin/student-agent-session.sh
chmod +x /etc/skel/.config/launcher/*.py /etc/skel/.config/launcher/*.sh
chmod +x /etc/skel/.config/launcher/network/*.py
