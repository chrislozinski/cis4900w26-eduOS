#!/usr/bin/env python3
"""
MakeCode Offline Editor
Serves the pre-built staticpkg from /opt/makecode/static
and renders it inside a native GTK + WebKit2 window.

Teacher  → opens full editor directly (unchanged behaviour).
Student  → opens a lesson landing page filtered by their classroom config,
           with a Home bar to return from within a lesson. Student browser
           data lives under ~/.local/share/makecode/<classId>/<username>/makecodeProfile/.
"""
import gi
import grp
import json
import getpass
import os
from datetime import datetime, timezone
import threading
import time
import http.server
import socketserver
import shutil
import urllib.request
from urllib.parse import urlsplit, urlunsplit, unquote

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, Gdk, WebKit2, GLib

STATIC_DIR      = "/opt/makecode/static"
CLASSROOMS_FILE = "/shared/classrooms.json"


def filesystem_safe_class_id(raw_id):
    """Safe directory segment for class id (supports students in multiple classes)."""
    if not raw_id or not isinstance(raw_id, str):
        return "_unassigned"
    cleaned = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in raw_id.strip()
    )
    return cleaned if cleaned else "_unassigned"


def student_makecode_profile_root(username, class_id):
    """
    Per-student WebKit profile (IndexedDB, localStorage) on the student's account:
    ~/.local/share/makecode/<classId>/<username>/makecodeProfile/{data,cache}/.
    """
    cid = filesystem_safe_class_id(class_id)
    return os.path.join(
        os.path.expanduser("~/.local/share"), "makecode", cid, username, "makecodeProfile"
    )


LESSON_CATALOG = [
    {
        "id":          "course_csintro1",
        "type":        "Course",
        "title":       "CS Intro 1",
        "description": "Core intro course with guided lessons and projects.",
        "url":         "/docs/courses/csintro1.html",
        "thumb":       "/docs/static/hero.svg",
    },
    {
        "id":          "course_csintro2",
        "type":        "Course",
        "title":       "CS Intro 2",
        "description": "Functions, tilemaps, logic, arrays, and projects.",
        "url":         "/docs/courses/csintro2.html",
        "thumb":       "/docs/static/hero.svg",
    },
    {
        "id":          "course_csintro3",
        "type":        "Course",
        "title":       "CS Intro 3",
        "description": "TypeScript-focused intermediate CS content.",
        "url":         "/docs/courses/csintro3.html",
        "thumb":       "/docs/static/hero.svg",
    },
    {
        "id":          "skillmap_beginner",
        "type":        "Skillmap",
        "title":       "Beginner Skillmap",
        "description": "Step-by-step interactive coding path.",
        "url":         "/--skillmap#beginner",
        "thumb":       "/docs/static/hero.svg",
    },
    {
        "id":          "open_editor",
        "type":        "Editor",
        "title":       "Open Free Editor",
        "description": "Start a new project from scratch.",
        "url":         "/",
        "thumb":       "/docs/static/icons/js.svg",
    },
]

LESSON_BY_ID = {l["id"]: l for l in LESSON_CATALOG}

server_port = 0


