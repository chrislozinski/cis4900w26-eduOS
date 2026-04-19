#!/bin/bash
# Enable WiFi radio (no-op if already on; fails silently if no device)
nmcli radio wifi on 2>/dev/null || true

# Check if NM sees any WiFi device at all
WIFI_DEV=$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')
if [ -z "$WIFI_DEV" ]; then
    notify-send "WiFi" "No WiFi adapter found — NM is running but sees no WiFi device. Run 'lspci | grep -i net' in a terminal to check hardware"
    exit 1
fi

# Trigger async scan, then wait for results to populate
nmcli dev wifi rescan ifname "$WIFI_DEV" 2>/dev/null || true
sleep 2

# List networks from populated scan cache
NETWORKS=$(nmcli -t -f SSID dev wifi list ifname "$WIFI_DEV" 2>/dev/null \
    | grep -v '^$' | sort -u)

if [ -z "$NETWORKS" ]; then
    notify-send "WiFi" "WiFi adapter found ($WIFI_DEV) but no networks detected"
    exit 1
fi

# Show vertical network picker at bottom of screen
SSID=$(printf '%s\n' "$NETWORKS" | dmenu -b -l 10 -p "WiFi:")
[ -z "$SSID" ] && exit 0

# Try saved profile first (silent)
nmcli dev wifi connect "$SSID" ifname "$WIFI_DEV" 2>/dev/null && exit 0

# Need password
PASSWORD=$(dmenu -b -p "Password for $SSID:" </dev/null)
[ -z "$PASSWORD" ] && exit 0

nmcli dev wifi connect "$SSID" ifname "$WIFI_DEV" password "$PASSWORD" && \
    notify-send "WiFi" "Connected to $SSID" || \
    notify-send "WiFi" "Failed to connect to $SSID"
