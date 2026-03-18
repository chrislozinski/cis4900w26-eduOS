#!/usr/bin/env python3
"""
Library
Student-facing app that shows approved research sites for their enrolled classroom.
Each site opens in a locked-down webapp-viewer.py window.
"""
import gi
import json
import os
import getpass
import subprocess
import shlex
import threading
import urllib.request
from urllib.parse import urlparse

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf

CLASSROOMS_FILE = '/shared/classrooms.json'
FAVICON_CACHE   = os.path.expanduser('~/.config/launcher/icons/favicons/')


def _favicon_path(url):
    host = urlparse(url).netloc.lstrip('www.').replace('/', '_')
    return os.path.join(FAVICON_CACHE, f"{host}.png")


def _fetch_favicon(url, dest):
    if os.path.exists(dest):
        return
    os.makedirs(FAVICON_CACHE, exist_ok=True)
    host = urlparse(url).netloc
    api  = f"https://www.google.com/s2/favicons?domain={host}&sz=64"
    try:
        req = urllib.request.Request(api, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = r.read()
        if data:
            with open(dest, 'wb') as f:
                f.write(data)
    except Exception:
        pass


def load_classrooms():
    try:
        with open(CLASSROOMS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"classrooms": []}


def get_student_sites():
    username = getpass.getuser()
    data = load_classrooms()
    for classroom in data.get('classrooms', []):
        if username in classroom.get('students', []):
            return classroom.get('library_sites', [])
    return []


class LibraryWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Library")
        self.set_wmclass("library", "Library")
        self.set_default_size(880, 1080)
        self.connect('destroy', Gtk.main_quit)

        self.icon_base = os.path.expanduser('~/.config/launcher/icons/')
        self.viewer    = os.path.expanduser('~/.config/launcher/webapp-viewer.py')

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        header = Gtk.Label()
        header.set_markup("<b>Library</b>")
        header.set_name("lib_header")
        header.set_margin_top(20)
        header.set_margin_bottom(16)
        vbox.pack_start(header, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_margin_start(16)
        scrolled.set_margin_end(16)
        scrolled.set_margin_bottom(16)
        vbox.pack_start(scrolled, True, True, 0)

        self.grid = Gtk.FlowBox()
        self.grid.set_valign(Gtk.Align.START)
        self.grid.set_max_children_per_line(4)
        self.grid.set_column_spacing(12)
        self.grid.set_row_spacing(12)
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(self.grid)

        sites = get_student_sites()

        if sites:
            for site in sites:
                threading.Thread(
                    target=_fetch_favicon,
                    args=(site.get('url', ''), _favicon_path(site.get('url', ''))),
                    daemon=True).start()
                self.grid.add(self._make_tile(site))
        else:
            empty = Gtk.Label(label="No sites have been added to your library yet.")
            empty.set_name("empty_label")
            empty.set_margin_top(40)
            self.grid.add(empty)

    def _make_tile(self, site):
        event_box = Gtk.EventBox()
        event_box.set_name("tile")

        event_box.connect('enter-notify-event',  lambda w, _: w.set_name("tile_hover"))
        event_box.connect('leave-notify-event',  lambda w, _: w.set_name("tile"))
        event_box.connect('button-press-event',  lambda w, _: w.set_name("tile_active"))
        event_box.connect('button-release-event', self._on_tile_release, site)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_size_request(160, 160)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)

        icon_rel  = site.get('icon', '')
        icon_path = os.path.join(self.icon_base, icon_rel) if icon_rel else ''
        favicon   = _favicon_path(site.get('url', ''))

        for candidate in (favicon, icon_path,
                          os.path.join(self.icon_base, 'stylized/rubikMixed.png')):
            if candidate and os.path.exists(candidate):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(candidate, 72, 72, True)
                    box.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 0)
                    break
                except Exception:
                    continue
        else:
            placeholder = Gtk.Label(label="🌐")
            placeholder.set_name("tile_icon_placeholder")
            box.pack_start(placeholder, False, False, 0)

        label = Gtk.Label(label=site.get('label', 'Site'))
        label.set_name("tile_label")
        label.set_line_wrap(True)
        label.set_max_width_chars(18)
        label.set_justify(Gtk.Justification.CENTER)
        box.pack_start(label, False, False, 0)

        event_box.add(box)
        return event_box

    def _get_open_tabs(self):
        try:
            raw = subprocess.check_output(['i3-msg', '-t', 'get_tree'], stderr=subprocess.DEVNULL)
            tree = json.loads(raw.decode())
            result = {}
            self._collect_leaves(tree, result)
            return result
        except Exception:
            return {}

    def _collect_leaves(self, node, result):
        if not node.get('nodes', []):
            name = node.get('name', '')
            cid  = node.get('id')
            if name and cid:
                result[name] = cid
        else:
            for child in node.get('nodes', []):
                self._collect_leaves(child, result)

    def _on_tile_release(self, widget, event, site):
        widget.set_name("tile_hover")
        if event.button != 1:
            return False
        
        label = site.get('label', 'Site')
        url   = site.get('url', '')
        if not url:
            return False
        open_tabs = self._get_open_tabs()
        if label in open_tabs:
            subprocess.Popen(['i3-msg', f'[con_id="{open_tabs[label]}"] focus'])
        else:
            cmd = f"python3 {self.viewer} {shlex.quote(label)} {shlex.quote(url)}"
            subprocess.Popen(
                ['i3-msg', f'[con_mark="viewer_tabs"] focus; focus child; exec {cmd}'])
        return False


def main():
    css = b"""
        window {
            background-color: #F2EEDE;
        }
        #lib_header {
            color: #262626;
            font-size: 20px;
        }
        #tile {
            background-color: #FFFFFF;
            border-radius: 8px;
            padding: 12px;
        }
        #tile_hover {
            background-color: #EAE5D8;
            border-radius: 8px;
            padding: 12px;
        }
        #tile_active {
            background-color: #D8D2C4;
            border-radius: 8px;
            padding: 12px;
        }
        #tile_label {
            color: #262626;
            font-size: 14px;
            font-weight: bold;
        }
        #tile_icon_placeholder {
            font-size: 48px;
        }
        #empty_label {
            color: #888888;
            font-size: 13px;
            font-style: italic;
        }
        label {
            color: #262626;
        }
        scrolledwindow {
            border: none;
        }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    win = LibraryWindow()
    win.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()