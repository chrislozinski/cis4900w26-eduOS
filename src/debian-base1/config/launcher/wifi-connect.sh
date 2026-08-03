#!/bin/bash
# using font awesome for a lock icon
LOCK=$(printf '') 

ROFI_THEME="$HOME/.config/rofi/rofi-network.rasi"

# Enable WiFi radio (no-op if already on; fails silently if no device)
nmcli radio wifi on 2>/dev/null || true

# Check if NM sees any WiFi device at all
WIFI_DEV=$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')
if [ -z "$WIFI_DEV" ]; then
    notify-send "WiFi" "No WiFi adapter found"
    exit 1
fi

# Trigger scan and block until hardware sweep completes, up to 8seconds
nmcli -w 8 dev wifi rescan ifname "$WIFI_DEV" 2>/dev/null || true

declare -A SSID_MAP
declare -a DISPLAY_LIST

# List networks from populated scan cache
while IFS= read -r line; do
    ssid=$(    echo "$line" | awk -F'  +' '{print $1}' | xargs)
    security=$(echo "$line" | awk -F'  +' '{print $2}' | xargs)
    bars=$(    echo "$line" | awk -F'  +' '{print $3}' | xargs)
    [ -z "$ssid" ] && continue
    lock_flag=""
    [[ "$security" != "--" && -n "$security" ]] && lock_flag="  $LOCK"
    display="${bars}  ${ssid}${lock_flag}"
    SSID_MAP["$display"]="$ssid"
    DISPLAY_LIST+=("$display")
done < <(nmcli -f SSID,SECURITY,BARS dev wifi list ifname "$WIFI_DEV" 2>/dev/null \
    | tail -n +2 | grep -v '^$' | sort -u -k1,1)

if [ ${#DISPLAY_LIST[@]} -eq 0 ]; then
    notify-send "WiFi" "No networks found"
    exit 1
fi

# Mark the currently-connected network's row as rofi's "active" element,
# so rofi-network.rasi can highlight it distinctly from the rest of the list
ACTIVE_SSID=$(nmcli -t -f ACTIVE,SSID dev wifi ifname "$WIFI_DEV" 2>/dev/null \
    | awk -F: '$1=="yes"{print $2; exit}')
ROFI_ACTIVE_ARGS=()
if [ -n "$ACTIVE_SSID" ]; then
    for i in "${!DISPLAY_LIST[@]}"; do
        [ "${SSID_MAP[${DISPLAY_LIST[$i]}]}" = "$ACTIVE_SSID" ] && ROFI_ACTIVE_ARGS=(-a "$i") && break
    done
fi

SELECTION=$(printf '%s\n' "${DISPLAY_LIST[@]}" \
    | rofi -dmenu -l 10 -p "WiFi" -theme "$ROFI_THEME" "${ROFI_ACTIVE_ARGS[@]}")
[ -z "$SELECTION" ] && exit 0

# Show network selector
SSID="${SSID_MAP[$SELECTION]}"
[ -z "$SSID" ] && exit 0

# Try saved profile first silently
nmcli dev wifi connect "$SSID" ifname "$WIFI_DEV" 2>/dev/null && exit 0

# Width adapts to SSID length, 40 chars, if you want non-obscured input, remove -password 
PASS_WIDTH=$(( ${#SSID} + 40 ))
PASSWORD=$(rofi -dmenu -password -lines 0 -p "Password for $SSID:" \
    -theme "$ROFI_THEME" -theme-str "window {width: ${PASS_WIDTH}ch;}")
[ -z "$PASSWORD" ] && exit 0

nmcli dev wifi connect "$SSID" ifname "$WIFI_DEV" password "$PASSWORD" && \
    notify-send "WiFi" "Connected to $SSID" || \
    notify-send "WiFi" "Failed to connect to $SSID"