def rewrite_makecode_path(raw_path):
    """
    Rewrite MakeCode clean routes to static files present in the offline package.
    """
    parts = urlsplit(raw_path)
    path = parts.path or "/"

    # App route aliases provided by pxt redirects
    if path == "/--skillmap":
        path = "/skillmap.html"

    # Skillmap markdown uses /static/skillmap/... (live site); offline package stores
    # those assets under docs/static/skillmap/... when present.
    if path.startswith("/static/skillmap/"):
        doc_static = "/docs" + path
        if os.path.exists(os.path.join(STATIC_DIR, doc_static.lstrip("/"))):
            path = doc_static

    # Docs clean routes, e.g. /courses/csintro1/intro -> /docs/courses/csintro1/intro.html
    if path.startswith("/courses/"):
        docs_base = "/docs" + path
        candidates = [
            docs_base + ".html",
            docs_base + "/index.html",
            docs_base,
        ]
        for cand in candidates:
            if os.path.exists(os.path.join(STATIC_DIR, cand.lstrip("/"))):
                path = cand
                break
    # Skillmap/content loaders often request /docs/<name> without the .html extension.
    if path.startswith("/docs/") and not path.endswith(".html"):
        html_cand = path + ".html"
        if os.path.exists(os.path.join(STATIC_DIR, html_cand.lstrip("/"))):
            path = html_cand
        else:
            idx_cand = os.path.join(path, "index.html")
            if os.path.exists(os.path.join(STATIC_DIR, idx_cand.lstrip("/"))):
                path = idx_cand

    # Offline skillmap assets sometimes request /skillmap/<name> which lives
    # under /docs/skillmap/<name>.html in the static package.
    if path.startswith("/skillmap/") and not path.endswith(".html"):
        docs_skillmap = "/docs" + path
        html_cand = docs_skillmap + ".html"
        if os.path.exists(os.path.join(STATIC_DIR, html_cand.lstrip("/"))):
            path = html_cand
        else:
            idx_cand = os.path.join(docs_skillmap, "index.html")
            if os.path.exists(os.path.join(STATIC_DIR, idx_cand.lstrip("/"))):
                path = idx_cand

    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _resolve_local_api_md(rel_under_docs):
    """
    Map MakeCode CDN /api/md/arcade/<path> to files under STATIC_DIR/docs/.
    Requests may use skillmap/beginner-skillmap, docs/skillmap/foo (prefix docs/), or ?query only on live CDN.
    """
    rel = (rel_under_docs or "").split("?")[0].strip("/").replace("..", "")
    alias = {
        "skillmap/beg": "skillmap/beginner-skillmap.md",
        "skillmap/beg.md": "skillmap/beginner-skillmap.md",
        "skillmap/beginner": "skillmap/beginner-skillmap.md",
    }
    if rel in alias:
        rel = alias[rel]
    candidates = []
    # Paths already include leading docs/ (mirror CDN layout)
    if rel.startswith("docs/"):
        if not rel.endswith(".md"):
            candidates.append(os.path.join(STATIC_DIR, rel + ".md"))
        candidates.append(os.path.join(STATIC_DIR, rel))
    if not rel.endswith(".md"):
        candidates.append(os.path.join(STATIC_DIR, "docs", rel + ".md"))
    candidates.append(os.path.join(STATIC_DIR, "docs", rel))
    seen = set()
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        if os.path.isfile(p):
            return p
    return None


class MakeCodeStaticHandler(http.server.SimpleHTTPRequestHandler):
    def _send_file_bytes(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_error(404)

    def do_GET(self):
        parts = urlsplit(self.path)
        path = unquote(parts.path or "/")

        if path.startswith("/api/md/arcade/"):
            rel = path[len("/api/md/arcade/") :].lstrip("/")
            local = _resolve_local_api_md(rel)
            if local:
                self._send_file_bytes(local, "text/plain; charset=utf-8")
            else:
                self.send_error(404)
            return

        if path.startswith("/api/config/arcade/targetconfig"):
            tc = os.path.join(STATIC_DIR, "targetconfig.json")
            if os.path.isfile(tc):
                self._send_file_bytes(tc, "application/json; charset=utf-8")
            else:
                self.send_error(404)
            return

        self.path = rewrite_makecode_path(self.path)
        return super().do_GET()

    def do_HEAD(self):
        parts = urlsplit(self.path)
        path = unquote(parts.path or "/")

        if path.startswith("/api/md/arcade/"):
            rel = path[len("/api/md/arcade/") :].lstrip("/")
            local = _resolve_local_api_md(rel)
            if not local:
                self.send_error(404)
                return
            try:
                length = os.path.getsize(local)
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(length))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return

        if path.startswith("/api/config/arcade/targetconfig"):
            tc = os.path.join(STATIC_DIR, "targetconfig.json")
            if not os.path.isfile(tc):
                self.send_error(404)
                return
            try:
                length = os.path.getsize(tc)
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(length))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return

        self.path = rewrite_makecode_path(self.path)
        return super().do_HEAD()


def get_preferred_port():
    """
    Derive a stable port from the user's UID so the HTTP origin
    (http://127.0.0.1:PORT) is identical across logout/login.
    """
    uid = os.getuid()
    return 7700 + (uid % 300)


