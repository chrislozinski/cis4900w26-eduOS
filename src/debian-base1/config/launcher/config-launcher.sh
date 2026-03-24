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
    cp /etc/skel/.config/launcher/makecode-app.py          "$home_dir/.config/launcher/makecode-app.py"
    cp /etc/skel/.config/launcher/library.py               "$home_dir/.config/launcher/library.py"
    cp /etc/skel/.config/launcher/lesson-config.py         "$home_dir/.config/launcher/lesson-config.py"
    cp /etc/skel/.config/launcher/waterfox-launcher.sh     "$home_dir/.config/launcher/waterfox-launcher.sh"

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
    chmod +x "$home_dir/.config/launcher/makecode-app.py"
    chmod +x "$home_dir/.config/launcher/webapp-viewer.py"
    chmod +x "$home_dir/.config/launcher/library.py"
    chmod +x "$home_dir/.config/launcher/lesson-config.py"
    chmod +x "$home_dir/.config/launcher/waterfox-launcher.sh"
    
    #  Documents directory 
    mkdir -p "$home_dir/Documents"
    
    # set directory ownership
    chown -R "$username:$username" "$home_dir/.config/launcher"
    chown -R "$username:$username" "$home_dir/Documents"
    
    echo "Launcher configured for: $username"
}

# /shared/classrooms.json
# Created once with the seed file, teachers edit it live with the classroom_manager.py app
if [ ! -f /shared/classrooms.json ]; then
    if [ -f /etc/skel/.config/launcher/classrooms.json ]; then
        cp /etc/skel/.config/launcher/classrooms.json /shared/classrooms.json
    else
        echo '{"classrooms":[{"id":"class001","name":"Class 001","students":[],"enabled_apps":[]}]}' \
            > /shared/classrooms.json
    fi
    chown root:teacher /shared/classrooms.json
    chmod 664 /shared/classrooms.json   # teacher group can read/write
    echo "Created /shared/classrooms.json"
fi

# config launcher for all users
users=$(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd)

for user in $users; do
    setup_launcher_for_user "$user"
done

echo "Sidebar configured for all users"