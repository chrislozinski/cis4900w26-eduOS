# build patched i3 
FROM debian:stable AS i3-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git build-essential pkg-config meson ninja-build \
    libxcb1-dev libxcb-util0-dev libxcb-keysyms1-dev libxcb-icccm4-dev \
    libxcb-randr0-dev libxcb-xinerama0-dev libxcb-shape0-dev \
    libxcb-xkb-dev libxcb-xrm-dev libxcb-cursor-dev \
    libev-dev libyajl-dev libstartup-notification0-dev \
    libpango1.0-dev libxkbcommon-dev libxkbcommon-x11-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 https://github.com/i3/i3.git /i3

WORKDIR /i3

#  set deco_height to 0 so tab decorations are invisible
RUN sed -i 's/params\.deco_height = render_deco_height();/params.deco_height = 0;/' src/render.c

# Disable mouse drag resize between split containers
RUN python3 -c "import re; src=open('src/resize.c').read(); src=re.sub(r'(void resize_graphical_handler\b[^{]*\{)', r'\1\n    return;', src); open('src/resize.c','w').write(src)"

# Force the resize cursor to stay as a normal pointer
RUN sed -i 's/xcursor_set_canvas_cursor(XCURSOR_CURSOR_RESIZE_HORIZONTAL);/xcursor_set_canvas_cursor(XCURSOR_CURSOR_POINTER);/' src/x.c && \
    sed -i 's/xcursor_set_canvas_cursor(XCURSOR_CURSOR_RESIZE_VERTICAL);/xcursor_set_canvas_cursor(XCURSOR_CURSOR_POINTER);/' src/x.c

RUN meson setup build && ninja -C build

# debootstrap minimal Debian base
# This is loosely based on the documentation found here:
# https://github.com/coolmagnet/Debootstrap?tab=readme-ov-file
# but has been modified to work with docker specifically 

FROM debian:stable AS builder
RUN apt-get update && apt-get install -y debootstrap
RUN debootstrap --variant=minbase stable /stable-chroot http://deb.debian.org/debian/

FROM scratch
COPY --from=builder /stable-chroot /

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    i3-wm \
    i3status \
    py3status \
    suckless-tools \
    xrdp \
    xorg \
    xorgxrdp \
    x11-xserver-utils \
    dbus \
    dbus-x11 \
    sudo \
    openssl \
    tini \
    xterm \
    curl \
    wget \
    git \
    vim \
    nano \
    python3 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    gir1.2-webkit2-4.1 \
    vifm \
    zathura \
    zathura-pdf-poppler \
    nsxiv \
    libdbus-glib-1-2 \
    libxt6 \
    bzip2 \
    picom \
    polybar \
    fonts-font-awesome \
    && apt-get install -y --no-install-recommends \
    pipewire \
    pipewire-pulse \
    wireplumber \
    pulseaudio-utils \
    gstreamer1.0-pipewire \
    gstreamer1.0-libav \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-tools \
    dunst \
    libnotify-bin \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# pipewire-module-xrdp is in bookworm-backports, bridges PipeWire audio to xrdp
RUN echo "deb http://deb.debian.org/debian bookworm-backports main" >> /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y -t bookworm-backports pipewire-module-xrdp \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# MakeCode static editor using the pre built HTML/JS/CSS to avoid runtime deps 
COPY widgets/makecode/makecode-static/ /opt/makecode/static/

# Install Waterfox (teacher browser), fetch latest version from GitHub releases 
RUN WF_VER=$(curl -sf https://api.github.com/repos/BrowserWorks/Waterfox/releases/latest \
        | grep -oP '"tag_name":\s*"\K[^"]+') \
    && : "${WF_VER:=6.6.9}" \
    && curl -L "https://cdn1.waterfox.net/waterfox/releases/${WF_VER}/Linux_x86_64/waterfox-${WF_VER}.tar.bz2" \
       -o /tmp/waterfox.tar.bz2 \
    && tar -xjf /tmp/waterfox.tar.bz2 -C /opt \
    && ln -sf /opt/waterfox/waterfox /usr/local/bin/waterfox \
    && rm /tmp/waterfox.tar.bz2

