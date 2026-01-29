#!/bin/bash
set -e

# Function to set up vifm configuration for a user
setup_vifm_for_user() {
    local username=$1
    local home_dir="/home/$username"
    
    # Create vifm config directory
    mkdir -p "$home_dir/.config/vifm"
    
    cp /etc/skel/.config/vifm/vifmrc "$home_dir/.config/vifm/vifmrc"
    
    # Set proper ownership
    chown -R "$username:$username" "$home_dir/.config/vifm"
    
    echo "Configured vifm for user: $username"
}

# Get list of all regular users (UID >= 1000)
users=$(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd)

# Configure vifm for each user
for user in $users; do
    setup_vifm_for_user "$user"
done

echo "vifm configuration completed for all users"