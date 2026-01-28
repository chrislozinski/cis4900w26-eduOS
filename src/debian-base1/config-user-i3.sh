#!/bin/bash
set -e

# i3 configuration for a user
setup_i3_for_user() {
    local username=$1
    local home_dir="/home/$username"
    
    # create i3 config dir
    mkdir -p "$home_dir/.config/i3"
    mkdir -p "$home_dir/.config/i3status"
    
    # copy i3 config files
    cp /etc/skel/.config/i3/config "$home_dir/.config/i3/config"
    cp /etc/skel/.config/i3status/config "$home_dir/.config/i3status/config"
    
    # user ownership
    chown -R "$username:$username" "$home_dir/.config"
    
    echo "configed i3 for user: $username"
}

# list of all regular users 
users=$(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd)

# anddd config i3 for each 
for user in $users; do
    setup_i3_for_user "$user"
done

echo "i3 config completed for all users"