# Install uBlock Origin as a force-installed system extension for Waterfox
RUN mkdir -p /opt/waterfox/distribution/extensions \
    && curl -L "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/addon-607454-latest.xpi" \
       -o /opt/waterfox/distribution/extensions/uBlock0@raymondhill.net.xpi \
    && echo '{"policies":{"ExtensionSettings":{"uBlock0@raymondhill.net":{"installation_mode":"force_installed","install_url":"file:///opt/waterfox/distribution/extensions/uBlock0@raymondhill.net.xpi"}}}}' \
       > /opt/waterfox/distribution/policies.json

# add the patched i3 binary with /usr/local/bin takong priority over /usr/bin
COPY --from=i3-builder /i3/build/i3 /usr/local/bin/i3

# Lock down zathura: no GUI chrome, disable the file-open command
RUN mkdir -p /etc/skel/.config/zathura \
    && printf 'set guioptions ""\nunmap o\nunmap O\n' \
       > /etc/skel/.config/zathura/zathurarc

# Set up default configuration directories in /etc/skel
RUN mkdir -p /etc/skel/.config/i3 \
             /etc/skel/.config/i3status \
             /etc/skel/.config/vifm \
             /etc/skel/.config/polybar \
             /etc/skel/.config/launcher \
             /etc/skel/.config/launcher/icons \
             /etc/skel/.config/launcher/network \
             /etc/skel/.config/dunst

# Copy i3 and i3status configs
COPY config/i3/i3-config /etc/skel/.config/i3/config
COPY config/i3/i3status-config /etc/skel/.config/i3status/config
COPY config/i3/polybar-config /etc/skel/.config/polybar/config.ini
COPY config/i3/layout.json /etc/skel/.config/i3/layout.json  

# Copy vifm config (kept for potential backend use)
COPY config/interface/vifmrc /etc/skel/.config/vifm/vifmrc
# Copy picom compositor config
COPY config/interface/picom.conf /etc/skel/.config/picom.conf

# Copy launcher scripts
COPY config/launcher/launcher.py            /etc/skel/.config/launcher/launcher.py
COPY config/launcher/folder_viewer.py       /etc/skel/.config/launcher/folder_viewer.py
COPY config/launcher/app-window.py          /etc/skel/.config/launcher/app-window.py
COPY config/launcher/classroom_manager.py   /etc/skel/.config/launcher/classroom_manager.py
COPY widgets/makecode/makecode-app.py       /etc/skel/.config/launcher/makecode-app.py
COPY widgets/fileNav/fileViewer.py          /etc/skel/.config/launcher/fileViewer.py
COPY widgets/library/library.py             /etc/skel/.config/launcher/library.py
COPY config/launcher/lesson-config.py       /etc/skel/.config/launcher/lesson-config.py
COPY config/launcher/waterfox-launcher.sh   /etc/skel/.config/launcher/waterfox-launcher.sh
COPY config/launcher/start-audio.sh        /etc/skel/.config/launcher/start-audio.sh

# Copy sidebar configs as fallback and role specific
COPY config/launcher/appbar-config.json          /etc/skel/.config/launcher/appbar-config.json
COPY config/launcher/appbar-config-teacher.json  /etc/skel/.config/launcher/appbar-config-teacher.json
COPY config/launcher/appbar-config-student.json  /etc/skel/.config/launcher/appbar-config-student.json

# Seed classroom data (written to /shared at runtime by config-launcher.sh)
COPY config/launcher/classrooms.json     /etc/skel/.config/launcher/classrooms.json
COPY config/launcher/available-apps.json /etc/skel/.config/launcher/available-apps.json