def start_server():
    global server_port
    os.chdir(STATIC_DIR)
    handler = MakeCodeStaticHandler
    handler.log_message = lambda *a: None
    preferred = get_preferred_port()

    class _ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    def _port_state_path():
        # Stable per-user port persistence so origin doesn't change across logins.
        root = os.path.expanduser("~/.local/share/makecode/ports")
        try:
            os.makedirs(root, exist_ok=True)
        except Exception:
            return None
        return os.path.join(root, f"{getpass.getuser()}.json")

    def _load_saved_port():
        pth = _port_state_path()
        if not pth:
            return None
        try:
            with open(pth, "r") as f:
                data = json.load(f)
            p = int(data.get("port", 0))
            return p if (1024 <= p <= 65535) else None
        except Exception:
            return None

    def _save_port(p):
        pth = _port_state_path()
        if not pth:
            return
        try:
            tmp = pth + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"port": int(p)}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, pth)
        except Exception:
            pass

    def _looks_like_our_server(p):
        # If a previous MakeCode server is still running on this port,
        # reuse it instead of switching origins.
        url = f"http://127.0.0.1:{p}/api/config/arcade/targetconfig"
        try:
            with urllib.request.urlopen(url, timeout=0.4) as resp:
                if resp.status != 200:
                    return False
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "json" not in ctype:
                    return False
                body = resp.read(5120) or b""
                # targetconfig.json should be JSON; avoid being too strict.
                return body.lstrip().startswith(b"{")
        except Exception:
            return False

    def _try_bind(p):
        return _ReusableTCPServer(("127.0.0.1", p), handler)

    # 1) If we previously selected a port, try it first (stable origin).
    candidates = []
    saved = _load_saved_port()
    if saved:
        candidates.append(saved)
    # 2) Then try the UID-derived preferred window.
    candidates.extend(range(preferred, preferred + 50))
    # Deduplicate while preserving order.
    seen = set()
    ordered = []
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        ordered.append(p)

    httpd = None
    for p in ordered:
        try:
            httpd = _try_bind(p)
            server_port = httpd.server_address[1]
            _save_port(server_port)
            httpd.serve_forever()
            return
        except OSError:
            # If another process is already serving *our* MakeCode static content,
            # reuse it rather than changing origins.
            if _looks_like_our_server(p):
                server_port = p
                _save_port(server_port)
                return
            continue

    # If we got here, nothing could be bound or reused.
    # Leave server_port=0 so the UI will stay on the loading screen rather than
    # silently switching to a random origin (which breaks persistence).
    server_port = 0


def get_user_role():
    try:
        if getpass.getuser() in grp.getgrnam("teacher").gr_mem:
            return "teacher"
    except KeyError:
        pass
    return "student"


def get_student_classroom():
    """
    Return (classroom_name, enabled_lesson_ids, class_id) for the current student.
    class_id comes from classrooms.json \"id\" (e.g. class001) for the profile path.
    """
    username = getpass.getuser()
    try:
        with open(CLASSROOMS_FILE, "r") as f:
            data = json.load(f)
        for cls in data.get("classrooms", []):
            if username in cls.get("students", []):
                name = cls.get("name", "Your Class")
                lessons = cls.get("enabled_lessons")
                if lessons is None:
                    lessons = cls.get("enabled_apps", [])
                cid = cls.get("id") or "_unassigned"
                return name, lessons, cid
    except Exception:
        pass
    return None, [], "_unassigned"


