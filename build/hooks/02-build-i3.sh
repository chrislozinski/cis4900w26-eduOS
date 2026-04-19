#!/usr/bin/env bash
set -euo pipefail

# Skip compilation if a cached binary was injected via includes.chroot
if [[ -x /usr/local/bin/i3 ]]; then
    echo "Cached i3 binary found — skipping compilation."
    exit 0
fi

BUILD_DEPS="build-essential pkg-config meson ninja-build \
    libxcb1-dev libxcb-util0-dev libxcb-keysyms1-dev libxcb-icccm4-dev \
    libxcb-randr0-dev libxcb-xinerama0-dev libxcb-shape0-dev \
    libxcb-xkb-dev libxcb-xrm-dev libxcb-cursor-dev \
    libev-dev libyajl-dev libstartup-notification0-dev \
    libpango1.0-dev libxkbcommon-dev libxkbcommon-x11-dev"

apt-get install -y --no-install-recommends ${BUILD_DEPS}

git clone --depth=1 https://github.com/i3/i3.git /tmp/i3-build
cd /tmp/i3-build

# Patch 1: make tab decoration height 0 so the tab strip is invisible
sed -i 's/params\.deco_height = render_deco_height();/params.deco_height = 0;/' src/render.c

# Patch 2: disable mouse drag resize between split containers
python3 -c "
import re
src = open('src/resize.c').read()
src = re.sub(r'(void resize_graphical_handler\b[^{]*\{)', r'\1\n    return;', src)
open('src/resize.c', 'w').write(src)
"

# Patch 3: lock resize cursor to normal pointer
sed -i 's/xcursor_set_canvas_cursor(XCURSOR_CURSOR_RESIZE_HORIZONTAL);/xcursor_set_canvas_cursor(XCURSOR_CURSOR_POINTER);/' src/x.c
sed -i 's/xcursor_set_canvas_cursor(XCURSOR_CURSOR_RESIZE_VERTICAL);/xcursor_set_canvas_cursor(XCURSOR_CURSOR_POINTER);/' src/x.c

meson setup build
ninja -C build

cp build/i3 /usr/local/bin/i3
chmod +x /usr/local/bin/i3

cd /
rm -rf /tmp/i3-build

apt-get purge -y --auto-remove ${BUILD_DEPS}
apt-get clean