# Network sync package
# /etc/skel copy: flat .py files accessible to each user at ~/.config/launcher/network/
COPY network/ /etc/skel/.config/launcher/network/
# /opt/cis4900 copy: python3 -m network.publisher runs from here (via network.sh)
RUN mkdir -p /opt/cis4900
COPY network/ /opt/cis4900/network/
COPY config/launcher/classrooms.json /opt/cis4900/classrooms.json
COPY network/network.sh /opt/cis4900/network.sh
RUN chmod +x /opt/cis4900/network.sh /etc/skel/.config/launcher/network/*.py

# Copy launcher icons
COPY icons/light/*.svg /etc/skel/.config/launcher/icons/light/
COPY icons/dark/*.svg /etc/skel/.config/launcher/icons/dark/
COPY icons/stylized/ /etc/skel/.config/launcher/icons/stylized/

# Make launcher scripts executable
RUN chmod +x /etc/skel/.config/launcher/launcher.py \
             /etc/skel/.config/launcher/folder_viewer.py \
             /etc/skel/.config/launcher/app-window.py \
             /etc/skel/.config/launcher/classroom_manager.py \
             /etc/skel/.config/launcher/makecode-app.py \
             /etc/skel/.config/launcher/fileViewer.py \
             /etc/skel/.config/launcher/library.py \
             /etc/skel/.config/launcher/lesson-config.py \
             /etc/skel/.config/launcher/waterfox-launcher.sh \
             /etc/skel/.config/launcher/start-audio.sh

# Copy setup scripts
COPY config/users/create-users.sh /usr/local/bin/create-users.sh
COPY config/users/user-roles.sh /usr/local/bin/user-roles.sh
COPY config/users/config-user-i3.sh /usr/local/bin/config-user-i3.sh
COPY config/interface/notifications.conf /etc/skel/.config/dunst/dunstrc
COPY config/interface/config-vifm.sh /usr/local/bin/config-vifm.sh
COPY config/interface/config-gtk.sh /usr/local/bin/config-gtk.sh
COPY config/interface/polybar-hover.py  /etc/skel/.config/polybar/polybar-hover.py
COPY config/launcher/config-launcher.sh /usr/local/bin/config-launcher.sh
COPY config/launcher/webapp-viewer.py /etc/skel/.config/launcher/webapp-viewer.py
COPY config/launcher/wifi-connect.sh /usr/local/bin/wifi-connect.sh

RUN chmod +x /usr/local/bin/create-users.sh \
             /usr/local/bin/user-roles.sh \
             /usr/local/bin/config-user-i3.sh \
             /usr/local/bin/config-vifm.sh \
             /usr/local/bin/config-gtk.sh \
             /etc/skel/.config/launcher/webapp-viewer.py \
             /etc/skel/.config/polybar/polybar-hover.py \
             /usr/local/bin/config-launcher.sh

# Create role groups 
RUN groupadd teacher && groupadd student

# Create all users 
RUN /usr/local/bin/create-users.sh

# Set up role-based access control 
RUN /usr/local/bin/user-roles.sh

# Configure i3 for all users
RUN /usr/local/bin/config-user-i3.sh

# Configure vifm for all users
RUN /usr/local/bin/config-vifm.sh

# Configure GTK file chooser for all users
RUN /usr/local/bin/config-gtk.sh

# Configure launcher for all users
# (also bootstraps /shared/classrooms.json with teacher-group write access)
RUN /usr/local/bin/config-launcher.sh

# Remove directory-listing permission from system paths for non-root users.
# 751 = rwxr-x--x: others keep traverse (x) so known paths still work, but
# cannot list the directory (r) so file pickers get "Permission denied".
RUN chmod 751 /opt

# XDG_RUNTIME_DIR parent, users mkdir their own /run/user/<uid>/ at session start
RUN mkdir -p /run/user && chmod 1777 /run/user

# dbus identity, RDP encryption keys and create the directory xrdp needs to store its process ID
RUN mkdir -p /run/dbus && dbus-uuidgen > /etc/machine-id
RUN xrdp-keygen xrdp /etc/xrdp/rsakeys.ini
RUN mkdir -p /var/run/xrdp

# expose the local host port 
EXPOSE 3389

# init process
ENTRYPOINT ["/usr/bin/tini", "--"]

#CMD dbus-daemon --system --fork && /usr/sbin/xrdp-sesman && /usr/sbin/xrdp -n
CMD dbus-daemon --system --fork && /usr/sbin/xrdp-sesman && (cd /opt/cis4900 && python3 -m network.publisher &) && /usr/sbin/xrdp -n