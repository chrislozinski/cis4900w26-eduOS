#!/usr/bin/env python3
"""
Classroom Manager:
a widget for the teacher to manage their classes, add or remove students,
and change availability of specific apps in the students' sidebar for each class.

Custom Web Apps:
Teachers can add URL-based apps (e.g. Google Classroom, Khan Academy) from the
Web Apps panel on the left. Once added globally, they appear in every classroom's
app checklist and can be enabled per-classroom like any other app.

Data lives in /shared/classrooms.json which is only writable by those with the teacher role.
"""
import gi
import json
import os
import shlex

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

CLASSROOMS_FILE     = '/shared/classrooms.json'
AVAILABLE_APPS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'available-apps.json')

#  Helpers 

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
    except PermissionError:
        raise RuntimeError(
            f"Cannot write to {CLASSROOMS_FILE}. "
            "Make sure you are in the 'teacher' group and the file is group writable.")

def load_available_apps():
    """Return the full list of static apps teachers can grant to students."""
    try:
        with open(AVAILABLE_APPS_FILE, 'r') as f:
            return json.load(f).get('available_apps', [])
    except Exception:
        return []

def _web_app_to_item(wa):
    """
    Convert a web_apps entry into the same shape as an available-apps entry
    so it can be dropped directly into a classroom's enabled_apps list.
    The command launches webapp-viewer.py with the title and URL as args.
    shlex.quote handles labels/URLs that contain spaces or special chars.
    """
    viewer = "~/.config/launcher/webapp-viewer.py"
    cmd    = f"python3 {viewer} {shlex.quote(wa['label'])} {shlex.quote(wa['url'])}"
    return {
        "type":         "webapp",
        "label":        wa["label"],
        "window_title": wa["label"],
        "icon":         wa.get("icon", "stylized/webSTYL.png"),
        "command":      cmd,
    }


#  Main window 

