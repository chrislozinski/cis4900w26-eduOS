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
from urllib.parse import urlparse

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, Gdk, WebKit2

_AD_DOMAINS = {
    'doubleclick.net', 'googlesyndication.com', 'googletagmanager.com',
    'google-analytics.com', 'googleadservices.com', 'adservice.google.com',
    'amazon-adsystem.com', 'scorecardresearch.com', 'quantserve.com',
    'taboola.com', 'outbrain.com', 'criteo.com', 'pubmatic.com',
    'rubiconproject.com', 'openx.net', 'advertising.com', 'moatads.com',
}

_AD_CSS = """
    .adsbygoogle, [id^='google_ads'], [class*='GoogleAd'],
    [class*='advertisement'], [id*='advertisement'],
    [class*='sponsored-'], [data-ad], [data-ad-slot],
    ins.adsbygoogle { display: none !important; }
"""

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

    # match window background so blank canvas never shows as a white/light square
    webview.set_background_color(Gdk.RGBA(0.149, 0.149, 0.149, 1))  # #262626

    # use CSS to hide common ad elements
    cm = webview.get_user_content_manager()
    cm.add_style_sheet(WebKit2.UserStyleSheet(
        _AD_CSS,
        WebKit2.UserContentInjectedFrames.ALL_FRAMES,
        WebKit2.UserStyleLevel.USER,
        None, None))

    # Block ad networks and lock navigation to the original domain
    _origin = urlparse(url).netloc.lstrip('www.')
    def _on_decide_policy(wv, decision, dtype):
        if dtype in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                     WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            action  = decision.get_navigation_action()
            nav_url = action.get_request().get_uri()
            if nav_url.startswith(('http://', 'https://')):
                host = urlparse(nav_url).netloc.lstrip('www.')
                if any(host == d or host.endswith('.' + d) for d in _AD_DOMAINS):
                    decision.ignore()
                    return True
                if (action.get_navigation_type() == WebKit2.NavigationType.LINK_CLICKED
                        and host != _origin
                        and not host.endswith('.' + _origin)
                        and not _origin.endswith('.' + host)):
                    decision.ignore()
                    return True
        return False
    webview.connect('decide-policy', _on_decide_policy)

    settings = webview.get_settings()
    settings.set_enable_javascript(True)
    settings.set_enable_developer_extras(False)
    settings.set_allow_file_access_from_file_urls(False)
    # Allow the JS Clipboard API so web apps (e.g. Google Docs) can read/write the clipboard
    try:
        settings.set_javascript_can_access_clipboard(True)
    except AttributeError:
        pass  # older WebKit2 builds don't expose this setting

    # suppress right click context menu ? 
    webview.connect("context-menu", lambda *a: True)

    webview.load_uri(url)
    win.add(webview)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()