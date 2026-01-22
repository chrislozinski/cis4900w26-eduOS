#!/bin/bash
set -e

# creating a role group for teachers and adding the test user to ut
groupadd teacher
usermod -aG teacher testuser

# set mount point for working directory and make sure only the teacher role has access to this
mkdir -p /home/testuser/work
chown testuser:teacher /home/testuser/work
chmod 775 /home/testuser/work