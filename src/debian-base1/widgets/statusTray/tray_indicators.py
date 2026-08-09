#!/usr/bin/env python3
"""
Network / volume / battery status-row indicators for the launcher sidebar.

Each IndicatorTile owns its own polling + its own popover content, reused
identically whether opened from its own row icon or from the combined
"quick settings" flyout in launcher.py.

To add a new indicator: subclass IndicatorTile, implement refresh() and
build_tile() (see NetworkIndicator/VolumeIndicator/BatteryIndicator below
for the shape), then append the class to TRAY_INDICATORS at the bottom of
this file. Nothing else needs to change.
"""
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

# FontAwesome 4 Private-Use-Area codepoint
GLYPH_WIFI             = '\uf1eb'   # fa-wifi
GLYPH_VOLUME_UP        = '\uf028'   # fa-volume-up
GLYPH_VOLUME_DOWN      = '\uf027'   # fa-volume-down
GLYPH_VOLUME_OFF       = '\uf026'   # fa-volume-off (also used when muted)
GLYPH_BATTERY_FULL     = '\uf240'   # fa-battery (4/4)
GLYPH_BATTERY_3Q       = '\uf241'   # fa-battery (3/4)
GLYPH_BATTERY_HALF     = '\uf242'   # fa-battery (2/4)
GLYPH_BATTERY_QUARTER  = '\uf243'   # fa-battery (1/4)
GLYPH_BATTERY_EMPTY    = '\uf244'   # fa-battery (0/4)
GLYPH_TRAY_MORE        = '\uf141'   # fa-ellipsis-h, the combined-flyout trigger

DEFAULT_SINK = '@DEFAULT_SINK@'
BATTERY_PATH = '/sys/class/power_supply/BAT0'


def tray_css():
    """Registers the tray's CSS: icon font/size and popover styling
    Self-contained like every other widget in this repo, so launcher.py just calls it once
    Icon size matches launcher.py's own proportional sizing formula."""
    icon_size = int(Gdk.Screen.get_default().get_height() * 0.0223)
    provider = Gtk.CssProvider()
    provider.load_from_data(f"""
        #tray_icon_label {{ font-family: "FontAwesome"; font-size: {icon_size * 0.8}px; }}
        #tray_percent_label {{ font-size: {icon_size * 0.5}px; color: #ffffff; }}
        .tray-popover-content {{
            background-color: #3c3c3c;
            border-radius: 9px;
            border: 1px solid #545454;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
            padding: 16px;
        }}
        .tray-popover-content label {{
            color: #ffffff;
        }}
        .tray-popover-content .tile-header {{
            font-weight: bold;
            font-size: {icon_size * 0.55}px;
            color: #cccccc;
            margin-bottom: 2px;
        }}
        .tray-popover-content button {{
            background-color: #505050;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 6px 14px;
            min-width: 72px;
        }}
        .tray-popover-content button:hover {{
            background-color: #606060;
        }}
        .tray-popover-content button:active {{
            background-color: #454545;
        }}
        .tray-popover-content button:checked {{
            background-color: #b23b3b;
        }}
        .tray-popover-content scale trough {{
            background-color: #2a2a2a;
            border-radius: 4px;
            min-height: 6px;
        }}
        .tray-popover-content scale highlight {{
            background-color: #6c9ef8;
            border-radius: 4px;
        }}
        .tray-popover-content scale slider {{
            background-color: #ffffff;
            border-radius: 50%;
            min-width: 14px;
            min-height: 14px;
        }}
    """.encode('utf-8'))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


_active_flyout = {'window': None}


def _close_active_flyout():
    win = _active_flyout['window']
    if win is None:
        return
    _active_flyout['window'] = None
    Gdk.Display.get_default().get_default_seat().ungrab()
    win.destroy()


FLYOUT_BOTTOM_PADDING = 8  # always kept between the flyout and the screen's bottom edge


