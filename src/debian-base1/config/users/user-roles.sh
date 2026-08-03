#!/bin/bash
set -e

usermod -aG teacher testuser

# set mount point for working directory and make sure only the teacher role has access to this
mkdir -p /home/testuser/work
chown testuser:teacher /home/testuser/work
chmod 775 /home/testuser/work

# resource sharing folder for teachers
# permissions: teachers can write, students can only read
mkdir -p /shared/resources
chown root:teacher /shared/resources
chmod 775 /shared/resources

# student work directory
# permissions: only students have access
mkdir -p /home/studentuser/homework
chown studentuser:student /home/studentuser/homework
chmod 755 /home/studentuser/homework

# prevent users from browsing home dirs of all teacher and student users
for grp in student teacher; do
    for user in $(getent group "$grp" 2>/dev/null | cut -d: -f4 | tr ',' ' '); do
        [ -d "/home/$user" ] && chmod 700 "/home/$user"
    done
done

# student submissions folder, teachers can read, students can write
mkdir -p /shared/submissions
chown testuser:teacher /shared/submissions
chmod 1775 /shared/submissions

# teacher-authored lesson packages (published tutorials)
# world-writable so student-agent can unpack synced lesson bodies
mkdir -p /shared/teacher-lessons
chown root:teacher /shared/teacher-lessons
chmod 1777 /shared/teacher-lessons

# classroom networking control / work / delivery / secrets
mkdir -p /shared/cis4900-control /shared/classroom-work /shared/classroom-delivery /shared/cis4900-secrets
chown root:teacher /shared/cis4900-control /shared/classroom-work /shared/classroom-delivery /shared/cis4900-secrets
chmod 775 /shared/cis4900-control /shared/classroom-work /shared/classroom-delivery
chmod 770 /shared/cis4900-secrets

# student state cache — agent (runs as the student) writes student-state.json here
mkdir -p /var/lib/cis4900
chown root:student /var/lib/cis4900
chmod 775 /var/lib/cis4900

echo "Creating convenient symlinks to shared folders..."

# Teacher gets symlinks to shared folders
ln -sf /shared/resources /home/testuser/resources
ln -sf /shared/submissions /home/testuser/submissions

# Student gets symlinks to shared folders
ln -sf /shared/resources /home/studentuser/resources
ln -sf /shared/submissions /home/studentuser/submissions

# Set ownership of symlinks
chown -h testuser:testuser /home/testuser/resources
chown -h testuser:testuser /home/testuser/submissions
chown -h studentuser:studentuser /home/studentuser/resources
chown -h studentuser:studentuser /home/studentuser/submissions

echo "Role-based directories and permissions configured"
echo "Shared folders accessible via symlinks in home directories"

