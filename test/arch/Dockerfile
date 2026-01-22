FROM archlinux:base

RUN pacman -Syu --noconfirm && pacman -S --noconfirm --needed \
        xrdp \
        xorg-server \
        xorgxrdp \
        i3-wm \
        dbus \
    && pacman -Scc --noconfirm

RUN mkdir -p /run/dbus && dbus-uuidgen > /etc/machine-id

RUN useradd -m testuser && \
    echo "testuser:test" | chpasswd && \
    echo "exec i3" > /home/testuser/.xsession && \
    chown testuser:testuser /home/testuser/.xsession

EXPOSE 3389

CMD dbus-daemon --system --fork && xrdp-sesman && xrdp -n
