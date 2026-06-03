#!/usr/bin/env python3
"""
Lesson Builder
Teacher tool for creating and publishing MakeCode tutorial lessons.
"""
import gi
import importlib.util
import json
import getpass
import os
import threading
import time
import http.server
import socketserver
from urllib.parse import urlsplit, urlunsplit, unquote

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, WebKit2, GLib

_THIS_DIR       = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR      = "/opt/makecode/static"
CLASSROOMS_FILE = "/shared/classrooms.json"


# Module imports

def _import_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_lesson_list    = _import_module("lesson_list",    os.path.join(_THIS_DIR, "lesson-list.py"))
_lesson_storage = _import_module("lesson_storage", os.path.join(_THIS_DIR, "lesson-storage.py"))
_convert_lesson = _import_module("convert_lesson", os.path.join(_THIS_DIR, "convert-lesson.py")).convert_lesson


# HTTP server

server_port = 0


def get_preferred_port():
    uid = os.getuid()
    return 7700 + (uid % 300)


def rewrite_makecode_path(raw_path):
    """Rewrite MakeCode clean routes to static files present in the offline package."""
    parts = urlsplit(raw_path)
    path  = parts.path or "/"

    if path == "/--skillmap":
        path = "/skillmap.html"

    if path.startswith("/static/skillmap/"):
        doc_static = "/docs" + path
        if os.path.exists(os.path.join(STATIC_DIR, doc_static.lstrip("/"))):
            path = doc_static

    if path.startswith("/courses/"):
        docs_base  = "/docs" + path
        candidates = [docs_base + ".html", docs_base + "/index.html", docs_base]
        for cand in candidates:
            if os.path.exists(os.path.join(STATIC_DIR, cand.lstrip("/"))):
                path = cand
                break

    if path.startswith("/docs/") and not path.endswith(".html"):
        html_cand = path + ".html"
        if os.path.exists(os.path.join(STATIC_DIR, html_cand.lstrip("/"))):
            path = html_cand
        else:
            idx_cand = os.path.join(path, "index.html")
            if os.path.exists(os.path.join(STATIC_DIR, idx_cand.lstrip("/"))):
                path = idx_cand

    if path.startswith("/skillmap/") and not path.endswith(".html"):
        docs_skillmap = "/docs" + path
        html_cand     = docs_skillmap + ".html"
        if os.path.exists(os.path.join(STATIC_DIR, html_cand.lstrip("/"))):
            path = html_cand
        else:
            idx_cand = os.path.join(docs_skillmap, "index.html")
            if os.path.exists(os.path.join(STATIC_DIR, idx_cand.lstrip("/"))):
                path = idx_cand

    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _resolve_local_api_md(rel_under_docs):
    """Map /api/md/arcade/<path> to files under STATIC_DIR/docs/."""
    rel   = (rel_under_docs or "").split("?")[0].strip("/").replace("..", "")
    alias = {
        "skillmap/beg":      "skillmap/beginner-skillmap.md",
        "skillmap/beg.md":   "skillmap/beginner-skillmap.md",
        "skillmap/beginner": "skillmap/beginner-skillmap.md",
    }
    if rel in alias:
        rel = alias[rel]
    candidates = []
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


