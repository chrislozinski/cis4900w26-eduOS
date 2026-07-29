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

    # students get the sync agent autostarted in their session
    if id -nG "$username" | grep -qw student; then
        printf '\nexec --no-startup-id /usr/local/bin/student-agent-session.sh\n' \
            >> "$home_dir/.config/i3/config"
    fi

    chown -R "$username:$username" "$home_dir/.config"

    # write .xsession — XDG_RUNTIME_DIR and session D-Bus must be set before i3 starts
    # so every child process (pipewire, wireplumber, webkit2, gstreamer) inherits both
    # /etc/cis4900-env bridges container env (TEACHER_IP) into the session; xrdp-sesman
    # strips daemon env vars, so GUI apps only see what .xsession sources. Absent on ISO.
    printf '#!/bin/bash\n[ -f /etc/cis4900-env ] && . /etc/cis4900-env\nexport XDG_RUNTIME_DIR="/run/user/$(id -u)"\nmkdir -p "$XDG_RUNTIME_DIR"\nchmod 700 "$XDG_RUNTIME_DIR"\nexport GDK_SCALE=1\nexport GDK_DPI_SCALE=1.0\necho "Xft.dpi: 96" | xrdb -merge -\nexec dbus-launch --exit-with-session i3\n' \
        > "$home_dir/.xsession"
    chmod +x "$home_dir/.xsession"
    chown "$username:$username" "$home_dir/.xsession"

    mkdir -p "$home_dir/.config/dunst"
    cp /etc/skel/.config/dunst/dunstrc "$home_dir/.config/dunst/dunstrc"
    
    echo "configured i3 for user: $username"
}

users=$(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd)

for user in $users; do
    setup_i3_for_user "$user"
done

echo "i3 config completed for all users"