#!/usr/bin/env python3
"""
MakeCode Offline Editor
Serves the pre-built staticpkg from /opt/makecode/static
and renders it inside a native GTK + WebKit2 window.
"""
import gi
import os
import threading
import http.server
import socketserver

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, Gdk, WebKit2, GLib

STATIC_DIR = "/opt/makecode/static"

# Port 0 = OS picks a free port, avoids conflict when multiple users are logged in
server_port = 0

def start_server():
    global server_port
    os.chdir(STATIC_DIR)
    handler = http.server.SimpleHTTPRequestHandler
    # suppress request logs so they don't clutter stdout
    handler.log_message = lambda *a: None
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    server_port = httpd.server_address[1]
    httpd.serve_forever()


class MakeCodeWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="MakeCode for micro:bit")
        self.set_default_size(1280, 900)
        self.connect("destroy", Gtk.main_quit)

        # CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window {
                background-color: #262626;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Loading label while server warms up
        self.stack = Gtk.Stack()
        self.add(self.stack)

        loading_label = Gtk.Label()
        loading_label.set_markup(
            "<span foreground='#ffffff' size='large'>Loading MakeCode…</span>"
        )
        loading_label.set_halign(Gtk.Align.CENTER)
        loading_label.set_valign(Gtk.Align.CENTER)
        self.stack.add_named(loading_label, "loading")

        # WebKit view
        self.webview = WebKit2.WebView()

        settings = self.webview.get_settings()
        settings.set_enable_javascript(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)
        settings.set_enable_developer_extras(False)

        # suppress right click context menu 
        self.webview.connect("context-menu", lambda *a: True)

        self.stack.add_named(self.webview, "editor")
        self.stack.set_visible_child_name("loading")

        # Wait for server then switch to editor
        GLib.timeout_add(900, self._load_editor)

    def _load_editor(self):
        if server_port == 0:
            return True  # server not ready yet, retry
        self.webview.load_uri(f"http://127.0.0.1:{server_port}")
        self.stack.set_visible_child_name("editor")
        return False  # run once


def main():
    # Daemon thread dies automatically when GTK window closes
    threading.Thread(target=start_server, daemon=True).start()

    win = MakeCodeWindow()
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
