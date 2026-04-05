#!/usr/bin/env python3
"""
FileViewer — dark GTK chrome + nsxiv embedded via XEmbed.
Single persistent instance; folder_viewer signals via SIGUSR1 to add tabs.
"""
import gi
import os
import sys
import json
import signal
import subprocess

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
VIEWER_DIR = os.path.expanduser('~/.cache/launcher_viewers')


def _siblings(path):
    """Return sorted list of image paths in the same directory as path."""
    d = os.path.dirname(path)
    try:
        return sorted(
            os.path.join(d, f) for f in os.listdir(d)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS and not f.startswith('.')
        )
    except Exception:
        return [path]


class FileViewer(Gtk.Window):
    def __init__(self, initial_path):
        super().__init__(title="Image View")
        self.set_wmclass("file_viewer", "FileViewer")
        self.set_default_size(800, 600)

        self.tabs = []
        self.active = None
        self.nsxiv_proc = None
        self.nsxiv_watch_id = None

        self._pid = os.getpid()
        self._pid_file  = os.path.join(VIEWER_DIR, 'fv.pid')
        self._json_file = os.path.join(VIEWER_DIR, f'{self._pid}.json')

        os.makedirs(VIEWER_DIR, exist_ok=True)
        with open(self._pid_file, 'w') as f:
            f.write(str(self._pid))
        with open(self._json_file, 'w') as f:
            json.dump({'name': 'Image View', 'pid': self._pid}, f)

        self.connect('destroy', self._on_destroy)

        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.vbox)

        # nav bar
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        nav_box.set_name("nav_bar")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        inner.set_margin_top(8)
        inner.set_margin_bottom(8)
        inner.set_margin_start(10)
        inner.set_margin_end(10)
        nav_box.pack_start(inner, True, True, 0)

        self.prev_btn = Gtk.Button(label="<")
        self.prev_btn.set_name("nav_btn")
        self.prev_btn.connect('clicked', self._on_prev)
        inner.pack_start(self.prev_btn, False, False, 0)

        self.next_btn = Gtk.Button(label=">")
        self.next_btn.set_name("nav_btn")
        self.next_btn.connect('clicked', self._on_next)
        inner.pack_start(self.next_btn, False, False, 0)

        self.tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.tab_bar.set_homogeneous(True)
        inner.pack_start(self.tab_bar, True, True, 4)

        self.vbox.pack_start(nav_box, False, False, 0)

        # socket_area holds the current GtkSocket; recreated on every nsxiv launch
        self.socket_area = Gtk.Box()
        self.socket_area.set_name("viewer_socket")
        self.vbox.pack_start(self.socket_area, True, True, 0)

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._on_open_request)

        self._initial_path = os.path.abspath(initial_path)

    #  socket management 

    def _fresh_socket(self):
        """Replace socket_area with a brand-new GtkSocket and return its XID.
        GtkSocket is one-use — once a plug disconnects the socket is dead."""
        for child in self.socket_area.get_children():
            self.socket_area.remove(child)

        sock = Gtk.Socket()
        self.socket_area.pack_start(sock, True, True, 0)
        sock.realize()   # creates the X window so the XID is valid
        sock.show()
        Gdk.flush()      # flush all pending X11 commands before handing XID to nsxiv
        return sock.get_id()

    #  tab management 

    def _open_tab(self, path):
        path = os.path.abspath(path)
        files = _siblings(path)
        # compare by basename to avoid path normalisation mismatches
        target = os.path.basename(path)
        index = next((i for i, f in enumerate(files) if os.path.basename(f) == target), 0)
        tab = {'files': files, 'index': index}
        self.tabs.append(tab)

        # Box holds two separate buttons — label button switches tab, X button closes
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        container.get_style_context().add_class('tab')

        lbl_btn = Gtk.Button()
        lbl_btn.set_relief(Gtk.ReliefStyle.NONE)
        lbl_btn.get_style_context().add_class('tab_label')
        lbl = Gtk.Label()
        lbl.set_halign(Gtk.Align.START)
        lbl_btn.add(lbl)
        lbl_btn.connect('clicked', lambda *_, t=tab: self._switch_tab(t))
        container.pack_start(lbl_btn, True, True, 0)

        x_btn = Gtk.Button(label="✕")
        x_btn.set_relief(Gtk.ReliefStyle.NONE)
        x_btn.get_style_context().add_class('tab_close')
        x_btn.connect('clicked', lambda *_, t=tab: self._close_tab(t))
        container.pack_start(x_btn, False, False, 0)

        tab['widget'] = container
        tab['label']  = lbl

        self.tab_bar.pack_start(container, True, True, 0)
        self.tab_bar.show_all()
        self._switch_tab(tab)

    def _switch_tab(self, tab):
        if self.active is not None:
            self.active['widget'].get_style_context().remove_class('active')
        self.active = tab
        tab['widget'].get_style_context().add_class('active')
        self._update_tab_label(tab)
        self._update_nav_buttons()
        self._launch_nsxiv(tab)

    def _close_tab(self, tab):
        idx = self.tabs.index(tab)
        was_active = tab is self.active
        if was_active:
            self._kill_nsxiv()
        self.tab_bar.remove(tab['widget'])
        self.tabs.remove(tab)
        if not self.tabs:
            self.destroy()
            return
        if was_active:
            self.active = None
            self._switch_tab(self.tabs[min(idx, len(self.tabs) - 1)])

    def _update_tab_label(self, tab):
        name = os.path.basename(tab['files'][tab['index']])
        tab['label'].set_text(name if len(name) <= 18 else name[:15] + '...')

    def _on_open_request(self):
        pending = os.path.join(VIEWER_DIR, 'fv_pending')
        if os.path.exists(pending):
            try:
                path = open(pending).read().strip()
                os.remove(pending)
                self._open_tab(path)
            except Exception:
                pass
        return True

    #  nsxiv ─

    def _launch_nsxiv(self, tab):
        self._kill_nsxiv()
        xid = self._fresh_socket()
        self.nsxiv_proc = subprocess.Popen(
            ['nsxiv', '-b', '-e', str(xid), tab['files'][tab['index']]]
        )
        self.nsxiv_watch_id = GLib.child_watch_add(
            self.nsxiv_proc.pid, self._on_nsxiv_exit
        )

    def _kill_nsxiv(self):
        if self.nsxiv_watch_id is not None:
            GLib.source_remove(self.nsxiv_watch_id)
            self.nsxiv_watch_id = None
        if self.nsxiv_proc and self.nsxiv_proc.poll() is None:
            try:
                self.nsxiv_proc.terminate()
                self.nsxiv_proc.wait(timeout=1)
            except Exception:
                pass
        self.nsxiv_proc = None

    def _on_nsxiv_exit(self, *_):
        self.nsxiv_watch_id = None
        self.nsxiv_proc = None
        if self.active is not None:
            GLib.idle_add(self._close_tab, self.active)

    #  navigation 

    def _update_nav_buttons(self):
        if self.active is None:
            return
        self.prev_btn.set_sensitive(self.active['index'] > 0)
        self.next_btn.set_sensitive(self.active['index'] < len(self.active['files']) - 1)

    def _on_prev(self, *_):
        if self.active and self.active['index'] > 0:
            self.active['index'] -= 1
            self._update_tab_label(self.active)
            self._update_nav_buttons()
            self._launch_nsxiv(self.active)

    def _on_next(self, *_):
        if self.active and self.active['index'] < len(self.active['files']) - 1:
            self.active['index'] += 1
            self._update_tab_label(self.active)
            self._update_nav_buttons()
            self._launch_nsxiv(self.active)

    #  cleanup 

    def _on_destroy(self, *_):
        self._kill_nsxiv()
        for p in (self._pid_file, self._json_file):
            try:
                os.remove(p)
            except Exception:
                pass
        Gtk.main_quit()


