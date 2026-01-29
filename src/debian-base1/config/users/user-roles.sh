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

# student submissions folder 
# permissions: teachers can read, students can write
mkdir -p /shared/submissions
chown testuser:teacher /shared/submissions
chmod 1775 /shared/submissions

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