def show_flyout(anchor_widget, content_widget, on_close=None):
    """Borderless flyout pinned to the sidebar's right edge and bottom-anchored with fixed screen edge padding
    it grows upward with its content instead of aligning to the clicked icon's Y"""
    _close_active_flyout()

    popup = Gtk.Window(type=Gtk.WindowType.POPUP)
    popup.set_decorated(False)
    screen = Gdk.Screen.get_default()
    visual = screen.get_rgba_visual()
    if visual is not None:
        popup.set_visual(visual)
    popup.get_style_context().add_class('tray-popover-content')
    popup.add(content_widget)

    # The sidebar is always at screen (0, 0), so its right edge is always exactly its current width
    sidebar = anchor_widget.get_toplevel()
    sidebar_width = sidebar.collapsed_width if sidebar.is_collapsed else sidebar.expanded_width

    # Show off-screen first so the size measurement below is accurate
    # (a unrealized/unshown window under 
    # measures)
    popup.move(-10000, -10000)
    popup.show_all()
    screen_height = screen.get_height()
    _, real_height = popup.get_size()
    y = max(0, screen_height - real_height - FLYOUT_BOTTOM_PADDING)

    popup.move(sidebar_width + 8, y)

    def on_button_press(widget, event):
        alloc = popup.get_allocation()
        if 0 <= event.x < alloc.width and 0 <= event.y < alloc.height:
            return False  # inside the flyout 
        _close_active_flyout()
        return True

    popup.connect('button-press-event', on_button_press)
    popup.connect('key-press-event',
                   lambda w, e: _close_active_flyout() if e.keyval == Gdk.KEY_Escape else None)
    if on_close is not None:
        popup.connect('destroy', lambda w: on_close())

    # owner_events=True so clicks on our own widgets (buttons, slider) dispatch normally
    Gdk.Display.get_default().get_default_seat().grab(
        popup.get_window(), Gdk.SeatCapabilities.ALL_POINTING, True, None, None, None, None
    )
    _active_flyout['window'] = popup
    return popup


