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
    suckless-tools \
    xrdp \
    xorg \
    xorgxrdp \
    x11-xserver-utils \
    dbus \
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
    vifm \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Drop in the patched i3 binary with /usr/local/bin takong priority over /usr/bin
COPY --from=i3-builder /i3/build/i3 /usr/local/bin/i3


# Set up default configuration directories in /etc/skel
RUN mkdir -p /etc/skel/.config/i3 \
             /etc/skel/.config/i3status \
             /etc/skel/.config/vifm \
             /etc/skel/.config/launcher \
             /etc/skel/.config/launcher/icons

# Copy i3 and i3status configs
COPY config/i3/i3-config /etc/skel/.config/i3/config
COPY config/i3/i3status-config /etc/skel/.config/i3status/config
COPY config/i3/layout.json /etc/skel/.config/i3/layout.json  

# Copy vifm config (kept for potential backend use)
COPY config/interface/vifmrc /etc/skel/.config/vifm/vifmrc

# Copy launcher scripts
COPY config/launcher/launcher.py           /etc/skel/.config/launcher/launcher.py
COPY config/launcher/folder_viewer.py      /etc/skel/.config/launcher/folder_viewer.py
COPY config/launcher/app-window.py         /etc/skel/.config/launcher/app-window.py
COPY config/launcher/classroom_manager.py  /etc/skel/.config/launcher/classroom_manager.py

# Copy sidebar configs — generic fallback + role-specific
COPY config/launcher/appbar-config.json          /etc/skel/.config/launcher/appbar-config.json
COPY config/launcher/appbar-config-teacher.json  /etc/skel/.config/launcher/appbar-config-teacher.json
COPY config/launcher/appbar-config-student.json  /etc/skel/.config/launcher/appbar-config-student.json

# Seed classroom data (written to /shared at runtime by config-launcher.sh)
COPY config/launcher/classrooms.json     /etc/skel/.config/launcher/classrooms.json
COPY config/launcher/available-apps.json /etc/skel/.config/launcher/available-apps.json

# Copy launcher icons
COPY icons/light/*.svg /etc/skel/.config/launcher/icons/light/
COPY icons/dark/*.svg /etc/skel/.config/launcher/icons/dark/

# Make launcher scripts executable
RUN chmod +x /etc/skel/.config/launcher/launcher.py \
             /etc/skel/.config/launcher/folder_viewer.py \
             /etc/skel/.config/launcher/app-window.py \
             /etc/skel/.config/launcher/classroom_manager.py

# Copy setup scripts
COPY config/users/create-users.sh /usr/local/bin/create-users.sh
COPY config/users/user-roles.sh /usr/local/bin/user-roles.sh
COPY config/users/config-user-i3.sh /usr/local/bin/config-user-i3.sh
COPY config/interface/config-vifm.sh /usr/local/bin/config-vifm.sh
COPY config/launcher/config-launcher.sh /usr/local/bin/config-launcher.sh

RUN chmod +x /usr/local/bin/create-users.sh \
             /usr/local/bin/user-roles.sh \
             /usr/local/bin/config-user-i3.sh \
             /usr/local/bin/config-vifm.sh \
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

# Configure launcher for all users
# (also bootstraps /shared/classrooms.json with teacher-group write access)
RUN /usr/local/bin/config-launcher.sh

# dbus identity, RDP encryption keys and create the directory xrdp needs to store its process ID
RUN mkdir -p /run/dbus && dbus-uuidgen > /etc/machine-id
RUN xrdp-keygen xrdp /etc/xrdp/rsakeys.ini
RUN mkdir -p /var/run/xrdp

# expose the local host port 
EXPOSE 3389

# init process
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD dbus-daemon --system --fork && /usr/sbin/xrdp-sesman && /usr/sbin/xrdp -n