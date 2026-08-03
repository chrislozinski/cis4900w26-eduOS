#!/bin/bash
set -e

# This function is to set up the side bar launcher for whichever user is logging into the machine 
setup_launcher_for_user() {
    local username=$1
    local home_dir="/home/$username"
    
    echo "setting up launcher for: $username"
    
    # launcher config directory
    mkdir -p "$home_dir/.config/launcher/icons"
    
    cp /etc/skel/.config/launcher/launcher.py              "$home_dir/.config/launcher/launcher.py"
    cp /etc/skel/.config/launcher/folder_viewer.py         "$home_dir/.config/launcher/folder_viewer.py"
    cp /etc/skel/.config/launcher/app-window.py            "$home_dir/.config/launcher/app-window.py"
    cp /etc/skel/.config/launcher/classroom_manager.py     "$home_dir/.config/launcher/classroom_manager.py"
    cp /etc/skel/.config/launcher/join-classroom.py        "$home_dir/.config/launcher/join-classroom.py"
    cp /etc/skel/.config/launcher/makecode-app.py          "$home_dir/.config/launcher/makecode-app.py"
    cp /etc/skel/.config/launcher/library.py               "$home_dir/.config/launcher/library.py"
    cp /etc/skel/.config/launcher/tray_indicators.py       "$home_dir/.config/launcher/tray_indicators.py"
    cp /etc/skel/.config/launcher/lesson-config.py         "$home_dir/.config/launcher/lesson-config.py"
    cp /etc/skel/.config/launcher/waterfox-launcher.sh     "$home_dir/.config/launcher/waterfox-launcher.sh"
    cp /etc/skel/.config/launcher/wifi-connect.sh          "$home_dir/.config/launcher/wifi-connect.sh"
    mkdir -p "$home_dir/.config/launcher/network"
    if [ -d "/etc/skel/.config/launcher/network" ]; then
        cp -r /etc/skel/.config/launcher/network/* "$home_dir/.config/launcher/network/" 2>/dev/null || true
    fi

    # sidebar configs, role resolved at runtime by launcher.py
    cp /etc/skel/.config/launcher/appbar-config.json          "$home_dir/.config/launcher/appbar-config.json"
    cp /etc/skel/.config/launcher/appbar-config-teacher.json  "$home_dir/.config/launcher/appbar-config-teacher.json"
    cp /etc/skel/.config/launcher/appbar-config-student.json  "$home_dir/.config/launcher/appbar-config-student.json"
    cp /etc/skel/.config/launcher/available-apps.json         "$home_dir/.config/launcher/available-apps.json"
    cp /etc/skel/.config/launcher/webapp-viewer.py            "$home_dir/.config/launcher/webapp-viewer.py"
    
    # directory for all the option icons 
    if [ -d "/etc/skel/.config/launcher/icons" ]; then
        cp -r /etc/skel/.config/launcher/icons/* "$home_dir/.config/launcher/icons/" 2>/dev/null || true
    fi
    
    # add the username of the person logging in to the generic fallback config
    sed -i "s|/home/USER|$home_dir|g" "$home_dir/.config/launcher/appbar-config.json"
    
    chmod +x "$home_dir/.config/launcher/launcher.py"
    chmod +x "$home_dir/.config/launcher/folder_viewer.py"
    chmod +x "$home_dir/.config/launcher/app-window.py"
    chmod +x "$home_dir/.config/launcher/classroom_manager.py"
    chmod +x "$home_dir/.config/launcher/join-classroom.py"
    chmod +x "$home_dir/.config/launcher/makecode-app.py"
    chmod +x "$home_dir/.config/launcher/webapp-viewer.py"
    chmod +x "$home_dir/.config/launcher/library.py"
    chmod +x "$home_dir/.config/launcher/lesson-config.py"
    chmod +x "$home_dir/.config/launcher/waterfox-launcher.sh"
    chmod +x "$home_dir/.config/launcher/wifi-connect.sh"
    if [ -d "$home_dir/.config/launcher/network" ]; then
        chmod +x "$home_dir/.config/launcher/network/"*.py 2>/dev/null || true
    fi
    
    #  Documents directory 
    mkdir -p "$home_dir/Documents"
    
    # set directory ownership
    chown -R "$username:$username" "$home_dir/.config/launcher"
    chown -R "$username:$username" "$home_dir/Documents"
    
    echo "Launcher configured for: $username"
}

# /shared/classrooms.json, live DB. Seed from /opt (survives Docker volume overlay).
bootstrap_shared_classrooms() {
    mkdir -p /shared /shared/teacher-lessons \
        /shared/cis4900-control /shared/classroom-work \
        /shared/classroom-delivery /shared/cis4900-secrets 2>/dev/null || true

    local need_seed=0
    if [ ! -f /shared/classrooms.json ]; then
        need_seed=1
    else
        # Empty classrooms list counts as needs seed (volume overlay of empty/broken file)
        if ! python3 -c "import json; d=json.load(open('/shared/classrooms.json')); raise SystemExit(0 if d.get('classrooms') else 1)" 2>/dev/null; then
            need_seed=1
        fi
    fi

    if [ "$need_seed" = "1" ]; then
        local src=""
        if [ -f /opt/cis4900/classrooms.json ]; then
            src=/opt/cis4900/classrooms.json
        elif [ -f /etc/skel/.config/launcher/classrooms.json ]; then
            src=/etc/skel/.config/launcher/classrooms.json
        fi
        if [ -n "$src" ]; then
            tmp=/shared/classrooms.json.tmp
            cp "$src" "$tmp"
            mv -f "$tmp" /shared/classrooms.json
            echo "Seeded /shared/classrooms.json from $src"
        else
            tmp=/shared/classrooms.json.tmp
            echo '{"classrooms":[{"id":"class001","name":"Class 001","students":["studentuser"],"enabled_apps":[],"enabled_lessons":[]}],"web_apps":[]}' > "$tmp"
            mv -f "$tmp" /shared/classrooms.json
            echo "Seeded /shared/classrooms.json with minimal default"
        fi
    fi

    chown root:teacher /shared/classrooms.json 2>/dev/null || true
    chmod 664 /shared/classrooms.json 2>/dev/null || true
}

bootstrap_shared_classrooms

# config launcher for all users
users=$(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd)

for user in $users; do
    setup_launcher_for_user "$user"
done

echo "Sidebar configured for all users"

# Optional: if state-sync units are present in the image, install and enable them.
if [ -d /etc/skel/.config/launcher/systemd ]; then
    cp /etc/skel/.config/launcher/systemd/*.service /etc/systemd/system/ 2>/dev/null || true
fi
if [ -f /etc/systemd/system/student-state-agent.service ]; then
    mkdir -p /etc/systemd/system/multi-user.target.wants
    ln -sf /etc/systemd/system/student-state-agent.service /etc/systemd/system/multi-user.target.wants/student-state-agent.service
fi
if [ -f /etc/systemd/system/teacher-state-publisher.service ]; then
    mkdir -p /etc/systemd/system/multi-user.target.wants
    ln -sf /etc/systemd/system/teacher-state-publisher.service /etc/systemd/system/multi-user.target.wants/teacher-state-publisher.service
fi