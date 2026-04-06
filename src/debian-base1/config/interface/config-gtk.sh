#!/bin/bash
set -e
# config file to hide and set certain directories for users in the default gtk file chooser app

# bookmarks are the shortcuts shown in the file choosers left panel
# the option to "show-hidden false" hides dotfiles and then 
# startup-mode cwd opens in current dir rather than root

setup_gtk_for_user() {
    local username=$1
    local home_dir="/home/$username"

    # create gtk config dir
    mkdir -p "$home_dir/.config/gtk-3.0"

    # write sidebar bookmarks using a command group redirect
    {
        echo "file:///home/$username Documents"
        echo "file:///home/$username/homework Homework"
        echo "file:///shared/resources Resources"
        echo "file:///shared/submissions Submissions"
    } > "$home_dir/.config/gtk-3.0/bookmarks"

    # set ownership
    chown -R "$username:$username" "$home_dir/.config/gtk-3.0"

    # apply file chooser settings
    su - "$username" -c "
        gsettings set org.gtk.Settings.FileChooser show-hidden false
        gsettings set org.gtk.Settings.FileChooser startup-mode cwd
    " 2>/dev/null || true
}

# run for all non-system users
users=$(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd)

for user in $users; do
    setup_gtk_for_user "$user"
done

echo "GTK file chooser configured for all users"