def update_student_makecode_profile(makecode_profile_dir):
    """Record that this student opened MakeCode and the on-disk browser profile path."""
    username = getpass.getuser()
    try:
        with open(CLASSROOMS_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return

    changed = False
    for cls in data.get("classrooms", []):
        if username not in cls.get("students", []):
            continue
        profiles = cls.setdefault("makecode_profiles", {})
        prior = profiles.get(username, {})
        profile = {
            "last_opened_utc": datetime.now(timezone.utc).isoformat(),
            "makecode_profile_dir": makecode_profile_dir or "",
        }
        if prior != profile:
            profiles[username] = profile
            changed = True
        break

    if changed:
        try:
            with open(CLASSROOMS_FILE, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            pass


def build_landing_html(base_url, classroom_name, enabled_ids):
    return build_landing_html_with_restore(base_url, classroom_name, enabled_ids, {})


def build_landing_html_with_restore(base_url, classroom_name, enabled_ids, restore_urls):
    type_colors = {
        "Skillmap": "#7c4dbd",
        "Tutorial": "#3d9970",
        "Course":   "#0078d4",
        "Editor":   "#e0791d",
    }

    lessons = [LESSON_BY_ID[lid] for lid in enabled_ids if lid in LESSON_BY_ID]

    cards_html = ""
    for lesson in lessons:
        color   = type_colors.get(lesson["type"], "#555")
        lesson_url = lesson["url"]
        restored = restore_urls.get(lesson["id"])
        if restored:
            # Allow restore_urls to be either absolute URLs or paths.
            if restored.startswith("http://") or restored.startswith("https://"):
                abs_url = restored
            else:
                abs_url = base_url.rstrip("/") + restored
        else:
            abs_url = base_url.rstrip("/") + lesson_url
        thumb = lesson.get("thumb")
        thumb_html = (
            f"<img class='card-thumb' src='{base_url.rstrip('/')}{thumb}' alt=''>"
            if thumb else
            "<div class='card-thumb card-thumb-fallback'></div>"
        )
        cards_html += f"""
        <div class="card" onclick="navigate('{abs_url}')">
          {thumb_html}
          <div class="card-body">
            <span class="badge" style="background:{color}">{lesson["type"]}</span>
            <div class="card-title">{lesson["title"]}</div>
            <div class="card-desc">{lesson["description"]}</div>
          </div>
        </div>"""

    empty_msg = "" if lessons else (
        '<p class="empty">Your teacher hasn\'t enabled any lessons yet.<br>'
        'Ask your teacher to enable lessons in Lesson Config.</p>'
    )

    class_badge = (
        f'<span class="class-badge">{classroom_name}</span>'
        if classroom_name else ""
    )
    section_title = "Your Lessons" if lessons else "Get Started"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MakeCode Lessons</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #1e1e1e;
    color: #f0f0f0;
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    min-height: 100vh;
    padding-bottom: 48px;
  }}
  .topbar {{
    background: #111;
    border-bottom: 3px solid #e0791d;
    padding: 16px 40px;
    display: flex;
    align-items: center;
    gap: 14px;
  }}
  .logo {{
    font-size: 22px;
    font-weight: 800;
    color: #e0791d;
    letter-spacing: -0.5px;
    user-select: none;
  }}
  .logo span {{ color: #fff; }}
  .class-badge {{
    background: #2d2d2d;
    border: 1px solid #444;
    color: #bbb;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    letter-spacing: 0.3px;
  }}
  .section-title {{
    font-size: 18px;
    font-weight: 700;
    color: #ddd;
    padding: 32px 40px 18px;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 12px;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: 14px;
    padding: 0 40px;
  }}
  .card {{
    background: #252525;
    border-radius: 10px;
    padding: 18px 20px;
    cursor: pointer;
    display: flex;
    gap: 16px;
    align-items: flex-start;
    border: 1px solid #333;
    transition: background 0.12s ease, transform 0.1s ease, border-color 0.12s ease;
  }}
  .card:hover {{
    background: #2e2e2e;
    transform: translateY(-2px);
    border-color: #505050;
  }}
  .card:active {{
    transform: translateY(0);
    background: #222;
  }}
  .card-thumb {{
    width: 54px;
    height: 54px;
    border-radius: 10px;
    overflow: hidden;
    flex-shrink: 0;
    border: 1px solid #333;
    background: #1a1a1a;
    object-fit: cover;
    display: grid;
    place-items: center;
    font-size: 22px;
    color: #e0791d;
  }}
  .card-thumb-fallback {{
    background: linear-gradient(135deg, rgba(224,121,29,0.15), rgba(0,0,0,0));
  }}
  .card-thumb-editor {{
    border-color: rgba(224,121,29,0.35);
  }}
  .card-body {{ flex: 1; min-width: 0; }}
  .badge {{
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    color: #fff;
    padding: 2px 7px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 8px;
  }}
  .card-title {{
    font-size: 15px;
    font-weight: 600;
    color: #fff;
    margin-bottom: 5px;
    line-height: 1.35;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .card-desc {{
    font-size: 12.5px;
    color: #999;
    line-height: 1.55;
  }}
  .card-editor {{
    border-color: rgba(224,121,29,0.2);
  }}
  .card-editor:hover {{
    border-color: rgba(224,121,29,0.5);
  }}
  .empty {{
    color: #666;
    font-size: 13.5px;
    padding: 12px 40px 20px;
    line-height: 1.7;
  }}
</style>
</head>
<body>
<div class="topbar">
  <div class="logo">Make<span>Code</span></div>
  {class_badge}
</div>
{empty_msg}
<div class="section-title">{section_title}</div>
<div class="grid">{cards_html}</div>
<script>
  function navigate(url) {{
    window.location.href = url;
  }}
</script>
</body>
</html>"""


class MakeCodeWindow(Gtk.Window):
    def __init__(self, role, classroom_name, enabled_ids, class_id="_unassigned"):
        super().__init__(title="MakeCode")
        self.set_default_size(1280, 900)
        self.connect("destroy", Gtk.main_quit)

        self._role          = role
        self._classroom     = classroom_name
        self._enabled_ids   = enabled_ids
        self._class_id      = filesystem_safe_class_id(class_id)
        self._landing_html  = None  # built once server port is known
        self._storage_dir   = ""
        self._username      = getpass.getuser()
        self._restore_urls  = {}
        self._current_key   = None
        self._current_uri   = None
        self._prev_key      = None
        self._prev_uri      = None
        self._last_btn      = None
        # True after a skillmap *tutorial/coding* step is open (not just the map shell).
        # Used to hide ↩ ↔ Open Editor to avoid glitching the shared editor iframe.
        self._skillmap_coding_started = False
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window { background-color: #1e1e1e; }
            .nav-bar { background-color: #111111; }
            button.home-btn {
                background-image: none;
                background-color: transparent;
                color: #e0791d;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 4px 12px;
                font-size: 13px;
                font-weight: bold;
                box-shadow: none;
                text-shadow: none;
            }
            button.home-btn:hover {
                background-color: #1e1e1e;
                border-color: #e0791d;
            }
            button.home-btn label { color: #e0791d; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.stack = Gtk.Stack()
        self.add(self.stack)

        # Loading screen
        loading_label = Gtk.Label()
        loading_label.set_markup(
            "<span foreground='#e0791d' size='large'>Loading MakeCode…</span>"
        )
        loading_label.set_halign(Gtk.Align.CENTER)
        loading_label.set_valign(Gtk.Align.CENTER)
        self.stack.add_named(loading_label, "loading")

        # WebKit view
        self.webview = self._create_webview()
        self._apply_offline_cdn_rewrite(self.webview)
        settings = self.webview.get_settings()
        settings.set_enable_javascript(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)
        settings.set_enable_developer_extras(False)
        try:
            settings.set_enable_html5_database(True)
            settings.set_enable_html5_local_storage(True)
        except Exception:
            pass
        self.webview.connect("context-menu", lambda *a: True)
        self.webview.connect("decide-policy", self._on_makecode_decide_policy)
        self.webview.connect("load-changed", self._on_makecode_load_changed)

        if role == "student":
            content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

            nav_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            nav_bar.get_style_context().add_class("nav-bar")
            nav_bar.set_margin_top(6)
            nav_bar.set_margin_bottom(6)
            nav_bar.set_margin_start(10)
            nav_bar.set_margin_end(10)

            home_btn = Gtk.Button(label="⌂  Lessons")
            home_btn.get_style_context().add_class("home-btn")
            home_btn.set_tooltip_text("Return to lesson picker")
            home_btn.connect("clicked", self._on_home_clicked)
            nav_bar.pack_start(home_btn, False, False, 0)

            self._last_btn = Gtk.Button(label="")
            self._last_btn.get_style_context().add_class("home-btn")
            self._last_btn.set_sensitive(False)
            self._last_btn.set_opacity(0.0)
            self._last_btn.connect("clicked", self._on_last_clicked)
            nav_bar.pack_start(self._last_btn, False, False, 0)

            content_box.pack_start(nav_bar, False, False, 0)
            content_box.pack_start(self.webview, True, True, 0)
            self.stack.add_named(content_box, "content")
        else:
            self.stack.add_named(self.webview, "content")

        self.stack.set_visible_child_name("loading")
        GLib.timeout_add(900, self._load_editor)

    def _create_webview(self):
        """
        Persistent WebKit WebsiteDataManager: IndexedDB and localStorage live on disk
        under base_dir/{data,cache}/.
        """
        username = self._username
        manager_cls = getattr(WebKit2, "WebsiteDataManager", None)
        if manager_cls is None:
            return WebKit2.WebView()

        if self._role == "student":
            candidates = [student_makecode_profile_root(username, self._class_id)]
        else:
            candidates = [
                os.path.join("/shared", "makecode", "profiles", username, "webkit"),
                os.path.join(os.path.expanduser("~/.local/share"), "makecode", "webkit"),
            ]

        base_dir = None
        cand_errors = []
        for cand in candidates:
            try:
                os.makedirs(cand, mode=0o775, exist_ok=True)
                test_path = os.path.join(cand, ".write_test")
                with open(test_path, "w") as f:
                    f.write("ok")
                os.remove(test_path)
                base_dir = cand
                break
            except Exception as e:
                cand_errors.append({"cand": cand, "err": repr(e)})
                continue

        if not base_dir:
            self._storage_dir = ""
            return WebKit2.WebView()

        data_dir = os.path.join(base_dir, "data")
        cache_dir = os.path.join(base_dir, "cache")
        try:
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(cache_dir, exist_ok=True)
        except Exception as e:
            self._storage_dir = ""
            return WebKit2.WebView()

        def _has_any_files(path):
            try:
                for _root, _dirs, files in os.walk(path):
                    if files:
                        return True
            except Exception:
                return False
            return False

        def _mirror_tree_best_effort(src, dst):
            try:
                for root, _dirs, files in os.walk(src):
                    rel = os.path.relpath(root, src)
                    dst_root = dst if rel == "." else os.path.join(dst, rel)
                    try:
                        os.makedirs(dst_root, exist_ok=True)
                    except Exception:
                        continue
                    for fn in files:
                        srcf = os.path.join(root, fn)
                        dstf = os.path.join(dst_root, fn)
                        try:
                            shutil.copy2(srcf, dstf)
                        except Exception:
                            pass
            except Exception:
                pass

        # Deterministic "rehydrate" step.
        # MakeCode projects live in IndexedDB, keyed by origin. WebKit must see the
        # same on-disk site data at startup to avoid an empty project list.
        data_has_files = _has_any_files(data_dir)
        cache_has_files = _has_any_files(cache_dir)
        if cache_has_files and (not data_has_files):
            _mirror_tree_best_effort(cache_dir, data_dir)
            data_has_files = _has_any_files(data_dir)
        if data_has_files and (not cache_has_files):
            _mirror_tree_best_effort(data_dir, cache_dir)

        # Always use `data/` as the WebKit "data" backend.
        effective_data_dir = data_dir

        manager = None
        # WebKit2GTK Python bindings don't necessarily expose GObject "new" helpers.
        # Runtime evidence (debug logs) shows `WebsiteDataManager.new` is missing here,
        # so we attempt common constructor patterns instead.
        try:
            manager = manager_cls(effective_data_dir, cache_dir)
        except Exception as e:
            try:
                manager = manager_cls(
                    base_data_directory=effective_data_dir,
                    base_cache_directory=cache_dir,
                )
            except Exception:
                manager = None

        if not manager:
            self._storage_dir = ""
            return WebKit2.WebView()
        try:
            if manager.is_ephemeral():
                manager = None
        except Exception:
            pass
        if not manager:
            self._storage_dir = ""
            return WebKit2.WebView()

        try:
            context = WebKit2.WebContext.new_with_website_data_manager(manager)
        except Exception:
            context = None
        if context is None:
            self._storage_dir = ""
            return WebKit2.WebView()

        try:
            cm = getattr(WebKit2, "CacheModel", None)
            if cm is not None and hasattr(cm, "WEB_BROWSER"):
                context.set_cache_model(cm.WEB_BROWSER)
        except Exception:
            pass

        abs_base = os.path.abspath(base_dir)
        abs_data = os.path.abspath(data_dir)
        abs_cache = os.path.abspath(cache_dir)
        add_sb = getattr(context, "add_path_to_sandbox", None)
        sandbox_added = []
        if add_sb:
            for path in (abs_base, abs_data, abs_cache):
                try:
                    add_sb(path, False)
                    sandbox_added.append(path)
                except Exception as e:
                    sandbox_added.append({"path": path, "err": repr(e)})

        try:
            webview = WebKit2.WebView.new_with_context(context)
        except Exception:
            webview = None
        if webview is None:
            self._storage_dir = ""
            return WebKit2.WebView()

        self._storage_dir = base_dir
        return webview

    def _apply_offline_cdn_rewrite(self, webview):
        """Rewrite fetch/XHR to makecode.com hosts into our static server (not covered by decide-policy)."""
        for _ in range(80):
            if server_port != 0:
                break
            time.sleep(0.025)
        if server_port == 0:
            return
        cm = webview.get_user_content_manager()
        if not cm:
            return
        origin = json.dumps(f"http://127.0.0.1:{server_port}")
        js = (
            "(function(){var L="
            + origin
            + ";var H=['https://cdn.makecode.com','http://cdn.makecode.com',"
            "'https://www.makecode.com','http://www.makecode.com',"
            "'https://arcade.makecode.com','http://arcade.makecode.com'];"
            "function rw(u){if(u==null||typeof u!=='string')return u;"
            "for(var i=0;i<H.length;i++){if(u.indexOf(H[i])===0){var t=u.slice(H[i].length);"
            "if(t.indexOf('/api/')===0)return L+t;break;}}return u;}"
            "var xo=XMLHttpRequest.prototype.open;"
            "XMLHttpRequest.prototype.open=function(m,u){var r=[].slice.call(arguments,2);"
            "return xo.apply(this,[m,rw(u)].concat(r));};"
            "if(window.fetch){var of=window.fetch;window.fetch=function(i,n){"
            "if(typeof i==='string')i=rw(i);"
            "else if(i&&typeof Request!=='undefined'&&i instanceof Request){"
            "var u=rw(i.url);if(u!==i.url)i=new Request(u,i);}"
            "return of.call(this,i,n);};}"
            "})();"
        )
        try:
            script = WebKit2.UserScript.new(
                js,
                WebKit2.UserContentInjectedFrames.ALL_FRAMES,
                WebKit2.UserScriptInjectionTime.START,
                None,
                None,
            )
            cm.add_script(script)
        except Exception:
            pass

    def _on_makecode_decide_policy(self, wv, decision, dtype):
        # Rewrite any navigations to the live domain back into our local offline server.
        # This is required because course/skillmap content often links to arcade.makecode.com
        # even when we're serving offline static files.
        try:
            if dtype in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                         WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
                action = decision.get_navigation_action()
                nav_url = action.get_request().get_uri()
                arcade_prefixes = (
                    "https://arcade.makecode.com",
                    "http://arcade.makecode.com",
                )
                cdn_prefixes = (
                    "https://cdn.makecode.com",
                    "http://cdn.makecode.com",
                )
                if server_port == 0:
                    return False
                base = f"http://127.0.0.1:{server_port}"
                parts = urlsplit(nav_url)
                path = parts.path or "/"
                rewrite = False
                if nav_url.startswith(arcade_prefixes):
                    rewrite = True
                elif nav_url.startswith(cdn_prefixes) and path.startswith("/api/"):
                    rewrite = True
                if rewrite:
                    local = base + path
                    if parts.query:
                        local += "?" + parts.query
                    if parts.fragment:
                        local += "#" + parts.fragment
                    decision.ignore()
                    wv.load_uri(local)
                    return True
        except Exception:
            return False
        return False

    def _on_makecode_load_changed(self, wv, event):
        # Capture where the user is so returning to the lesson picker
        # can restore their last position.
        try:
            if event != WebKit2.LoadEvent.FINISHED:
                return
            uri = wv.get_uri() or ""
            if "landing=1" in uri:
                return
            self._capture_location_from_webview(wv, None)
        except Exception:
            pass

    def _capture_location_from_webview(self, webview, done_callback):
        """
        WebKit get_uri() omits the URL fragment; MakeCode stores editor/skillmap
        state in the hash. Read window.location.href after load.
        """
        def _cb(wv, result, _ud):
            href = None
            try:
                js_result = wv.run_javascript_finish(result)
                if js_result:
                    v = js_result.get_js_value()
                    if v is not None:
                        href = v.to_string()
            except Exception:
                pass
            if not href:
                href = wv.get_uri() or ""
            if href and "landing=1" not in href:
                self._capture_restore_url(href)

            if done_callback:
                done_callback()

        try:
            webview.run_javascript("window.location.href", None, _cb, None)
        except Exception:
            href = webview.get_uri() or ""
            if href and "landing=1" not in href:
                self._capture_restore_url(href)
            if done_callback:
                done_callback()

    def _is_skillmap_app_uri(self, parts, uri):
        """The React skillmap shell — not tutorial HTML under /docs/skillmap/."""
        path = parts.path or ""
        frag = parts.fragment or ""
        if path.startswith("/docs/skillmap/"):
            return False
        if path.endswith("/skillmap.html") or path.rstrip("/").endswith("/--skillmap"):
            return True
        if path == "/--skillmap":
            return True
        if path in ("", "/"):
            q = (parts.query or "").lower()
            if "skillmap" in q:
                return True
            fl = frag.lower()
            if fl == "beginner" or fl.startswith("beginner"):
                return True
            if "docs:/skillmap" in frag or "doc:/docs/skillmap" in frag:
                return True
        return False

    def _maybe_mark_skillmap_coding_started(self, uri, parts):
        """
        Sticky for the WebView session until the user returns to the lesson picker.
        Detects skillmap iframe mode or a deep skillmap doc hash (not just #beginner / map md).
        """
        if self._role != "student":
            return
        low = uri.lower()
        if "skillmap=1" in low:
            self._skillmap_coding_started = True
            return
        frag = parts.fragment or ""
        doc_key = "docs:/skillmap/"
        alt_key = "doc:/docs/skillmap/"
        if doc_key not in frag and alt_key not in frag:
            return
        tail = frag.split(doc_key, 1)[-1] if doc_key in frag else frag.split(alt_key, 1)[-1]
        tail = tail.split("#")[0].split("?")[0].strip().lower().replace(".md", "")
        if not tail:
            return
        # Map graph definition only — still the skillmap shell, not a coding activity.
        if tail in ("beginner-skillmap", "beg", "beginner"):
            return
        self._skillmap_coding_started = True

    def _capture_restore_url(self, uri):
        if not uri or server_port == 0:
            return
        base = f"http://127.0.0.1:{server_port}"
        if not uri.startswith(base):
            return

        parts = urlsplit(uri)
        self._maybe_mark_skillmap_coding_started(uri, parts)
        frag = parts.fragment or ""
        # Hash-only doc routes keep path "/" but still belong to a course.
        combo = uri + " " + frag

        def _combo_has_course(seg):
            return (
                f"/courses/{seg}/" in combo
                or f"/docs/courses/{seg}/" in combo
                or f"/courses/{seg}." in combo
                or f"/docs/courses/{seg}." in combo
                or f"docs:/courses/{seg}/" in combo
                or f"docs:/courses/{seg}." in combo
                or f"doc:/docs/courses/{seg}/" in combo
                or f"doc:/docs/courses/{seg}." in combo
                or combo.rstrip("/").endswith(f"/courses/{seg}")
                or combo.rstrip("/").endswith(f"/docs/courses/{seg}")
            )

        # Skillmap app before editor: / with only #editor was misclassified as skillmap
        # if we checked skillmap too loosely — keep beginner/docs skillmap only on /.
        if self._is_skillmap_app_uri(parts, uri):
            self._restore_urls["skillmap_beginner"] = uri
            self._note_visit("skillmap_beginner", uri)
            return

        # Track CS Intro location and the free editor location so returning
        # to "Lessons" and then back to the editor keeps the project.
        # Match longer course ids first so csintro2 does not look like csintro.
        if _combo_has_course("csintro3"):
            self._restore_urls["course_csintro3"] = uri
            self._note_visit("course_csintro3", uri)
        elif _combo_has_course("csintro2"):
            self._restore_urls["course_csintro2"] = uri
            self._note_visit("course_csintro2", uri)
        elif _combo_has_course("csintro1"):
            self._restore_urls["course_csintro1"] = uri
            self._note_visit("course_csintro1", uri)
        else:
            # Base editor: MakeCode often navigates via hash routes
            # (e.g. "/#tutorial:/..."), so detect editor view by path == "/".
            if parts.path in ("", "/"):
                if "landing=1" not in parts.query:
                    self._restore_urls["open_editor"] = uri
                    self._note_visit("open_editor", uri)

    def _note_visit(self, key, uri):
        if not key or not uri:
            return
        if self._current_key == key and self._current_uri == uri:
            return
        # Same lesson "container" (e.g. CS Intro 1): only advance the deep
        # link for restore; do not rotate prev/current or the ↩ label changes.
        if self._current_key == key:
            self._current_uri = uri
            self._maybe_mark_skillmap_coding_started(uri, urlsplit(uri))
            self._update_last_button()
            return

        if self._current_key and self._current_uri:
            self._prev_key = self._current_key
            self._prev_uri = self._current_uri
        self._current_key = key
        self._current_uri = uri
        self._update_last_button()

    def _update_last_button(self):
        if not self._last_btn:
            return
        if self._prev_key and self._prev_uri:
            # Do not offer Open Editor while on the skillmap shell — same editor glue glitches.
            if (
                self._current_key == "skillmap_beginner"
                and self._prev_key == "open_editor"
            ):
                self._last_btn.set_label("")
                self._last_btn.set_sensitive(False)
                self._last_btn.set_opacity(0.0)
                return
            # After a skillmap coding step, hide all ↩ from the free editor for this session.
            if (
                self._current_key == "open_editor"
                and self._skillmap_coding_started
            ):
                self._last_btn.set_label("")
                self._last_btn.set_sensitive(False)
                self._last_btn.set_opacity(0.0)
                return
            label = LESSON_BY_ID.get(self._prev_key, {}).get("title", "Last")
            self._last_btn.set_label(f"↩  {label}")
            self._last_btn.set_sensitive(True)
            self._last_btn.set_opacity(1.0)
        else:
            self._last_btn.set_label("")
            self._last_btn.set_sensitive(False)
            self._last_btn.set_opacity(0.0)

    def _on_last_clicked(self, _btn):
        if not self._prev_uri:
            return
        target_key = self._prev_key
        target_uri = self._prev_uri
        if self._current_key == "skillmap_beginner" and target_key == "open_editor":
            return
        if self._current_key == "open_editor" and self._skillmap_coding_started:
            return

        def _after_capture():
            self._prev_key, self._current_key = self._current_key, target_key
            self._prev_uri, self._current_uri = self._current_uri, target_uri
            self._update_last_button()
            if target_uri:
                self.webview.load_uri(target_uri)

        self._capture_location_from_webview(self.webview, _after_capture)

    def _load_editor(self):
        if server_port == 0:
            return True
        base = f"http://127.0.0.1:{server_port}"
        if self._role == "teacher":
            self.webview.load_uri(base + "/")
        else:
            self._skillmap_coding_started = False
            html = build_landing_html_with_restore(
                base,
                self._classroom,
                self._enabled_ids,
                self._restore_urls,
            )
            self._landing_html = html
            self.webview.load_html(html, base + "/?landing=1")
            self._update_last_button()
        self.stack.set_visible_child_name("content")
        return False

    def _on_home_clicked(self, _btn):
        base = f"http://127.0.0.1:{server_port}"

        def _show_landing():
            self._skillmap_coding_started = False
            html = build_landing_html_with_restore(
                base,
                self._classroom,
                self._enabled_ids,
                self._restore_urls,
            )
            self._landing_html = html
            self.webview.load_html(html, base + "/?landing=1")
            self._update_last_button()

        self._capture_location_from_webview(self.webview, _show_landing)


def main():
    threading.Thread(target=start_server, daemon=True).start()

    role = get_user_role()
    if role == "student":
        classroom_name, enabled_ids, class_id = get_student_classroom()
    else:
        classroom_name, enabled_ids, class_id = None, [], "_unassigned"

    win = MakeCodeWindow(role, classroom_name, enabled_ids, class_id)
    if role == "student":
        fallback = student_makecode_profile_root(
            getpass.getuser(), win._class_id
        )
        update_student_makecode_profile(win._storage_dir or fallback)
    win.realize()
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
    