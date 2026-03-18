#!/usr/bin/env python3
"""
Web App Viewer
Opens a given URL in a focused native GTK + WebKit2 window.
Usage: webapp-viewer.py <title> <url>

The window title is set to <title> so launcher.py's existing
get_open_tabs() deduplication works with no changes.
i3 matches all instances via: for_window [instance="webapp_viewer"]
"""
import gi
import sys

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, Gdk, WebKit2


def main():
    if len(sys.argv) < 3:
        print("Usage: webapp-viewer.py <title> <url>")
        sys.exit(1)

    title = sys.argv[1]
    url   = sys.argv[2]

    win = Gtk.Window(title=title)
    win.set_wmclass("webapp_viewer", "WebAppViewer")
    win.set_default_size(1280, 900)
    win.connect("destroy", Gtk.main_quit)

    css = Gtk.CssProvider()
    css.load_from_data(b"window { background-color: #262626; }")
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    webview = WebKit2.WebView()

    settings = webview.get_settings()
    settings.set_enable_javascript(True)
    settings.set_enable_developer_extras(False)
    settings.set_allow_file_access_from_file_urls(False)
    # Allow the JS Clipboard API so web apps (e.g. Google Docs) can
    # read/write the clipboard; keyboard Ctrl+C/V works regardless
    try:
        settings.set_javascript_can_access_clipboard(True)
    except AttributeError:
        pass  # older WebKit2 builds don't expose this setting

    # suppress right-click context menu for clean app feel
    webview.connect("context-menu", lambda *a: True)

    webview.load_uri(url)
    win.add(webview)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()