def _run(cmd, timeout=2):
    """Run a command, returning stdout on success or None on any failure
    (missing binary, timeout, non-zero exit doesn't matter here it will crash).
    Every query_*() below goes through this instead of repeating its own
    try/except subprocess.run boilerplate."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return None


@dataclass
class NetworkStatus:
    has_adapter: bool
    connected: bool = False
    ssid: Optional[str] = None


@dataclass
class VolumeStatus:
    volume_pct: int = 0
    muted: bool = False


@dataclass
class BatteryStatus:
    present: bool
    percent: Optional[int] = None
    charging: Optional[bool] = None


def query_network_status():
    """Current wifi adapter/connection state via nmcli."""
    dev_out = _run(['nmcli', '-t', '-f', 'DEVICE,TYPE', 'dev'])
    if dev_out is None:
        return NetworkStatus(has_adapter=False)

    has_adapter = any(
        line.split(':', 1)[1] == 'wifi'
        for line in dev_out.splitlines() if ':' in line
    )
    if not has_adapter:
        return NetworkStatus(has_adapter=False)

    wifi_out = _run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'])
    if wifi_out is None:
        return NetworkStatus(has_adapter=True)

    for line in wifi_out.splitlines():
        if line.startswith('yes:'):
            return NetworkStatus(has_adapter=True, connected=True, ssid=line.split(':', 1)[1])
    return NetworkStatus(has_adapter=True)


def query_volume_status():
    """Current default-sink volume/mute via pactl."""
    status = VolumeStatus()
    vol_out = _run(['pactl', 'get-sink-volume', DEFAULT_SINK])
    if vol_out is not None:
        match = re.search(r'(\d+)%', vol_out)
        if match:
            status.volume_pct = int(match.group(1))
    mute_out = _run(['pactl', 'get-sink-mute', DEFAULT_SINK])
    if mute_out is not None:
        status.muted = 'yes' in mute_out.lower()
    return status


def query_battery_status():
    """Battery presence/percent/charging via sysfs."""
    cap_path = os.path.join(BATTERY_PATH, 'capacity')
    status_path = os.path.join(BATTERY_PATH, 'status')
    if not os.path.exists(cap_path):
        return BatteryStatus(present=False)
    try:
        with open(cap_path) as f:
            percent = int(f.read().strip())
    except Exception:
        return BatteryStatus(present=False)
    charging = None
    try:
        with open(status_path) as f:
            charging = f.read().strip().lower() == 'charging'
    except Exception:
        pass
    return BatteryStatus(present=True, percent=percent, charging=charging)


class IndicatorTile:
    """Base class for one status-row indicator (network/volume/battery).
    Subclasses implement refresh() (poll + repaint the row icon, via the
    _set_icon() helper) and build_tile() (render popover content into a
    caller-supplied Gtk.Box, optionally via the _status_label() helper)."""

    def __init__(self):
        self.state = None  # set by the first refresh(); a query_*() dataclass instance
        self.icon_label = Gtk.Label(label='?')
        self.icon_label.set_name('tray_icon_label')
        self.icon_label.set_halign(Gtk.Align.CENTER)

    def create_icon_widget(self):
        event = Gtk.EventBox()
        event.add(self.icon_label)
        event.connect('button-release-event', self.on_icon_click)
        self.refresh()
        return event

    def on_icon_click(self, widget, event=None):
        # event=None: also reused as a plain Gtk.Button 'clicked' handler (1 arg, not 2)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.build_tile(content)
        show_flyout(widget, content, on_close=self._on_flyout_closed)

    def _on_flyout_closed(self):
        """Override to clean up any per-flyout widget references (e.g.
        VolumeIndicator's slider) once the flyout is destroyed."""
        pass

    # --- shared helpers, so every indicator follows the same shape ---
    def _set_icon(self, glyph, tooltip, dim=False):
        """Update the row icon. Every refresh() implementation should
        end by calling this instead of touching icon_label directly"""
        self.icon_label.set_text(glyph)
        self.icon_label.set_opacity(0.4 if dim else 1.0)
        self.icon_label.set_tooltip_text(tooltip)

    def _status_label(self, container, text):
        """
        Pack a left-aligned status line into a popover tile. 
        Available for build_tile() implementations that just need a plain line of
        text (NetworkIndicator, BatteryIndicator) which is not needed for
        ones with their own primary widget like the VolumeIndicator's slider
        as it already shows its value
        """
        label = Gtk.Label(label=text)
        label.set_halign(Gtk.Align.START)
        container.pack_start(label, False, False, 0)
        return label

    def _tile_header(self, container, text):
        """Bold title line at the top of a flyout tile, e.g. 'Volume'."""
        label = Gtk.Label(label=text)
        label.set_halign(Gtk.Align.START)
        label.get_style_context().add_class('tile-header')
        container.pack_start(label, False, False, 0)
        return label

    def refresh(self):
        raise NotImplementedError

    def build_tile(self, container):
        raise NotImplementedError


class NetworkIndicator(IndicatorTile):
    def refresh(self):
        self.state = query_network_status()
        if not self.state.has_adapter:
            self._set_icon(GLYPH_WIFI, 'No WiFi adapter', dim=True)
        elif not self.state.connected:
            self._set_icon(GLYPH_WIFI, 'Not connected', dim=True)
        else:
            self._set_icon(GLYPH_WIFI, self.state.ssid)

    def on_icon_click(self, widget, event=None):
        # network's "menu" is the rofi picker itself, not a popover
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wifi-connect.sh')
        subprocess.Popen(['bash', script])

    def build_tile(self, container):
        self._tile_header(container, 'Wi-Fi')
        status = query_network_status()
        if not status.has_adapter:
            text = 'No WiFi adapter'
        elif status.connected:
            text = f'Connected: {status.ssid}'
        else:
            text = 'Not connected'
        self._status_label(container, text)

        manage_btn = Gtk.Button(label='Manage Wi-Fi')
        manage_btn.connect('clicked', self.on_icon_click)
        container.pack_start(manage_btn, False, False, 0)


class VolumeIndicator(IndicatorTile):
    def __init__(self):
        super().__init__()
        self._scale = None
        self._scale_handler_id = None
        self._debounce_id = None
        self._fast_poll_id = None
        self._last_local_change = 0.0

    def refresh(self):
        self.state = query_volume_status()
        pct, muted = self.state.volume_pct, self.state.muted
        if muted or pct == 0:
            glyph = GLYPH_VOLUME_OFF
        elif pct < 50:
            glyph = GLYPH_VOLUME_DOWN
        else:
            glyph = GLYPH_VOLUME_UP
        self._set_icon(glyph, f'Volume: {pct}%' + (' (muted)' if muted else ''))
        # sync an open popover's slider without re-triggering write-back
        if self._scale is not None and (time.monotonic() - self._last_local_change) > 1.0:
            self._scale.handler_block(self._scale_handler_id)
            self._scale.set_value(pct)
            self._scale.handler_unblock(self._scale_handler_id)

    def build_tile(self, container):
        self._tile_header(container, 'Volume')
        status = query_volume_status()  # fresh, not the 5s-stale poll cache

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_value(status.volume_pct)
        scale.set_draw_value(False)
        scale.set_size_request(160, -1)
        self._scale_handler_id = scale.connect('value-changed', self._on_scale_changed)
        self._scale = scale
        container.pack_start(scale, False, False, 0)

        mute_btn = Gtk.ToggleButton(label='Mute')
        mute_btn.set_active(status.muted)
        mute_btn.connect('toggled', self._on_mute_toggled)
        container.pack_start(mute_btn, False, False, 0)

        # Poll every 300ms only while this flyout is open, so an external change
        # (hardware volume keys) shows up in the open slider immediately instead
        # of waiting for the shared 5s row-icon refresh timer (launcher.py L300).
        self._fast_poll_id = GLib.timeout_add(300, self._fast_poll)

    def _fast_poll(self):
        if self._scale is None:
            return False
        self.refresh()
        return True

    def _on_scale_changed(self, scale):
        self._last_local_change = time.monotonic()
        # Debounce so a slider drag doesn't spawn a pactl process per pixel
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
        value = int(scale.get_value())
        self._debounce_id = GLib.timeout_add(150, self._commit_volume, value)

    def _commit_volume(self, value):
        self._debounce_id = None
        result = subprocess.run(['pactl', 'set-sink-volume', DEFAULT_SINK, f'{value}%'])
        if result.returncode == 0:
            subprocess.run(['notify-send', '-t', '800', '-h', f'int:value:{value}', 'Volume', ''])
        return False

    def _on_mute_toggled(self, button):
        result = subprocess.run(['pactl', 'set-sink-mute', DEFAULT_SINK, 'toggle'])
        if result.returncode == 0:
            subprocess.run(['notify-send', '-t', '800', 'Volume',
                             'Muted' if button.get_active() else 'Unmuted'])
        GLib.timeout_add(120, self._resync_after_mute)

    def _resync_after_mute(self):
        self.refresh()
        return False

    def _on_flyout_closed(self):
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
            self._debounce_id = None
        if self._fast_poll_id is not None:
            GLib.source_remove(self._fast_poll_id)
            self._fast_poll_id = None
        self._scale = None
        self._scale_handler_id = None


class BatteryIndicator(IndicatorTile):
    """Battery is display-only in the row: icon + a small '72%' readout next to it
    no click/popover unlike Network/Volume """

    _THRESHOLDS = (
        (85, GLYPH_BATTERY_FULL),
        (60, GLYPH_BATTERY_3Q),
        (35, GLYPH_BATTERY_HALF),
        (10, GLYPH_BATTERY_QUARTER),
        (0,  GLYPH_BATTERY_EMPTY),
    )

    def __init__(self):
        super().__init__()
        self.percent_label = Gtk.Label(label='')
        self.percent_label.set_name('tray_percent_label')

    def create_icon_widget(self):
        # Plain Box, not an EventBox, no click handler, so no popover
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        box.pack_start(self.icon_label, False, False, 0)
        box.pack_start(self.percent_label, False, False, 0)
        self.refresh()
        return box

    def refresh(self):
        self.state = query_battery_status()
        if not self.state.present:
            self._set_icon(GLYPH_BATTERY_EMPTY, 'No battery', dim=True)
            self.percent_label.set_text('')
            return
        pct = self.state.percent
        glyph = next(g for threshold, g in self._THRESHOLDS if pct >= threshold)
        suffix = ' (charging)' if self.state.charging else ''
        self._set_icon(glyph, f'Battery: {pct}%{suffix}')
        self.percent_label.set_text(f'{pct}%')

    def build_tile(self, container):
        self._tile_header(container, 'Battery')
        # Still used inside the combined "..." quick-settings flyout
        status = query_battery_status()
        if not status.present:
            text = 'Battery: --'
        else:
            text = f'Battery: {status.percent}%'
            if status.charging:
                text += ' : Charging'
        self._status_label(container, text)


# What appears in the status row, left to right. Add an indicator here.
TRAY_INDICATORS = [NetworkIndicator, VolumeIndicator, BatteryIndicator]
