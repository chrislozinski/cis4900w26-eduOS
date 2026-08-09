#!/bin/bash
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null || true
pkill -u "$(id -u)" -x pipewire       2>/dev/null || true
pkill -u "$(id -u)" -x pipewire-pulse 2>/dev/null || true

/usr/bin/pipewire &
until [ -S "$XDG_RUNTIME_DIR/pipewire-0" ] || ! kill -0 $! 2>/dev/null; do sleep 0.1; done

/usr/bin/pipewire-pulse &
until [ -S "$XDG_RUNTIME_DIR/pulse/native" ] || ! kill -0 $! 2>/dev/null; do sleep 0.1; done

# wireplumber is started by systemd (wireplumber.service, via i3-config); just wait for it
for i in $(seq 1 50); do wpctl status >/dev/null 2>&1 && break; sleep 0.1; done
if ! wpctl status >/dev/null 2>&1; then
    notify-send -u critical "Audio" "WirePlumber did not start" 2>/dev/null || true
fi

wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.8 2>/dev/null || true

/usr/libexec/pipewire-module-xrdp/load_pw_modules.sh 2>/dev/null || true

