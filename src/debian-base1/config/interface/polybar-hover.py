#!/usr/bin/env python3
import gi, subprocess, re, time
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gdk, GdkX11, GLib

def find_polybar_wid():
    try:
        out = subprocess.check_output(
            ['xwininfo', '-tree', '-root'],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            if '"polybar"' in line or '"Polybar"' in line:
                m = re.search(r'(0x[0-9a-f]+)', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None

wid_hex = None
while wid_hex is None:
    wid_hex = find_polybar_wid()
    if wid_hex is None:
        time.sleep(1)

def set_name(name):
    subprocess.run(
        ['xprop', '-id', wid_hex, '-set', 'WM_NAME', name],
        capture_output=True
    )

display = Gdk.Display.get_default()
gdk_win = GdkX11.X11Window.foreign_new_for_display(display, int(wid_hex, 16))
gdk_win.set_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)

def on_event(event, _):
    if event.type == Gdk.EventType.ENTER_NOTIFY:
        set_name('polybar-hover')
    elif event.type == Gdk.EventType.LEAVE_NOTIFY:
        set_name('polybar')

Gdk.event_handler_set(on_event, None)
GLib.MainLoop().run()
