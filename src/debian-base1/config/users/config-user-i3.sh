#!/bin/bash
set -e

setup_i3_for_user() {
    local username=$1
    local home_dir="/home/$username"
    
    mkdir -p "$home_dir/.config/i3"
    mkdir -p "$home_dir/.config/i3status"
    mkdir -p "$home_dir/.config/vifm"
    
    cp /etc/skel/.config/i3/config "$home_dir/.config/i3/config"
    cp /etc/skel/.config/i3status/config "$home_dir/.config/i3status/config"
    cp /etc/skel/.config/vifm/vifmrc "$home_dir/.config/vifm/vifmrc"
    cp /etc/skel/.config/picom.conf "$home_dir/.config/picom.conf"
    
    chown -R "$username:$username" "$home_dir/.config"
    
    echo "configured i3 for user: $username"
}

users=$(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd)

for user in $users; do
    setup_i3_for_user "$user"
done

echo "i3 config completed for all users"