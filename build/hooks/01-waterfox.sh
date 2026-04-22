#!/usr/bin/env bash
set -euo pipefail

WF_VER=$(curl -sf https://api.github.com/repos/BrowserWorks/Waterfox/releases/latest \
    | grep -oP '"tag_name":\s*"\K[^"]+') || WF_VER="6.6.9"
: "${WF_VER:=6.6.9}"

curl -L "https://cdn1.waterfox.net/waterfox/releases/${WF_VER}/Linux_x86_64/waterfox-${WF_VER}.tar.bz2" \
    -o /tmp/waterfox.tar.bz2
tar -xjf /tmp/waterfox.tar.bz2 -C /opt
ln -sf /opt/waterfox/waterfox /usr/local/bin/waterfox
rm /tmp/waterfox.tar.bz2

mkdir -p /opt/waterfox/distribution/extensions
curl -L "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/addon-607454-latest.xpi" \
    -o /opt/waterfox/distribution/extensions/uBlock0@raymondhill.net.xpi
echo '{"policies":{"ExtensionSettings":{"uBlock0@raymondhill.net":{"installation_mode":"force_installed","install_url":"file:///opt/waterfox/distribution/extensions/uBlock0@raymondhill.net.xpi"}}}}' \
    > /opt/waterfox/distribution/policies.json
