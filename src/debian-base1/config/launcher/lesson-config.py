#!/usr/bin/env python3
"""
Lesson Config
Teacher-facing tool for configuring per-classroom lesson resources.
Currently manages the Library (approved research sites per classroom).
Designed to accept additional lesson modules in the future.
"""
import gi
import json
import os
import shlex
import sys

# Make lessonBuilder modules importable from the deployed path or dev source tree.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LESSON_BUILDER_DIR = None
for _cand in [
    "/opt/cis4900/widgets/lessonBuilder",
    os.path.join(_THIS_DIR, "lessonBuilder"),
    os.path.join(_THIS_DIR, "..", "..", "widgets", "lessonBuilder"),
]:
    if os.path.isdir(_cand):
        _LESSON_BUILDER_DIR = _cand
        break
if _LESSON_BUILDER_DIR and _LESSON_BUILDER_DIR not in sys.path:
    sys.path.insert(0, _LESSON_BUILDER_DIR)

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

CLASSROOMS_FILE = '/shared/classrooms.json'

LESSON_CATALOG = [
    {
        "id":          "course_csintro1",
        "type":        "Course",
        "title":       "CS Intro 1",
        "description": "Core intro course with guided lessons and projects.",
    },
    {
        "id":          "course_csintro2",
        "type":        "Course",
        "title":       "CS Intro 2",
        "description": "Functions, tilemaps, logic, arrays, and projects.",
    },
    {
        "id":          "course_csintro3",
        "type":        "Course",
        "title":       "CS Intro 3",
        "description": "TypeScript-focused intermediate CS content.",
    },
    {
        "id":          "skillmap_beginner",
        "type":        "Skillmap",
        "title":       "Beginner Skillmap",
        "description": "Step-by-step interactive coding path.",
    },
    {
        "id":          "open_editor",
        "type":        "Editor",
        "title":       "Open Free Editor",
        "description": "Allow students to open the full MakeCode editor.",
    },
]


def load_classrooms():
    if os.path.exists(CLASSROOMS_FILE):
        try:
            with open(CLASSROOMS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"classrooms": [], "web_apps": []}