class ClassroomManager(Gtk.Window):
    def __init__(self):
        super().__init__(title="Classroom Manager")
        self.set_default_size(900, 600)
        self.set_wmclass("classroom_manager", "ClassroomManager")
        self.connect('destroy', Gtk.main_quit)

        self.data            = load_classrooms()
        # ensure web_apps key exists for older classrooms.json files
        self.data.setdefault("web_apps", [])
        self.selected_cls_id = None
        self.selected_wa_idx = None   # index into data["web_apps"]

        #  Top-level layout ─
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(paned)

        #  LEFT PANEL ─
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_margin_top(12); left.set_margin_bottom(12)
        left.set_margin_start(12); left.set_margin_end(6)
        paned.pack1(left, False, False)
        paned.set_position(250)

        # — Classrooms section —
        cls_hdr = Gtk.Label()
        cls_hdr.set_markup("<b>Classrooms</b>")
        cls_hdr.set_halign(Gtk.Align.START)
        left.pack_start(cls_hdr, False, False, 0)

        cls_sw = Gtk.ScrolledWindow()
        cls_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cls_sw.set_size_request(-1, 200)
        left.pack_start(cls_sw, False, False, 0)

        self.cls_listbox = Gtk.ListBox()
        self.cls_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.cls_listbox.connect('row-selected', self._on_cls_selected)
        cls_sw.add(self.cls_listbox)

        cls_btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        left.pack_start(cls_btn_row, False, False, 0)

        add_cls_btn = Gtk.Button(label="+ New")
        add_cls_btn.connect('clicked', self._on_add_cls)
        cls_btn_row.pack_start(add_cls_btn, True, True, 0)

        del_cls_btn = Gtk.Button(label="Delete")
        del_cls_btn.get_style_context().add_class("destructive-btn")
        del_cls_btn.connect('clicked', self._on_del_cls)
        cls_btn_row.pack_start(del_cls_btn, False, False, 0)

        left.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # — Web Apps section —
        wa_hdr = Gtk.Label()
        wa_hdr.set_markup("<b>Custom Web Apps</b>")
        wa_hdr.set_halign(Gtk.Align.START)
        left.pack_start(wa_hdr, False, False, 0)

        wa_note = Gtk.Label(label="Add URL apps (e.g. Google Classroom).")
        wa_note.set_halign(Gtk.Align.START)
        wa_note.get_style_context().add_class("dim-label")
        left.pack_start(wa_note, False, False, 0)

        wa_sw = Gtk.ScrolledWindow()
        wa_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        wa_sw.set_size_request(-1, 160)
        left.pack_start(wa_sw, True, True, 0)

        self.wa_listbox = Gtk.ListBox()
        self.wa_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.wa_listbox.connect('row-selected', self._on_wa_selected)
        wa_sw.add(self.wa_listbox)

        wa_btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        left.pack_start(wa_btn_row, False, False, 0)

        add_wa_btn = Gtk.Button(label="+ Add Web App")
        add_wa_btn.connect('clicked', self._on_add_wa)
        wa_btn_row.pack_start(add_wa_btn, True, True, 0)

        del_wa_btn = Gtk.Button(label="Remove")
        del_wa_btn.get_style_context().add_class("destructive-btn")
        del_wa_btn.connect('clicked', self._on_del_wa)
        wa_btn_row.pack_start(del_wa_btn, False, False, 0)

        #  RIGHT PANEL 
        right_sw = Gtk.ScrolledWindow()
        right_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        paned.pack2(right_sw, True, False)

        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.right_box.set_margin_top(12); self.right_box.set_margin_bottom(12)
        self.right_box.set_margin_start(6); self.right_box.set_margin_end(12)
        right_sw.add(self.right_box)

        self._show_placeholder("Select a classroom on the left to manage it.")

        self._refresh_cls_list()
        self._refresh_wa_list()

    #  Refresh helpers 

    def _refresh_cls_list(self):
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

    def _refresh_wa_list(self):
        for row in self.wa_listbox.get_children():
            self.wa_listbox.remove(row)
        for idx, wa in enumerate(self.data.get('web_apps', [])):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            box.set_margin_top(6); box.set_margin_bottom(6)
            box.set_margin_start(10)

            lbl = Gtk.Label(label=wa['label'])
            lbl.set_halign(Gtk.Align.START)
            box.pack_start(lbl, False, False, 0)

            url_lbl = Gtk.Label(label=wa['url'])
            url_lbl.set_halign(Gtk.Align.START)
            url_lbl.get_style_context().add_class("dim-label")
            url_lbl.set_ellipsize(3)   # PANGO_ELLIPSIZE_END
            url_lbl.set_max_width_chars(30)
            box.pack_start(url_lbl, False, False, 0)

            row.add(box)
            row.wa_idx = idx
            self.wa_listbox.add(row)
        self.wa_listbox.show_all()

    #  Right panel helpers 

    def _clear_right(self):
        for child in self.right_box.get_children():
            self.right_box.remove(child)

    def _show_placeholder(self, text):
        self._clear_right()
        lbl = Gtk.Label(label=text)
        lbl.get_style_context().add_class("placeholder")
        self.right_box.pack_start(lbl, True, True, 0)
        self.right_box.show_all()

    #  Classroom selection & detail ─

    def _get_cls(self, cls_id):
        for c in self.data.get('classrooms', []):
            if c['id'] == cls_id:
                return c
        return None

    def _on_cls_selected(self, _lb, row):
        if row is None:
            return
        # deselect web apps list to avoid dual-selection confusion
        self.wa_listbox.unselect_all()
        self.selected_cls_id = row.cls_id
        cls = self._get_cls(row.cls_id)
        if cls:
            self._show_detail(cls)

    def _on_wa_selected(self, _lb, row):
        """Selecting a web app in the left panel just deselects classrooms — no detail panel needed."""
        if row is None:
            return
        self.cls_listbox.unselect_all()
        self.selected_cls_id = None
        self.selected_wa_idx = row.wa_idx
        self._show_placeholder(
            f"Web app: {self.data['web_apps'][row.wa_idx]['label']}\n"
            f"{self.data['web_apps'][row.wa_idx]['url']}\n\n"
            "Enable this app per-classroom using the checklist\n"
            "in the classroom detail view on the left.")

    #  Classroom CRUD ─

    def _on_add_cls(self, _btn):
        dialog = Gtk.Dialog(title="New Classroom", transient_for=self, flags=0)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL,
                           "Create", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        box.pack_start(Gtk.Label(label="Classroom name:"), False, False, 0)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("e.g. Math 101")
        box.pack_start(name_entry, False, False, 0)
        box.pack_start(Gtk.Label(label="Classroom ID (no spaces):"), False, False, 0)
        id_entry = Gtk.Entry()
        id_entry.set_placeholder_text("e.g. math101")
        box.pack_start(id_entry, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        name   = name_entry.get_text().strip()
        cls_id = id_entry.get_text().strip().replace(' ', '_')
        dialog.destroy()

        if response != Gtk.ResponseType.OK or not name or not cls_id:
            return
        if self._get_cls(cls_id):
            self._error(f"ID '{cls_id}' already exists.")
            return
        self.data['classrooms'].append({
            'id': cls_id, 'name': name,
            'students': [], 'enabled_apps': []})
        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e)); return
        self._refresh_cls_list()

    def _on_del_cls(self, _btn):
        if not self.selected_cls_id:
            return
        cls = self._get_cls(self.selected_cls_id)
        if not cls:
            return
        confirm = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete classroom '{cls['name']}'?")
        confirm.format_secondary_text("This cannot be undone.")
        resp = confirm.run(); confirm.destroy()
        if resp != Gtk.ResponseType.YES:
            return
        self.data['classrooms'] = [
            c for c in self.data['classrooms'] if c['id'] != self.selected_cls_id]
        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e)); return
        self.selected_cls_id = None
        self._show_placeholder("Select a classroom on the left to manage it.")
        self._refresh_cls_list()

    #  Web App CRUD ─

    def _on_add_wa(self, _btn):
        dialog = Gtk.Dialog(title="Add Custom Web App", transient_for=self, flags=0)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL,
                           "Add", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(14); box.set_margin_end(14)

        box.pack_start(Gtk.Label(label="App name (shown in sidebar):"), False, False, 0)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("e.g. Google Classroom")
        name_entry.set_width_chars(40)
        box.pack_start(name_entry, False, False, 0)

        box.pack_start(Gtk.Label(label="URL:"), False, False, 0)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://classroom.google.com")
        url_entry.set_width_chars(40)
        box.pack_start(url_entry, False, False, 0)

        dialog.show_all()
        response = dialog.run()
        name = name_entry.get_text().strip()
        url  = url_entry.get_text().strip()
        dialog.destroy()

        if response != Gtk.ResponseType.OK or not name or not url:
            return

        # Ensure URL has a scheme so WebKit doesn't get confused
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Check for duplicate label
        if any(wa['label'] == name for wa in self.data['web_apps']):
            self._error(f"A web app named '{name}' already exists.")
            return

        self.data['web_apps'].append({'label': name, 'url': url})
        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e)); return
        self._refresh_wa_list()

        # If a classroom is currently open, refresh its checklist so the new
        # web app appears immediately without needing to re-select the classroom
        if self.selected_cls_id:
            cls = self._get_cls(self.selected_cls_id)
            if cls:
                self._show_detail(cls)

    def _on_del_wa(self, _btn):
        row = self.wa_listbox.get_selected_row()
        if row is None:
            return
        idx = row.wa_idx
        wa  = self.data['web_apps'][idx]

        confirm = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove web app '{wa['label']}'?")
        confirm.format_secondary_text(
            "It will also be removed from all classrooms where it was enabled.")
        resp = confirm.run(); confirm.destroy()
        if resp != Gtk.ResponseType.YES:
            return

        label = wa['label']
        self.data['web_apps'].pop(idx)

        # scrub from every classroom's enabled_apps
        for cls in self.data.get('classrooms', []):
            cls['enabled_apps'] = [
                a for a in cls.get('enabled_apps', []) if a.get('label') != label]

        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e)); return

        self.selected_wa_idx = None
        self._refresh_wa_list()
        if self.selected_cls_id:
            cls = self._get_cls(self.selected_cls_id)
            if cls:
                self._show_detail(cls)
        else:
            self._show_placeholder("Select a classroom on the left to manage it.")

    #  Classroom detail panel ─

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

        # Students
        s_hdr = Gtk.Label()
        s_hdr.set_markup("<b>Enrolled Students</b>")
        s_hdr.set_halign(Gtk.Align.START)
        self.right_box.pack_start(s_hdr, False, False, 0)

        self.student_lb = Gtk.ListBox()
        self.student_lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.student_lb.get_style_context().add_class("inner-list")
        for name in cls.get('students', []):
            self.student_lb.add(self._make_text_row(name, attr='student_name'))
        self.right_box.pack_start(self.student_lb, False, False, 0)

        s_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_s = Gtk.Button(label="+ Add Student")
        add_s.connect('clicked', self._on_add_student, cls)
        s_btns.pack_start(add_s, False, False, 0)
        rem_s = Gtk.Button(label="Remove Selected")
        rem_s.get_style_context().add_class("destructive-btn")
        rem_s.connect('clicked', self._on_rem_student, cls)
        s_btns.pack_start(rem_s, False, False, 0)
        self.right_box.pack_start(s_btns, False, False, 0)

        self.right_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Apps
        a_hdr = Gtk.Label()
        a_hdr.set_markup("<b>Apps Available to Students in this Classroom</b>")
        a_hdr.set_halign(Gtk.Align.START)
        self.right_box.pack_start(a_hdr, False, False, 0)

        note = Gtk.Label(
            label="Checked items appear in the sidebar of every enrolled student.")
        note.set_halign(Gtk.Align.START)
        note.get_style_context().add_class("dim-label")
        self.right_box.pack_start(note, False, False, 0)

        self.right_box.pack_start(self._build_app_checklist(cls), False, False, 0)
        self.right_box.show_all()

    #  App checklist (static apps + custom web apps merged) ─

    def _build_app_checklist(self, cls):
        """
        Checkbox list combining:
          1. Static apps from available-apps.json
          2. Custom web apps from classrooms.json["web_apps"]
        Toggle = immediate save.
        """
        enabled_labels = {app['label'] for app in cls.get('enabled_apps', [])}

        # Merge both sources into one flat list for display
        static_apps = load_available_apps()
        web_apps    = [_web_app_to_item(wa) for wa in self.data.get('web_apps', [])]
        all_apps    = static_apps + web_apps

        frame = Gtk.Frame()
        frame.get_style_context().add_class("inner-list")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        frame.add(vbox)

        if not all_apps:
            vbox.pack_start(
                Gtk.Label(label="No apps defined. Add apps or web apps on the left."),
                False, False, 8)
            return frame

        # Group separator between static apps and web apps
        shown_web_sep = False

        for app in all_apps:
            # Insert a visual divider before the first web app
            if app['type'] == 'webapp' and not shown_web_sep:
                shown_web_sep = True
                sep_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                sep_box.set_margin_start(10); sep_box.set_margin_end(10)
                sep_box.set_margin_top(4); sep_box.set_margin_bottom(2)
                sep_lbl = Gtk.Label()
                sep_lbl.set_markup("<small><i>Custom Web Apps</i></small>")
                sep_lbl.set_halign(Gtk.Align.START)
                sep_lbl.get_style_context().add_class("dim-label")
                sep_box.pack_start(sep_lbl, False, False, 0)
                vbox.pack_start(sep_box, False, False, 0)

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_box.set_margin_start(10); row_box.set_margin_end(10)
            row_box.set_margin_top(6);   row_box.set_margin_bottom(6)

            cb = Gtk.CheckButton()
            cb.set_active(app['label'] in enabled_labels)
            row_box.pack_start(cb, False, False, 0)

            desc = Gtk.Label()
            if app['type'] == 'webapp':
                # Show URL instead of command for web apps — more readable
                url = next(
                    (wa['url'] for wa in self.data.get('web_apps', [])
                     if wa['label'] == app['label']), '')
                desc.set_text(f"{app['label']}  [web]  {url}")
            else:
                detail = app.get('command', app.get('path', ''))
                desc.set_markup(
                    f"<b>{app['label']}</b>  "
                    f"<small>[{app['type']}]  {detail}</small>")
            desc.set_halign(Gtk.Align.START)
            row_box.pack_start(desc, True, True, 0)

            cb.connect('toggled', self._on_app_toggle, app, cls)
            vbox.pack_start(row_box, False, False, 0)

        return frame

    def _on_app_toggle(self, cb, app, cls):
        """Called when a checkbox is toggled — updates cls and saves immediately."""
        if cb.get_active():
            if not any(a['label'] == app['label'] for a in cls['enabled_apps']):
                cls['enabled_apps'].append(app)
        else:
            cls['enabled_apps'] = [
                a for a in cls['enabled_apps'] if a['label'] != app['label']]
        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e))

    #  Row factory & student management (unchanged) ─

    def _make_text_row(self, text, attr=None):
        row = Gtk.ListBoxRow()
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_margin_start(10); lbl.set_margin_top(5); lbl.set_margin_bottom(5)
        row.add(lbl)
        if attr:
            setattr(row, attr, text)
        return row

    def _on_add_student(self, _btn, cls):
        dialog = Gtk.Dialog(title="Add Student", transient_for=self, flags=0)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL,
                           "Add", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        box.pack_start(Gtk.Label(label="Student username:"), False, False, 0)
        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g. studentuser")
        box.pack_start(entry, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        username = entry.get_text().strip()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not username:
            return
        if username in cls['students']:
            self._error(f"'{username}' is already enrolled.")
            return
        cls['students'].append(username)
        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e)); return
        self._show_detail(cls)

    def _on_rem_student(self, _btn, cls):
        row = self.student_lb.get_selected_row()
        if not row or not hasattr(row, 'student_name'):
            return
        cls['students'] = [s for s in cls['students'] if s != row.student_name]
        try:
            save_classrooms(self.data)
        except RuntimeError as e:
            self._error(str(e)); return
        self._show_detail(cls)

    def _error(self, msg):
        d = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=msg)
        d.run(); d.destroy()


#  Entry point 

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
        .placeholder {
            color: #888888;
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

    win = ClassroomManager()
    win.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()