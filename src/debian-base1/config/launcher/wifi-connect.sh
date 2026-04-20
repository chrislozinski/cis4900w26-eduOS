#!/bin/bash
# Enable WiFi radio (no-op if already on; fails silently if no device)
nmcli radio wifi on 2>/dev/null || true

# Check if NM sees any WiFi device at all
WIFI_DEV=$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')
if [ -z "$WIFI_DEV" ]; then
    notify-send "WiFi" "No WiFi adapter found — NM is running but sees no WiFi device. Run 'lspci | grep -i net' in a terminal to check hardware"
    exit 1
fi

# Trigger scan and block until hardware sweep completes (up to 8s)
nmcli -w 8 dev wifi rescan ifname "$WIFI_DEV" 2>/dev/null || true

# List networks from populated scan cache
NETWORKS=$(nmcli -t -f SSID dev wifi list ifname "$WIFI_DEV" 2>/dev/null \
    | grep -v '^$' | sort -u)

if [ -z "$NETWORKS" ]; then
    notify-send "WiFi" "WiFi adapter found ($WIFI_DEV) but no networks detected"
    exit 1
fi

# Show centered network picker
SSID=$(printf '%s\n' "$NETWORKS" | rofi -dmenu -l 10 -p "WiFi:")
[ -z "$SSID" ] && exit 0

# Try saved profile first (silent)
nmcli dev wifi connect "$SSID" ifname "$WIFI_DEV" 2>/dev/null && exit 0

# Width adapts to SSID length: prompt chars + 40ch input room; remove -password for non-obscured input
PASS_WIDTH=$(( ${#SSID} + 40 ))
PASSWORD=$(rofi -dmenu -password -lines 0 -p "Password for $SSID:" -theme-str "window {width: ${PASS_WIDTH}ch;}")
[ -z "$PASSWORD" ] && exit 0

nmcli dev wifi connect "$SSID" ifname "$WIFI_DEV" password "$PASSWORD" && \
    notify-send "WiFi" "Connected to $SSID" || \
    notify-send "WiFi" "Failed to connect to $SSID"
