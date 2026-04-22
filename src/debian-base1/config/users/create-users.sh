#!/bin/bash
set -e

# create a user with specified role
create_user() {
    local username=$1
    local password=$2
    local role=$3
    
    # Create user
    useradd -m "$username" -p "$(openssl passwd "$password")"
    
    # i3 session
    echo "exec i3" > "/home/$username/.xsession"
    chown "$username:$username" "/home/$username/.xsession"
    
    # Add to role group and audio group
    usermod -aG "$role",audio "$username"
    
    echo "Created user: $username with role: $role"
}

# Teacher user 
create_user "testuser" "1234" "teacher"
usermod -aG sudo testuser

# Student user 
create_user "studentuser" "1234" "student"

echo "User creation completed"