class LessonBuilderHandler(http.server.SimpleHTTPRequestHandler):
    def _send_file(self, path, content_type):
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

    def _mime(self, path):
        ext = os.path.splitext(path)[1].lower()
        return {
            ".html": "text/html; charset=utf-8",
            ".js":   "application/javascript; charset=utf-8",
            ".css":  "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg":  "image/svg+xml",
            ".png":  "image/png",
        }.get(ext, "application/octet-stream")

    def do_GET(self):
        parts = urlsplit(self.path)
        path  = unquote(parts.path or "/")

        if path.startswith("/lessonbuilder/"):
            rel   = path[len("/lessonbuilder/"):].lstrip("/") or "index.html"
            local = os.path.normpath(os.path.join(_THIS_DIR, "ui", rel.replace("..", "")))
            if os.path.isfile(local) and local.startswith(os.path.join(_THIS_DIR, "ui")):
                self._send_file(local, self._mime(local))
            else:
                self.send_error(404)
            return

        if path.startswith("/api/md/teacher-lessons/"):
            rel  = path[len("/api/md/teacher-lessons/"):].strip("/").split("/")
            if len(rel) >= 2:
                lesson_id = rel[0]
                filename  = rel[1].rstrip(".md") + ".md"
                local     = os.path.join("/shared/teacher-lessons", lesson_id, filename)
                if os.path.isfile(local):
                    self._send_file(local, "text/plain; charset=utf-8")
                else:
                    self.send_error(404)
            else:
                self.send_error(404)
            return

        if path.startswith("/api/md/arcade/"):
            local = _resolve_local_api_md(path[len("/api/md/arcade/"):].lstrip("/"))
            if local:
                self._send_file(local, "text/plain; charset=utf-8")
            else:
                self.send_error(404)
            return

        if path.startswith("/api/config/arcade/targetconfig"):
            tc = os.path.join(STATIC_DIR, "targetconfig.json")
            if os.path.isfile(tc):
                self._send_file(tc, "application/json; charset=utf-8")
            else:
                self.send_error(404)
            return

        self.path = rewrite_makecode_path(self.path)
        return super().do_GET()

    def do_HEAD(self):
        parts = urlsplit(self.path)
        path  = unquote(parts.path or "/")

        if path.startswith("/lessonbuilder/"):
            rel   = path[len("/lessonbuilder/"):].lstrip("/") or "index.html"
            local = os.path.normpath(os.path.join(_THIS_DIR, "ui", rel.replace("..", "")))
            if os.path.isfile(local) and local.startswith(os.path.join(_THIS_DIR, "ui")):
                try:
                    length = os.path.getsize(local)
                except Exception:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", self._mime(local))
                self.send_header("Content-Length", str(length))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
            else:
                self.send_error(404)
            return

        if path.startswith("/api/md/teacher-lessons/"):
            rel  = path[len("/api/md/teacher-lessons/"):].strip("/").split("/")
            if len(rel) >= 2:
                lesson_id = rel[0]
                filename  = rel[1].rstrip(".md") + ".md"
                local     = os.path.join("/shared/teacher-lessons", lesson_id, filename)
                if not os.path.isfile(local):
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
            else:
                self.send_error(404)
            return

        if path.startswith("/api/md/arcade/"):
            local = _resolve_local_api_md(path[len("/api/md/arcade/"):].lstrip("/"))
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


def start_server():
    global server_port
    os.chdir(STATIC_DIR)
    handler             = LessonBuilderHandler
    handler.log_message = lambda *a: None
    preferred           = get_preferred_port()

    class _ReuseServer(socketserver.TCPServer):
        allow_reuse_address = True

    def _port_state_path():
        root = os.path.expanduser("~/.local/share/makecode/ports")
        try:
            os.makedirs(root, exist_ok=True)
        except Exception:
            return None
        return os.path.join(root, f"{getpass.getuser()}-builder.json")

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

    candidates = []
    saved = _load_saved_port()
    if saved:
        candidates.append(saved)
    candidates.extend(range(preferred, preferred + 50))
    seen    = set()
    ordered = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            ordered.append(p)

    for p in ordered:
        try:
            httpd       = _ReuseServer(("127.0.0.1", p), handler)
            server_port = httpd.server_address[1]
            _save_port(server_port)
            httpd.serve_forever()
            return
        except OSError:
            continue

    server_port = 0


# LessonBuilderWindow

class LessonBuilderWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Lesson Builder")
        self.set_default_size(1400, 900)
        self.connect("destroy", Gtk.main_quit)

        self.set_size_request(900, 600)
        self._username          = getpass.getuser()
        self._current_lesson_id = None
        self._current_step_idx  = None
        self._classrooms_cache  = None
        self.connect("focus-in-event", lambda w, e: self._refresh_classrooms() or False)

        self._paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self._paned)

        self._ui_webview = self._create_webview(
            os.path.join("/shared", "makecode", "profiles", self._username, "webkit-builder-ui")
        )
        self._paned.pack1(self._ui_webview, resize=True, shrink=False)

        self._makecode_webview = self._create_webview(
            os.path.join("/shared", "makecode", "profiles", self._username, "webkit-sandbox")
        )
        self._makecode_box = Gtk.Box()
        self._makecode_box.pack_start(self._makecode_webview, True, True, 0)
        self._paned.pack2(self._makecode_box, resize=True, shrink=False)
        self._makecode_box.set_visible(False)

        self._setup_bridges()
        GLib.timeout_add(200, self._wait_for_server)

    def _create_webview(self, profile_dir):
        manager_cls = getattr(WebKit2, "WebsiteDataManager", None)
        if not manager_cls:
            return WebKit2.WebView()

        data_dir  = os.path.join(profile_dir, "data")
        cache_dir = os.path.join(profile_dir, "cache")
        try:
            os.makedirs(data_dir,  mode=0o775, exist_ok=True)
            os.makedirs(cache_dir, mode=0o775, exist_ok=True)
        except Exception:
            return WebKit2.WebView()

        manager = None
        try:
            manager = manager_cls(data_dir, cache_dir)
        except Exception:
            try:
                manager = manager_cls(base_data_directory=data_dir, base_cache_directory=cache_dir)
            except Exception:
                pass
        if not manager:
            return WebKit2.WebView()

        try:
            if manager.is_ephemeral():
                manager = None
        except Exception:
            pass
        if not manager:
            return WebKit2.WebView()

        try:
            context = WebKit2.WebContext.new_with_website_data_manager(manager)
        except Exception:
            return WebKit2.WebView()

        try:
            cm = getattr(WebKit2, "CacheModel", None)
            if cm and hasattr(cm, "WEB_BROWSER"):
                context.set_cache_model(cm.WEB_BROWSER)
        except Exception:
            pass

        try:
            webview = WebKit2.WebView.new_with_context(context)
        except Exception:
            return WebKit2.WebView()

        settings = webview.get_settings()
        settings.set_enable_javascript(True)
        try:
            settings.set_enable_html5_database(True)
            settings.set_enable_html5_local_storage(True)
        except Exception:
            pass
        webview.connect("context-menu", lambda *a: True)
        return webview

    def _apply_cdn_rewrite(self, webview):
        """Inject XHR/fetch rewrite so MakeCode CDN requests stay local."""
        if server_port == 0:
            return
        cm = webview.get_user_content_manager()
        if not cm:
            return
        origin = json.dumps(f"http://127.0.0.1:{server_port}")
        js = (
            "(function(){var L=" + origin +
            ";var H=['https://cdn.makecode.com','http://cdn.makecode.com',"
            "'https://www.makecode.com','http://www.makecode.com',"
            "'https://arcade.makecode.com','http://arcade.makecode.com'];"
            "function rw(u){if(u==null||typeof u!=='string')return u;"
            "for(var i=0;i<H.length;i++){if(u.indexOf(H[i])===0){"
            "return L+u.slice(H[i].length);}}return u;}"
            "var xo=XMLHttpRequest.prototype.open;"
            "XMLHttpRequest.prototype.open=function(m,u){"
            "return xo.apply(this,[m,rw(u)].concat([].slice.call(arguments,2)));};"
            "if(window.fetch){var _of=window.fetch;window.fetch=function(i,n){"
            "if(typeof i==='string')i=rw(i);"
            "else if(i&&typeof Request!=='undefined'&&i instanceof Request){"
            "var u=rw(i.url);if(u!==i.url)i=new Request(u,i);}"
            "return _of.call(this,i,n);}}"
            "})();"
        )
        try:
            script = WebKit2.UserScript.new(
                js,
                WebKit2.UserContentInjectedFrames.ALL_FRAMES,
                WebKit2.UserScriptInjectionTime.START,
                None, None,
            )
            cm.add_script(script)
        except Exception:
            pass

    def _setup_bridges(self):
        ui_cm = self._ui_webview.get_user_content_manager()
        if ui_cm:
            ui_cm.register_script_message_handler("lessonAction")
            ui_cm.connect("script-message-received::lessonAction", self._on_lesson_action)

        mc_cm = self._makecode_webview.get_user_content_manager()
        if mc_cm:
            mc_cm.register_script_message_handler("editorChanged")
            mc_cm.connect("script-message-received::editorChanged", self._on_code_autosave)
            self._inject_autosave_script(mc_cm)

    def _inject_autosave_script(self, content_manager):
        js = r"""
(function() {
    var debounce = null;

    function attachIfNeeded() {
        if (!window.monaco || monaco.editor.getEditors().length === 0) return;
        var ed = monaco.editor.getEditors()[0];
        if (ed.__lessonListenerAttached) return;
        ed.__lessonListenerAttached = true;
        ed.onDidChangeModelContent(function() {
            clearTimeout(debounce);
            debounce = setTimeout(function() {
                window.webkit.messageHandlers.editorChanged.postMessage(ed.getValue());
            }, 1500);
        });
    }

    // Re-checks every 800ms so the listener re-attaches after importproject
    // replaces the Monaco instance.
    setInterval(attachIfNeeded, 800);
})();
"""
        try:
            script = WebKit2.UserScript.new(
                js,
                WebKit2.UserContentInjectedFrames.MAIN_FRAME,
                WebKit2.UserScriptInjectionTime.END,
                None, None,
            )
            content_manager.add_script(script)
        except Exception:
            pass

    def _on_code_autosave(self, manager, result):
        try:
            code = result.get_js_value().to_string()
        except Exception:
            return
        if not code or self._current_lesson_id is None or self._current_step_idx is None:
            return
        draft = _lesson_storage.load_draft(self._current_lesson_id)
        if not draft:
            return
        steps = draft.get("steps", [])
        if self._current_step_idx < len(steps):
            steps[self._current_step_idx]["captured_code"] = code
            draft["steps"] = steps
            _lesson_storage.save_draft(self._current_lesson_id, draft)

    def _send_to_ui(self, payload):
        try:
            self._ui_webview.run_javascript(
                f"window.receiveFromPython({json.dumps(payload)})",
                None, None, None,
            )
        except Exception:
            pass

    def _on_lesson_action(self, manager, result):
        try:
            msg    = json.loads(result.get_js_value().to_string())
            action = msg.get("action", "")
            data   = msg.get("data") or {}
        except Exception:
            return
        try:
            {
                "init":            self._handle_init,
                "createLesson":    self._handle_create,
                "loadDraft":       self._handle_load_draft,
                "saveDraft":       self._handle_save_draft,
                "publishLesson":   self._handle_publish,
                "unpublishLesson": self._handle_unpublish,
                "deleteLesson":    self._handle_delete,
                "recoverLesson":   self._handle_recover,
                "permanentDelete": self._handle_perma_delete,
                "getTrash":        self._handle_get_trash,
                "previewLesson":   self._handle_preview,
                "cleanupPreview":  self._handle_cleanup_preview,
                "showEditor":      lambda d: self._set_editor_visible(True),
                "hideEditor":      lambda d: self._set_editor_visible(False),
                "setCurrentStep":  self._handle_set_current_step,
                "setCurrentLesson": self._handle_set_current_lesson,
                "setEditorCode":   self._handle_set_editor_code,
                "renameLesson":    self._handle_rename,
            }.get(action, lambda d: None)(data)
        except Exception as e:
            self._send_to_ui({"action": "error", "source": action, "error": str(e)})

    def _handle_init(self, data):
        try:
            with open(CLASSROOMS_FILE, "r") as f:
                cls_data = json.load(f)
        except Exception:
            cls_data = {"classrooms": [], "web_apps": []}
        self._send_to_ui({
            "action":     "initData",
            "classrooms": cls_data.get("classrooms", []),
            "drafts":     _lesson_storage.load_drafts_index(),
        })

    def _handle_create(self, data):
        lesson_id = _lesson_storage.create_draft(
            data.get("title", "Untitled Lesson"),
            "makecode",
            data.get("description", ""),
            data.get("classroomId", ""),
        )
        self._send_to_ui({
            "action":   "lessonCreated",
            "lessonId": lesson_id,
            "draft":    _lesson_storage.load_draft(lesson_id),
        })

    def _handle_load_draft(self, data):
        lesson_id = data.get("lessonId")
        draft     = _lesson_storage.load_draft(lesson_id) if lesson_id else None
        self._current_lesson_id = lesson_id
        self._current_step_idx  = 0
        self._send_to_ui({"action": "draftLoaded", "lessonId": lesson_id, "draft": draft})

    def _handle_save_draft(self, data):
        lesson_id  = data.get("lessonId")
        draft_data = data.get("draft")
        if lesson_id and draft_data:
            _lesson_storage.save_draft(lesson_id, draft_data)
        self._send_to_ui({"action": "draftSaved", "lessonId": lesson_id})

    def _handle_publish(self, data):
        lesson_id    = data.get("lessonId")
        classroom_id = data.get("classroomId")
        draft        = data.get("draft") or _lesson_storage.load_draft(lesson_id)
        if not draft:
            self._send_to_ui({"action": "error", "source": "publishLesson", "error": "Draft not found"})
            return
        _lesson_storage.publish_lesson(
            lesson_id,
            _convert_lesson(draft),
            draft.get("solution_code", ""),
            classroom_id,
        )
        self._send_to_ui({"action": "lessonPublished", "lessonId": lesson_id, "classroomId": classroom_id})
        try:
            with open(CLASSROOMS_FILE, "r") as f:
                cls_data = json.load(f)
            classrooms = cls_data.get("classrooms", [])
            serialized = json.dumps(classrooms, sort_keys=True)
            self._classrooms_cache = serialized
            self._send_to_ui({"action": "classroomsUpdated", "classrooms": classrooms})
        except Exception:
            pass

    def _handle_unpublish(self, data):
        _lesson_storage.unpublish_lesson(data.get("lessonId"), data.get("classroomId"))
        self._send_to_ui({
            "action":      "lessonUnpublished",
            "lessonId":    data.get("lessonId"),
            "classroomId": data.get("classroomId"),
        })

    def _handle_delete(self, data):
        lesson_id = data.get("lessonId")
        if lesson_id == self._current_lesson_id:
            self._current_lesson_id = None
            self._current_step_idx  = None
        _lesson_storage.move_to_bin(lesson_id)
        self._send_to_ui({"action": "lessonDeleted", "lessonId": lesson_id})

    def _handle_recover(self, data):
        lesson_id = data.get("lessonId")
        _lesson_storage.recover_draft(lesson_id)
        self._send_to_ui({
            "action":   "lessonRecovered",
            "lessonId": lesson_id,
            "draft":    _lesson_storage.load_draft(lesson_id),
        })

    def _handle_perma_delete(self, data):
        lesson_id = data.get("lessonId")
        _lesson_storage.permanent_delete(lesson_id)
        self._send_to_ui({"action": "lessonPermanentlyDeleted", "lessonId": lesson_id})

    def _handle_get_trash(self, data):
        self._send_to_ui({"action": "trashLoaded", "items": _lesson_storage.load_trash_index()})

    def _handle_preview(self, data):
        lesson_id   = data.get("lessonId")
        draft_input = data.get("draft")
        draft       = draft_input or _lesson_storage.load_draft(lesson_id)
        if not draft:
            self._send_to_ui({"action": "error", "source": "previewLesson", "error": "Draft not found"})
            return
        _lesson_storage.write_preview(lesson_id, _convert_lesson(draft))
        if server_port != 0:
            url = f"http://127.0.0.1:{server_port}/#tutorial:/api/md/teacher-lessons/{lesson_id}/tutorial"
            GLib.idle_add(self._open_preview_window, url, lesson_id)
        self._send_to_ui({"action": "previewReady", "lessonId": lesson_id})

    def _handle_cleanup_preview(self, data):
        _lesson_storage.cleanup_preview(data.get("lessonId"))

    def _handle_set_current_step(self, data):
        idx = data.get("stepIndex")
        if idx is not None:
            self._current_step_idx = int(idx)

    def _handle_set_current_lesson(self, data):
        self._current_lesson_id = data.get("lessonId")
        self._current_step_idx  = int(data.get("stepIndex", 0))

    def _handle_set_editor_code(self, data):
        self._do_import_project(data.get("code") or "")

    _PXT_JSON = json.dumps({
        "name": "Lesson Sandbox",
        "dependencies": {"core": "*"},
        "description": "",
        "files": ["main.blocks", "main.ts"],
    })
    _EMPTY_BLOCKS = '<xml xmlns="http://www.w3.org/1999/xhtml"></xml>'

    def _do_import_project(self, code):
        msg = json.dumps({
            "type":   "pxteditor",
            "action": "importproject",
            "id":     "lesson-step",
            "project": {
                "text": {
                    "main.ts":     code or "",
                    "main.blocks": self._EMPTY_BLOCKS,
                    "pxt.json":    self._PXT_JSON,
                }
            },
        })
        self._makecode_webview.run_javascript(
            f"window.postMessage({msg}, '*')",
            None, None, None,
        )
        self._makecode_webview.run_javascript(
            'window.postMessage({type:"pxteditor",action:"switchjavascript",id:"sw-js"}, "*")',
            None, None, None,
        )

    def _handle_rename(self, data):
        lesson_id = data.get("lessonId")
        title     = (data.get("title") or "").strip()
        if not lesson_id or not title:
            return
        draft = _lesson_storage.load_draft(lesson_id)
        if draft:
            draft["title"] = title
            _lesson_storage.save_draft(lesson_id, draft)
        _lesson_storage._update_index_entry(lesson_id, {"title": title})
        self._send_to_ui({"action": "lessonRenamed", "lessonId": lesson_id, "title": title})

    def _refresh_classrooms(self):
        try:
            with open(CLASSROOMS_FILE, "r") as f:
                cls_data = json.load(f)
            classrooms = cls_data.get("classrooms", [])
            serialized = json.dumps(classrooms, sort_keys=True)
            if serialized == self._classrooms_cache:
                return
            self._classrooms_cache = serialized
            self._send_to_ui({"action": "classroomsUpdated", "classrooms": classrooms})
        except Exception:
            pass

    def _set_editor_visible(self, visible):
        def _update():
            self._makecode_box.set_visible(visible)
            if visible:
                self._paned.set_position(420)
            return False
        GLib.idle_add(_update)

    def _open_preview_window(self, url, lesson_id):
        win = Gtk.Window(title="Lesson Preview")
        win.set_default_size(1280, 900)
        win.connect("destroy", lambda w: _lesson_storage.cleanup_preview(lesson_id))

        preview = self._create_webview(
            os.path.join("/shared", "makecode", "profiles", self._username, "webkit-preview")
        )
        self._apply_cdn_rewrite(preview)
        win.add(preview)
        win.show_all()
        preview.load_uri(url)
        return False

    def _wait_for_server(self):
        if server_port == 0:
            return True
        GLib.idle_add(self._load_webviews)
        return False

    def _load_webviews(self):
        base         = f"http://127.0.0.1:{server_port}"
        profile_data = os.path.join(
            "/shared", "makecode", "profiles", self._username, "webkit-sandbox", "data"
        )
        self._apply_cdn_rewrite(self._makecode_webview)
        self._ui_webview.load_uri(f"{base}/lessonbuilder/index.html")
        try:
            has_data = os.path.isdir(profile_data) and any(os.scandir(profile_data))
        except Exception:
            has_data = False
        if has_data:
            self._makecode_webview.load_uri(f"{base}/")
        else:
            self._makecode_webview.load_uri(f"{base}/#newproject")
        return False


def main():
    threading.Thread(target=start_server, daemon=True).start()
    win = LessonBuilderWindow()
    win.realize()
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
