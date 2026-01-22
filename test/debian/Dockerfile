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
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# user setup
RUN useradd -m testuser -p $(openssl passwd 1234) && \
    usermod -aG sudo testuser && \
    echo "exec i3" > /home/testuser/.xsession && \
    chown testuser:testuser /home/testuser/.xsession

# role based access setup
COPY usr-roles.sh /usr/local/bin/usr-roles.sh
RUN chmod +x /usr/local/bin/usr-roles.sh && /usr/local/bin/usr-roles.sh

# i3 configuration
RUN mkdir -p /home/testuser/.config/i3
COPY i3-config /home/testuser/.config/i3/config
RUN chown -R testuser:testuser /home/testuser/.config

# dbus identity, RDP encryption keys and create the directory xrdp needs to store its process ID
RUN mkdir -p /run/dbus && dbus-uuidgen > /etc/machine-id
RUN xrdp-keygen xrdp /etc/xrdp/rsakeys.ini
RUN mkdir -p /var/run/xrdp

# expose the local host port 
EXPOSE 3389

# init process
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD dbus-daemon --system --fork && /usr/sbin/xrdp-sesman && /usr/sbin/xrdp -n
