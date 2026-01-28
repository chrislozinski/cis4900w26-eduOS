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
    dbus \
    sudo \
    openssl \
    tini \
    xterm \
    curl \
    wget \
    git \     
    vim \
    vifm \
    nano \
    python3 \ 
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set up default i3 configuration in /etc/skel
RUN mkdir -p /etc/skel/.config/i3 /etc/skel/.config/i3status
COPY i3-config /etc/skel/.config/i3/config
COPY i3status-config /etc/skel/.config/i3status/config

# Copy setup scripts
COPY create-users.sh /usr/local/bin/create-users.sh
COPY user-roles.sh /usr/local/bin/user-roles.sh
COPY config-user-i3.sh /usr/local/bin/config-user-i3.sh
RUN chmod +x /usr/local/bin/create-users.sh \
             /usr/local/bin/user-roles.sh \
             /usr/local/bin/config-user-i3.sh

# Create role groups 
RUN groupadd teacher && groupadd student

# Create all users 
RUN /usr/local/bin/create-users.sh

# Set up role-based access control 
RUN /usr/local/bin/user-roles.sh

# Configure i3 for all users 
RUN /usr/local/bin/config-user-i3.sh

# dbus identity, RDP encryption keys and create the directory xrdp needs to store its process ID
RUN mkdir -p /run/dbus && dbus-uuidgen > /etc/machine-id
RUN xrdp-keygen xrdp /etc/xrdp/rsakeys.ini
RUN mkdir -p /var/run/xrdp

# expose the local host port 
EXPOSE 3389

# init process
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD dbus-daemon --system --fork && /usr/sbin/xrdp-sesman && /usr/sbin/xrdp -n