def save_classrooms(data):
    try:
        with open(CLASSROOMS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        raise RuntimeError(f"Failed to save {CLASSROOMS_FILE}: {e}")


class LessonConfig(Gtk.Window):
    def __init__(self):
        super().__init__(title="Lesson Config")
        self.set_default_size(860, 580)
        self.set_wmclass("lesson_config", "LessonConfig")
        self.connect('destroy', Gtk.main_quit)

        self.data             = load_classrooms()
        self.selected_cls_id  = None

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(paned)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_margin_top(12); left.set_margin_bottom(12)
        left.set_margin_start(12); left.set_margin_end(6)
        paned.pack1(left, False, False)
        paned.set_position(220)

        cls_hdr = Gtk.Label()
        cls_hdr.set_markup("<b>Classrooms</b>")
        cls_hdr.set_halign(Gtk.Align.START)
        left.pack_start(cls_hdr, False, False, 0)

        cls_sw = Gtk.ScrolledWindow()
        cls_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        left.pack_start(cls_sw, True, True, 0)

        self.cls_listbox = Gtk.ListBox()
        self.cls_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.cls_listbox.connect('row-selected', self._on_cls_selected)
        cls_sw.add(self.cls_listbox)

        right_sw = Gtk.ScrolledWindow()
        right_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        paned.pack2(right_sw, True, False)

        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.right_box.set_margin_top(12); self.right_box.set_margin_bottom(12)
        self.right_box.set_margin_start(6); self.right_box.set_margin_end(12)
        right_sw.add(self.right_box)

        self.connect("focus-in-event", self._on_focus)
        self._show_placeholder("Select a classroom to configure its lesson resources.")
        self._refresh_cls_list()

    def _refresh_cls_list(self):
        self.data = load_classrooms()
        for row in self.cls_listbox.get_children():
            self.cls_listbox.remove(row)
        for cls in self.data.get('classrooms', []):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_top(8); box.set_margin_bottom(8)
            box.set_margin_start(10)
            name_lbl = Gtk.Label(label=cls['name'])
            name_lbl.set_halign(Gtk.Align.START)
            box.pack_start(name_lbl, False, False, 0)
            id_lbl = Gtk.Label()
            id_lbl.set_markup(f"<small>{cls['id']}</small>")
            id_lbl.set_halign(Gtk.Align.START)
            id_lbl.get_style_context().add_class("dim-label")
            box.pack_start(id_lbl, False, False, 0)
            row.add(box)
            row.cls_id = cls['id']
            self.cls_listbox.add(row)
        self.cls_listbox.show_all()

    def _clear_right(self):
        for child in self.right_box.get_children():
            self.right_box.remove(child)

    def _show_placeholder(self, text):
        self._clear_right()
        lbl = Gtk.Label(label=text)
        lbl.get_style_context().add_class("dim-label")
        self.right_box.pack_start(lbl, True, True, 0)
        self.right_box.show_all()

    def _get_cls(self, cls_id):
        for c in self.data.get('classrooms', []):
            if c['id'] == cls_id:
                return c
        return None

    def _on_focus(self, widget, event):
        if not self.selected_cls_id:
            return False
        self.data = load_classrooms()
        cls = self._get_cls(self.selected_cls_id)
        if cls:
            self._show_detail(cls)
        return False

    def _on_cls_selected(self, _lb, row):
        if row is None:
            return
        self.selected_cls_id = row.cls_id
        cls = self._get_cls(row.cls_id)
        if cls:
            self._show_detail(cls)

    def _show_detail(self, cls):
        self._clear_right()

        title_lbl = Gtk.Label()
        title_lbl.set_markup(
            f"<big><b>{cls['name']}</b></big>  "
            f"<small>id: {cls['id']}</small>")
        title_lbl.set_halign(Gtk.Align.START)
        self.right_box.pack_start(title_lbl, False, False, 0)

        self.right_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)

        self.right_box.pack_start(self._build_library_section(cls), False, False, 0)

        self.right_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        self.right_box.pack_start(self._build_lessons_section(cls), False, False, 0)
        self.right_box.show_all()

    def _build_library_section(self, cls):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        hdr = Gtk.Label()
        hdr.set_markup("<b>Library Sites</b>")
        hdr.set_halign(Gtk.Align.START)
        section.pack_start(hdr, False, False, 0)

        note = Gtk.Label(
            label="Sites students can open from their Library app.")
        note.set_halign(Gtk.Align.START)
        note.get_style_context().add_class("dim-label")
        section.pack_start(note, False, False, 0)

        self.sites_lb = Gtk.ListBox()
        self.sites_lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sites_lb.get_style_context().add_class("inner-list")

        for site in cls.get('library_sites', []):
            self.sites_lb.add(self._make_site_row(site))

        section.pack_start(self.sites_lb, False, False, 0)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_btn = Gtk.Button(label="+ Add Site")
        add_btn.connect('clicked', self._on_add_site, cls)
        btn_row.pack_start(add_btn, False, False, 0)

        rem_btn = Gtk.Button(label="Remove Selected")
        rem_btn.get_style_context().add_class("destructive-btn")
        rem_btn.connect('clicked', self._on_rem_site, cls)
        btn_row.pack_start(rem_btn, False, False, 0)

        section.pack_start(btn_row, False, False, 0)
        return section

    def _make_site_row(self, site):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(10)

        name_lbl = Gtk.Label(label=site.get('label', ''))
        name_lbl.set_halign(Gtk.Align.START)
        box.pack_start(name_lbl, False, False, 0)

        url_lbl = Gtk.Label(label=site.get('url', ''))
        url_lbl.set_halign(Gtk.Align.START)
        url_lbl.get_style_context().add_class("dim-label")
        url_lbl.set_ellipsize(3)
        url_lbl.set_max_width_chars(50)
        box.pack_start(url_lbl, False, False, 0)

        row.add(box)
        row.site_label = site.get('label', '')
        return row

    def _on_add_site(self, _btn, cls):
        dialog = Gtk.Dialog(title="Add Library Site", transient_for=self, flags=0)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL,
                           "Add", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(14); box.set_margin_end(14)

        box.pack_start(Gtk.Label(label="Site name (shown to students):"), False, False, 0)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("e.g. Encyclopaedia Britannica")
        name_entry.set_width_chars(44)
        box.pack_start(name_entry, False, False, 0)

        box.pack_start(Gtk.Label(label="URL:"), False, False, 0)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://www.britannica.com")
        url_entry.set_width_chars(44)
        box.pack_start(url_entry, False, False, 0)

        dialog.show_all()
        response = dialog.run()
        name = name_entry.get_text().strip()
        url  = url_entry.get_text().strip()
        dialog.destroy()

        if response != Gtk.ResponseType.OK or not name or not url:
            return

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        sites = cls.setdefault('library_sites', [])

        if any(s['label'] == name for s in sites):
            self._error(f"A site named '{name}' already exists in this classroom.")
            return

        sites.append({'label': name, 'url': url})

        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e)); return

        self._show_detail(cls)

    def _on_rem_site(self, _btn, cls):
        row = self.sites_lb.get_selected_row()
        if row is None:
            return

        label = row.site_label
        cls['library_sites'] = [
            s for s in cls.get('library_sites', []) if s['label'] != label]

        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e)); return

        self._show_detail(cls)

    def _build_lessons_section(self, cls):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        hdr = Gtk.Label()
        hdr.set_markup("<b>MakeCode Lessons</b>")
        hdr.set_halign(Gtk.Align.START)
        section.pack_start(hdr, False, False, 0)

        note = Gtk.Label(label="Checked lessons appear on students' MakeCode home screen.")
        note.set_halign(Gtk.Align.START)
        note.get_style_context().add_class("dim-label")
        section.pack_start(note, False, False, 0)

        enabled_ids = set(cls.get('enabled_lessons', []))

        frame = Gtk.Frame()
        frame.get_style_context().add_class("inner-list")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        frame.add(vbox)

        type_colors = {"Skillmap": "#7c4dbd", "Tutorial": "#3d9970", "Course": "#0078d4", "Editor": "#e0791d"}
        shown_type = None

        for lesson in LESSON_CATALOG:
            if lesson["type"] != shown_type:
                shown_type = lesson["type"]
                sep_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                sep_box.set_margin_start(10); sep_box.set_margin_end(10)
                sep_box.set_margin_top(6);   sep_box.set_margin_bottom(2)
                sep_lbl = Gtk.Label()
                color = type_colors.get(lesson["type"], "#666")
                sep_lbl.set_markup(
                    f'<small><b><span foreground="{color}">{lesson["type"]}s</span></b></small>')
                sep_lbl.set_halign(Gtk.Align.START)
                sep_box.pack_start(sep_lbl, False, False, 0)
                vbox.pack_start(sep_box, False, False, 0)

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_box.set_margin_start(10); row_box.set_margin_end(10)
            row_box.set_margin_top(5);   row_box.set_margin_bottom(5)

            cb = Gtk.CheckButton()
            cb.set_active(lesson["id"] in enabled_ids)
            cb.connect("toggled", self._on_lesson_toggle, lesson["id"], cls)
            row_box.pack_start(cb, False, False, 0)

            desc = Gtk.Label()
            desc.set_markup(
                f'<b>{lesson["title"]}</b>  '
                f'<small>{lesson["description"]}</small>')
            desc.set_halign(Gtk.Align.START)
            row_box.pack_start(desc, True, True, 0)

            vbox.pack_start(row_box, False, False, 0)

        section.pack_start(frame, False, False, 0)

        # Teacher-published lessons from /shared/teacher-lessons/
        try:
            from lessonList import load_published_lessons
            teacher_lessons = load_published_lessons()
        except Exception:
            teacher_lessons = []

        if teacher_lessons:
            section.pack_start(
                Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

            teacher_hdr = Gtk.Label()
            teacher_hdr.set_markup("<b>Teacher Lessons</b>")
            teacher_hdr.set_halign(Gtk.Align.START)
            section.pack_start(teacher_hdr, False, False, 0)

            teacher_note = Gtk.Label(label="Lessons you created in Lesson Builder.")
            teacher_note.set_halign(Gtk.Align.START)
            teacher_note.get_style_context().add_class("dim-label")
            section.pack_start(teacher_note, False, False, 0)

            teacher_frame = Gtk.Frame()
            teacher_frame.get_style_context().add_class("inner-list")
            teacher_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            teacher_frame.add(teacher_vbox)

            for lesson in teacher_lessons:
                lid = lesson.get("id", "")
                if not lid:
                    continue
                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row_box.set_margin_start(10); row_box.set_margin_end(10)
                row_box.set_margin_top(5);   row_box.set_margin_bottom(5)

                cb = Gtk.CheckButton()
                cb.set_active(lid in enabled_ids)
                cb.connect("toggled", self._on_lesson_toggle, lid, cls)
                row_box.pack_start(cb, False, False, 0)

                desc = Gtk.Label()
                desc.set_markup(
                    f'<b><span foreground="#3d9970">{lesson.get("title", lid)}</span></b>  '
                    f'<small>{lesson.get("description", "")}</small>')
                desc.set_halign(Gtk.Align.START)
                row_box.pack_start(desc, True, True, 0)

                teacher_vbox.pack_start(row_box, False, False, 0)

            section.pack_start(teacher_frame, False, False, 0)

        return section

    def _on_lesson_toggle(self, cb, lesson_id, cls):
        ids = cls.setdefault('enabled_lessons', [])
        if cb.get_active():
            if lesson_id not in ids:
                ids.append(lesson_id)
        else:
            cls['enabled_lessons'] = [i for i in ids if i != lesson_id]
        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e))

    def _error(self, msg):
        d = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=msg)
        d.run(); d.destroy()


def main():
    css = b"""
        window {
            background-color: #F2EEDE;
            color: #262626;
        }
        label {
            color: #262626;
        }
        button {
            background-color: #0238c2;
            color: white;
            padding: 4px 12px;
            border: none;
            border-radius: 2px;
            min-height: 28px;
        }
        button:hover {
            background-color: #001f6e;
        }
        .destructive-btn {
            background-color: #a0161a;
        }
        .destructive-btn:hover {
            background-color: #700f12;
        }
        .inner-list {
            border: 1px solid #cccccc;
            border-radius: 2px;
        }
        row:selected {
            background-color: #c8d8f8;
        }
        row:selected label {
            color: #000000;
        }
        .dim-label {
            color: #888888;
            font-style: italic;
        }
        entry {
            background-color: #ffffff;
            color: #262626;
            border: 1px solid #aaaaaa;
            border-radius: 2px;
            padding: 4px;
        }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    win = LessonConfig()
    win.realize()
    win.set_opacity(0)
    win.show_all()
    GLib.timeout_add(150, lambda: win.set_opacity(1) or False)
    Gtk.main()


if __name__ == '__main__':
    main()