def main():
    if len(sys.argv) < 2:
        print("Usage: fileViewer.py <image_path>")
        sys.exit(1)

    css = b"""
        window          { background-color: #2C2C2C; }
        #nav_bar        { background-color: #232323; padding: 0; margin: 0; }
        button#nav_btn  { background-image: none; background-color: #3A3A3A;
                          color: #E8E8E8; border: none; border-radius: 2px;
                          padding: 2px 8px; font-size: 13px; font-weight: bold;
                          min-width: 0; box-shadow: none; text-shadow: none;
                          -gtk-icon-shadow: none; }
        button#nav_btn:hover    { background-image: none; background-color: #4A4A4A; }
        button#nav_btn:active   { background-image: none; background-color: #1A1A1A; }
        button#nav_btn:disabled { background-image: none; background-color: #2A2A2A;
                                  color: #666666; }
        button#nav_btn label            { color: #E8E8E8; }
        button#nav_btn:disabled label   { color: #666666; }
        .tab            { background-color: #333333; }
        .tab.active     { background-color: #4A4A4A; }
        .tab button     { background-image: none; background-color: transparent;
                          border: none; box-shadow: none; min-width: 0;
                          -gtk-icon-shadow: none; text-shadow: none; }
        .tab button:hover { background-image: none;
                            background-color: rgba(255,255,255,0.06); }
        .tab_label label { color: #E8E8E8; font-size: 12px; }
        .tab_close      { color: #888888; padding: 0 4px; }
        .tab_close label { color: #888888; }
        .tab_close:hover { background-image: none; }
        .tab_close:hover label { color: #E8E8E8; }
        label           { color: #E8E8E8; }
        #viewer_socket  { background-color: #1A1A1A; }
    """

    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    win = FileViewer(sys.argv[1])
    win.set_opacity(0)
    win.show_all()
    # open first tab after window is fully mapped so socket XID is valid
    GLib.timeout_add(100, lambda: (win._open_tab(win._initial_path), win.set_opacity(1), False)[2])
    Gtk.main()


if __name__ == '__main__':
    main()
