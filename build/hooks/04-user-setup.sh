#!/usr/bin/env bash
set -euo pipefail

groupadd -f teacher
groupadd -f student

/usr/local/bin/create-users.sh
/usr/local/bin/user-roles.sh
/usr/local/bin/config-user-i3.sh
/usr/local/bin/config-vifm.sh
/usr/local/bin/config-gtk.sh
/usr/local/bin/config-launcher.sh
