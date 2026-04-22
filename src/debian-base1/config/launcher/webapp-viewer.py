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
    win.set_position(Gtk.WindowPosition.CENTER)
    win.connect("destroy", Gtk.main_quit)

    context = WebKit2.WebContext.get_default()
    context.set_process_model(WebKit2.ProcessModel.MULTIPLE_SECONDARY_PROCESSES)

    font_px = max(11, int(Gdk.Screen.get_default().get_height() * 0.015))  # 16px at 1080p, 11px at 768p
    css = Gtk.CssProvider()
    css.load_from_data(f"""
        window {{
            background-color: #F2EEDE;
        }}
        progressbar {{
            padding: 4px;
            padding-bottom: 10px;
        }}
        progressbar text {{
            color: #2b2b2b;
            font-size: {font_px}px;
            padding: 4px;
            margin-bottom: 6px;
        }}
        progressbar trough {{
            background-color: #e0dccf;
            border-radius: 6px;
            min-height: 10px;
            box-shadow: inset 0 1px 2px rgba(0,0,0,0.15);
        }}
        progressbar progress {{
            background-color: #12921E;
            border-radius: 6px;
            min-height: 10px;
        }}
        """.encode('utf-8'))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    webview = WebKit2.WebView.new_with_context(context)
    webview.set_opacity(0)

    overlay = Gtk.Overlay()
    overlay.add(webview)

    progress = Gtk.ProgressBar()
    progress.set_halign(Gtk.Align.CENTER)
    progress.set_valign(Gtk.Align.CENTER)
    progress.set_size_request(300, -1)
    overlay.add_overlay(progress)
    progress.show()

    progress.set_show_text(True)
    progress.set_text("Loading…")

    first_load = True

    def _on_load_changed(wv, event):
        nonlocal first_load

        if first_load and event == WebKit2.LoadEvent.STARTED:
            progress.show()
            webview.set_opacity(0.0)
            progress.set_fraction(0.0)
            return

        if event == WebKit2.LoadEvent.FINISHED:
            progress.hide()
            webview.set_opacity(1.0)
            first_load = False

    webview.connect("load-changed", _on_load_changed)

    def _on_progress_notify(wv, pspec):
        if progress.get_visible():
            progress.set_fraction(wv.get_estimated_load_progress())

    webview.connect("notify::estimated-load-progress", _on_progress_notify)

    # use CSS to hide common ad elements
    cm = webview.get_user_content_manager()
    cm.add_style_sheet(WebKit2.UserStyleSheet(
        _AD_CSS,
        WebKit2.UserContentInjectedFrames.TOP_FRAME,
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
                # Only block when a user-initiated link click would navigate
                # away from the original domain (redirects/forms should be allowed).
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
    settings.set_enable_accelerated_2d_canvas(True)
    settings.set_enable_webgl(True)
    settings.set_hardware_acceleration_policy(
        WebKit2.HardwareAccelerationPolicy.ALWAYS
    )
    settings.set_javascript_can_open_windows_automatically(False)
    settings.set_allow_file_access_from_file_urls(False)
    settings.set_media_playback_requires_user_gesture(True)
    
    # Allow the JS Clipboard API so web apps (e.g. Google Docs) can read/write the clipboard
    try:
        settings.set_javascript_can_access_clipboard(True)
    except AttributeError:
        pass  # older WebKit2 builds don't expose this setting

    # suppress right click context menu ? 
    webview.connect("context-menu", lambda *a: True)

    webview.load_uri(url)
    win.add(overlay)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()