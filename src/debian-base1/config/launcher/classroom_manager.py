#!/usr/bin/env python3
"""
Classroom Manager: two-screen teacher UI for classrooms, pairing, delivery, export/import.
Data: /shared/classrooms.json
"""
import json
import os
import shlex
import socket
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

_HERE = os.path.dirname(os.path.abspath(__file__))
for p in (
    "/usr/local/share/cis4900-src/src/debian-base1",
    _HERE,
    os.path.dirname(os.path.dirname(_HERE)),
):
    if os.path.isdir(os.path.join(p, "network")) and p not in sys.path:
        sys.path.insert(0, p)

from network import archive, delivery, pairing  # noqa: E402
from network.bootstrap import ensureSharedClassrooms  # noqa: E402
from network.constants import CONTROL_DIR  # noqa: E402

CLASSROOMS_FILE = "/shared/classrooms.json"
AVAILABLE_APPS_FILE = os.path.join(_HERE, "available-apps.json")


def load_classrooms():
    if os.path.exists(CLASSROOMS_FILE):
        try:
            with open(CLASSROOMS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"classrooms": [], "web_apps": []}


def save_classrooms(data):
    """Atomic write so CM / agent / MakeCode never see a torn classrooms.json."""
    directory = os.path.dirname(CLASSROOMS_FILE) or "/shared"
    os.makedirs(directory, exist_ok=True)
    tmp = CLASSROOMS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CLASSROOMS_FILE)


def load_available_apps():
    try:
        with open(AVAILABLE_APPS_FILE, "r") as f:
            return json.load(f).get("available_apps", [])
    except Exception:
        return []


def _web_app_to_item(wa):
    viewer = "~/.config/launcher/webapp-viewer.py"
    cmd = f"python3 {viewer} {shlex.quote(wa['label'])} {shlex.quote(wa['url'])}"
    return {
        "type": "webapp",
        "label": wa["label"],
        "window_title": wa["label"],
        "icon": wa.get("icon", "stylized/globeInternet.svg"),
        "command": cmd,
        "url": wa["url"],
    }


def _canonical_app_list(data):
    """available-apps.json order, then custom web apps in stored order.
    Default apps are excluded: the launcher shows them unconditionally,
    so they are not part of a classroom's enabled_apps."""
    return [a for a in load_available_apps() if not a.get("default")] + [
        _web_app_to_item(wa) for wa in data.get("web_apps", [])
    ]


def _rebuild_enabled_apps(cls, data):
    enabled = {a.get("label") for a in cls.get("enabled_apps", [])}
    cls["enabled_apps"] = [
        app for app in _canonical_app_list(data) if app["label"] in enabled
    ]


def _lan_ip_guess() -> str:
    path = os.path.join(CONTROL_DIR, "lan_ip.txt")
    if os.path.isfile(path):
        try:
            return open(path).read().strip()
        except Exception:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


class ClassroomManager(Gtk.Window):
    def __init__(self):
        super().__init__(title="Classroom Manager")
        self.set_default_size(900, 640)
        self.set_wmclass("classroom_manager", "ClassroomManager")
        self.connect("destroy", Gtk.main_quit)

        ensureSharedClassrooms(CLASSROOMS_FILE)
        self.data = load_classrooms()
        self.data.setdefault("web_apps", [])
        self.selected_cls_id = None
        self._app_toggle_handlers = []
        self._poll_id = None

        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.root)

        self.list_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.list_page.set_margin_top(12)
        self.list_page.set_margin_bottom(12)
        self.list_page.set_margin_start(12)
        self.list_page.set_margin_end(12)
        self.root.pack_start(self.list_page, True, True, 0)

        self.detail_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.root.pack_start(self.detail_page, True, True, 0)

        self._build_list_page()
        self._show_list()

    def _build_list_page(self):
        hdr = Gtk.Label()
        hdr.set_markup("<big><b>Classrooms</b></big>")
        hdr.set_halign(Gtk.Align.START)
        self.list_page.pack_start(hdr, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_frame = Gtk.Frame()
        list_frame.get_style_context().add_class("inner-list")
        self.list_page.pack_start(list_frame, True, True, 0)
        list_frame.add(sw)

        self.cls_listbox = Gtk.ListBox()
        self.cls_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.cls_listbox.set_activate_on_single_click(False)
        # Double-click (or Enter) opens; single click only selects/highlights
        self.cls_listbox.connect("row-activated", self._on_cls_activated)
        self.cls_listbox.connect("row-selected", self._on_cls_selected)
        sw.add(self.cls_listbox)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.list_page.pack_start(btn_row, False, False, 0)

        add_btn = Gtk.Button(label="+ New")
        add_btn.connect("clicked", self._on_add_cls)
        btn_row.pack_start(add_btn, False, False, 0)

        del_btn = Gtk.Button(label="Delete")
        del_btn.get_style_context().add_class("destructive-btn")
        del_btn.connect("clicked", self._on_del_cls)
        btn_row.pack_start(del_btn, False, False, 0)

        btn_row.pack_start(Gtk.Label(), True, True, 0)

        import_btn = Gtk.Button(label="Import classroom")
        import_btn.connect("clicked", self._on_import)
        btn_row.pack_start(import_btn, False, False, 0)

        self._refresh_cls_list()

    def _show_list(self):
        self._stop_poll()
        self.selected_cls_id = None
        self.detail_page.hide()
        for child in self.detail_page.get_children():
            self.detail_page.remove(child)
        self.list_page.show_all()
        self._refresh_cls_list()

    def _show_detail(self, cls):
        self.list_page.hide()
        for child in self.detail_page.get_children():
            self.detail_page.remove(child)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.detail_page.pack_start(scroll, True, True, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_margin_top(12)
        body.set_margin_bottom(12)
        body.set_margin_start(12)
        body.set_margin_end(12)
        scroll.add(body)
        self.detail_body = body
        self.selected_cls_id = cls["id"]

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        back = Gtk.Button(label="< Back")
        back.connect("clicked", lambda *_: self._show_list())
        hdr.pack_start(back, False, False, 0)

        title = Gtk.Label()
        title.set_markup(
            f"<big><b>{cls['name']}</b></big>  <small>id: {cls['id']}</small>"
        )
        title.set_halign(Gtk.Align.START)
        hdr.pack_start(title, True, True, 0)

        export_btn = Gtk.Button(label="Export")
        export_btn.connect("clicked", self._on_export, cls["id"])
        hdr.pack_end(export_btn, False, False, 0)
        body.pack_start(hdr, False, False, 0)
        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)

        # Students + delivery
        s_hdr = Gtk.Label()
        s_hdr.set_markup("<b>Enrolled Students</b>")
        s_hdr.set_halign(Gtk.Align.START)
        body.pack_start(s_hdr, False, False, 0)

        self.student_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        body.pack_start(self.student_box, False, False, 0)
        self._rebuild_students(cls)

        s_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_s = Gtk.Button(label="+ Add Student")
        add_s.connect("clicked", self._on_add_student, cls["id"])
        s_btns.pack_start(add_s, False, False, 0)
        rem_s = Gtk.Button(label="Remove Selected")
        rem_s.get_style_context().add_class("destructive-btn")
        rem_s.connect("clicked", self._on_rem_student, cls["id"])
        s_btns.pack_start(rem_s, False, False, 0)
        body.pack_start(s_btns, False, False, 0)

        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Classroom Network (framed panel)
        n_hdr = Gtk.Label()
        n_hdr.set_markup("<b>Classroom Network</b>")
        n_hdr.set_halign(Gtk.Align.START)
        body.pack_start(n_hdr, False, False, 0)

        net_frame = Gtk.Frame()
        net_frame.get_style_context().add_class("inner-list")
        net_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        net_inner.set_margin_top(14)
        net_inner.set_margin_bottom(14)
        net_inner.set_margin_start(14)
        net_inner.set_margin_end(14)
        net_frame.add(net_inner)

        # Status left; clean join code + timer on the right
        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        self.net_status = Gtk.Label()
        self.net_status.set_halign(Gtk.Align.START)
        self.net_status.set_valign(Gtk.Align.CENTER)
        self.net_status.set_line_wrap(True)
        status_row.pack_start(self.net_status, True, True, 0)

        code_col = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        code_col.set_halign(Gtk.Align.END)
        self.code_lbl = Gtk.Label()
        self.code_lbl.set_halign(Gtk.Align.END)
        self.code_lbl.set_valign(Gtk.Align.CENTER)
        self.code_lbl.get_style_context().add_class("join-code")
        code_col.pack_start(self.code_lbl, False, False, 0)
        self.timer_lbl = Gtk.Label()
        self.timer_lbl.set_halign(Gtk.Align.END)
        self.timer_lbl.set_valign(Gtk.Align.CENTER)
        self.timer_lbl.get_style_context().add_class("join-timer")
        code_col.pack_start(self.timer_lbl, False, False, 0)
        status_row.pack_end(code_col, False, False, 0)
        net_inner.pack_start(status_row, False, False, 0)

        self.lan_lbl = Gtk.Label()
        self.lan_lbl.set_halign(Gtk.Align.START)
        self.lan_lbl.get_style_context().add_class("dim-label")
        net_inner.pack_start(self.lan_lbl, False, False, 0)

        net_inner.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
        )

        net_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        open_j = Gtk.Button(label="Open joining")
        open_j.connect("clicked", self._on_open_joining, cls["id"])
        net_btns.pack_start(open_j, False, False, 0)
        close_j = Gtk.Button(label="Close joining")
        close_j.connect("clicked", self._on_close_joining, cls["id"])
        net_btns.pack_start(close_j, False, False, 0)
        collect = Gtk.Button(label="Collect work")
        collect.connect("clicked", self._on_collect, cls["id"])
        net_btns.pack_start(collect, False, False, 0)
        resend_all = Gtk.Button(label="Resend all pending")
        resend_all.connect(
            "clicked", lambda *_: delivery.markForceResendAllPending(cls["id"])
        )
        net_btns.pack_start(resend_all, False, False, 0)
        net_inner.pack_start(net_btns, False, False, 0)

        self.collect_lbl = Gtk.Label()
        self.collect_lbl.set_halign(Gtk.Align.START)
        self.collect_lbl.set_line_wrap(True)
        self.collect_lbl.get_style_context().add_class("dim-label")
        net_inner.pack_start(self.collect_lbl, False, False, 0)

        body.pack_start(net_frame, False, False, 0)

        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Apps
        a_hdr = Gtk.Label()
        a_hdr.set_markup("<b>Apps Available to Students in this Classroom</b>")
        a_hdr.set_halign(Gtk.Align.START)
        body.pack_start(a_hdr, False, False, 0)
        note = Gtk.Label(
            label="Checked items appear in the sidebar of every enrolled student."
        )
        note.set_halign(Gtk.Align.START)
        note.get_style_context().add_class("dim-label")
        body.pack_start(note, False, False, 0)
        self._pending_connects = []
        body.pack_start(self._build_app_checklist(cls), False, False, 0)

        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        # Custom web apps
        wa_hdr = Gtk.Label()
        wa_hdr.set_markup("<b>Custom Web Apps</b>")
        wa_hdr.set_halign(Gtk.Align.START)
        body.pack_start(wa_hdr, False, False, 0)
        body.pack_start(self._build_webapps_section(), False, False, 0)

        self.detail_page.show_all()
        for old_cb, hid in self._app_toggle_handlers:
            try:
                old_cb.disconnect(hid)
            except Exception:
                pass
        self._app_toggle_handlers = []
        for cb, app, cls_id in self._pending_connects:
            hid = cb.connect("toggled", self._on_app_toggle, app, cls_id)
            self._app_toggle_handlers.append((cb, hid))
        self._pending_connects = []

        self._refresh_network_panel()
        self._stop_poll()
        self._poll_id = GLib.timeout_add_seconds(1, self._poll_tick)

    def _poll_tick(self):
        if not self.selected_cls_id:
            return False
        try:
            self.data = load_classrooms()
        except Exception:
            pass
        cls = self._get_cls(self.selected_cls_id)
        if not cls:
            return False
        self._refresh_network_panel()
        self._rebuild_students(cls)
        self.detail_page.show_all()
        return True

    def _stop_poll(self):
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = None

    def _refresh_network_panel(self):
        if not self.selected_cls_id:
            return
        cid = self.selected_cls_id
        st = pairing.readStatus(cid)
        lan = _lan_ip_guess()
        if hasattr(self, "lan_lbl"):
            self.lan_lbl.set_text(f"LAN IP: {lan}")
        if st.get("joining_enabled") and st.get("code_plain"):
            import time
            left = max(0, int(float(st.get("expires_at") or 0) - time.time()))
            mm, ss = divmod(left, 60)
            self.code_lbl.set_text(st["code_plain"])
            if hasattr(self, "timer_lbl"):
                self.timer_lbl.set_text(f"{mm}:{ss:02d}")
            join_state = "OPEN"
        else:
            self.code_lbl.set_text("")
            if hasattr(self, "timer_lbl"):
                self.timer_lbl.set_text("Joining closed")
            join_state = "CLOSED"
        delivered = pending = failed = 0
        cls = self._get_cls(cid)
        for sid in (cls or {}).get("students", []):
            label, _ = delivery.uiStatus(cid, sid)
            if label == "delivered":
                delivered += 1
            elif label == "failed":
                failed += 1
            else:
                pending += 1
        self.net_status.set_markup(
            f"Joining: <b>{join_state}</b>   ·   "
            f"{delivered} delivered · {pending} pending · {failed} failed"
        )
        ddata = delivery.load(cid)
        collected = [
            sid
            for sid, e in ddata.get("students", {}).items()
            if e.get("collect_requested") is False
            and os.path.isfile(
                os.path.join("/shared/classroom-work", cid, sid, "work.json")
            )
        ]
        self.collect_lbl.set_text(
            "Work cache: "
            + (", ".join(collected) if collected else "none yet (Collect work, then wait for student sync)")
        )

    def _on_open_joining(self, _btn, cls_id):
        try:
            pairing.ensureDirs()
            try:
                os.chmod(CONTROL_DIR, 0o775)
            except OSError:
                pass
            data = pairing.openJoining(cls_id)
            self._refresh_network_panel()
            if not (data.get("joining_enabled") and data.get("code_plain")):
                self._error("Unable to open joining because: status write did not enable joining.")
        except Exception as e:
            self._error(f"Unable to open joining because: {e}")

    def _on_close_joining(self, _btn, cls_id):
        try:
            pairing.ensureDirs()
            pairing.closeJoining(cls_id)
            self._refresh_network_panel()
        except Exception as e:
            self._error(f"Unable to close joining because: {e}")

    def _rebuild_students(self, cls):
        # The 1s network poll rebuilds this list; remember the selection so
        # "Remove Selected" still has a selected row afterwards
        sel_name = None
        old_lb = getattr(self, "student_lb", None)
        if old_lb is not None:
            sel_row = old_lb.get_selected_row()
            if sel_row is not None:
                sel_name = getattr(sel_row, "student_name", None)
        for child in self.student_box.get_children():
            self.student_box.remove(child)
        self.student_lb = Gtk.ListBox()
        self.student_lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
        student_frame = Gtk.Frame()
        student_frame.get_style_context().add_class("inner-list")
        student_frame.add(self.student_lb)
        for name in cls.get("students", []):
            row = Gtk.ListBoxRow()
            h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            h.set_margin_start(8)
            h.set_margin_end(8)
            h.set_margin_top(4)
            h.set_margin_bottom(4)
            lbl = Gtk.Label(label=name)
            lbl.set_halign(Gtk.Align.START)
            h.pack_start(lbl, False, False, 0)
            status, sub = delivery.uiStatus(cls["id"], name)
            st = Gtk.Label(label=f"{status.capitalize()} · {sub}" if sub else status.capitalize())
            st.set_halign(Gtk.Align.START)
            st.get_style_context().add_class("dim-label")
            h.pack_start(st, True, True, 0)
            resend = Gtk.Button(label="Resend")
            resend.connect(
                "clicked",
                lambda _b, sid=name, cid=cls["id"]: delivery.markForceResend(cid, sid),
            )
            h.pack_end(resend, False, False, 0)
            row.add(h)
            row.student_name = name
            self.student_lb.add(row)
        if sel_name is not None:
            for row in self.student_lb.get_children():
                if getattr(row, "student_name", None) == sel_name:
                    self.student_lb.select_row(row)
                    break
        self.student_box.pack_start(student_frame, False, False, 0)
        self.student_box.show_all()

    def _refresh_cls_list(self):
        self.data = load_classrooms()
        for row in self.cls_listbox.get_children():
            self.cls_listbox.remove(row)
        for cls in self.data.get("classrooms", []):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(10)
            name_lbl = Gtk.Label(label=cls["name"])
            name_lbl.set_halign(Gtk.Align.START)
            box.pack_start(name_lbl, False, False, 0)
            id_lbl = Gtk.Label()
            id_lbl.set_markup(f"<small>id: {cls['id']}</small>")
            id_lbl.set_halign(Gtk.Align.START)
            id_lbl.get_style_context().add_class("dim-label")
            box.pack_start(id_lbl, False, False, 0)
            row.add(box)
            row.cls_id = cls["id"]
            self.cls_listbox.add(row)
        self.cls_listbox.show_all()

    def _get_cls(self, cls_id):
        for c in self.data.get("classrooms", []):
            if c["id"] == cls_id:
                return c
        return None

    def _on_cls_selected(self, _lb, row):
        if row is None:
            return
        self.selected_cls_id = row.cls_id

    def _on_cls_activated(self, _lb, row):
        if row is None:
            return
        cls = self._get_cls(row.cls_id)
        if cls:
            self._show_detail(cls)

    def _on_add_cls(self, _btn):
        dialog = Gtk.Dialog(title="New Classroom", transient_for=self, flags=0)
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL, "Create", Gtk.ResponseType.OK
        )
        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.pack_start(Gtk.Label(label="Classroom name:"), False, False, 0)
        name_entry = Gtk.Entry()
        box.pack_start(name_entry, False, False, 0)
        box.pack_start(Gtk.Label(label="Classroom ID (no spaces):"), False, False, 0)
        id_entry = Gtk.Entry()
        box.pack_start(id_entry, False, False, 0)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        response = dialog.run()
        name = name_entry.get_text().strip()
        cls_id = id_entry.get_text().strip().replace(" ", "_")
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not name or not cls_id:
            return
        if self._get_cls(cls_id):
            self._error(f"ID '{cls_id}' already exists.")
            return
        self.data["classrooms"].append(
            {"id": cls_id, "name": name, "students": [], "enabled_apps": []}
        )
        self._ensure_save()
        self._refresh_cls_list()

    def _on_del_cls(self, _btn):
        row = self.cls_listbox.get_selected_row()
        if row is None:
            return
        cls = self._get_cls(row.cls_id)
        if not cls:
            return
        extra = ""
        if delivery.workCacheHasBundles(cls["id"]):
            extra = (
                "\n\nThis classroom has collected student work on this teacher machine. "
                "Export first if you need a backup. Delete removes the classroom entry "
                "and the teacher work cache for this id."
            )
        confirm = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete classroom '{cls['name']}'?",
        )
        confirm.format_secondary_text("This cannot be undone." + extra)
        resp = confirm.run()
        confirm.destroy()
        if resp != Gtk.ResponseType.YES:
            return
        self.data["classrooms"] = [
            c for c in self.data["classrooms"] if c["id"] != cls["id"]
        ]
        self._ensure_save()
        # best-effort clear work cache
        import shutil
        cache = os.path.join("/shared/classroom-work", cls["id"])
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
        self._refresh_cls_list()

    def _on_import(self, _btn):
        info = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Import a classroom export folder",
        )
        info.format_secondary_text(
            "Please select the classroom export folder with classroom.json and student-data."
        )
        resp = info.run()
        info.destroy()
        if resp != Gtk.ResponseType.OK:
            return

        dialog = Gtk.FileChooserDialog(
            title="Import classroom (select export folder)",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            "Import", Gtk.ResponseType.OK,
        )
        if dialog.run() != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        path = dialog.get_filename()
        dialog.destroy()
        replace = False
        try:
            archive.importClassroom(path, CLASSROOMS_FILE, replaceExisting=False)
        except FileExistsError:
            confirm = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Classroom id already exists. Replace it?",
            )
            resp = confirm.run()
            confirm.destroy()
            if resp != Gtk.ResponseType.YES:
                return
            archive.importClassroom(path, CLASSROOMS_FILE, replaceExisting=True)
            replace = True
        except Exception as e:
            self._error(str(e))
            return
        self.data = load_classrooms()
        self._refresh_cls_list()
        try:
            manifest = archive.findClassroomJson(path)
            if manifest:
                with open(manifest) as f:
                    payload = json.load(f)
                cid = (payload.get("classroom") or payload).get("id")
                if cid:
                    cache = os.path.join("/shared/classroom-work", cid)
                    if os.path.isdir(cache):
                        for sid in os.listdir(cache):
                            delivery.queueWorkRestore(cid, sid)
        except Exception:
            pass
        self._error("Import complete." if replace else "Import complete.")

    def _on_export(self, _btn, cls_id):
        dialog = Gtk.FileChooserDialog(
            title="Export classroom (choose parent folder)",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            "Export", Gtk.ResponseType.OK,
        )
        if dialog.run() != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        parent = dialog.get_filename()
        dialog.destroy()
        try:
            out = archive.exportClassroom(cls_id, parent, CLASSROOMS_FILE)
            self._error(f"Exported to:\n{out}")
        except Exception as e:
            self._error(str(e))

    def _on_collect(self, _btn, cls_id):
        delivery.requestCollect(cls_id)
        self.collect_lbl.set_text(
            "Collect requested. Students will REPORT on their next agent sync."
        )

    def _build_webapps_section(self):
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        frame = Gtk.Frame()
        frame.get_style_context().add_class("inner-list")

        wa_sw = Gtk.ScrolledWindow()
        wa_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        wa_sw.set_size_request(-1, 160)
        frame.add(wa_sw)

        self.webapp_lb = Gtk.ListBox()
        self.webapp_lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for idx, wa in enumerate(self.data.get("web_apps", [])):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(10)

            lbl = Gtk.Label(label=wa["label"])
            lbl.set_halign(Gtk.Align.START)
            box.pack_start(lbl, False, False, 0)

            url_lbl = Gtk.Label(label=wa["url"])
            url_lbl.set_halign(Gtk.Align.START)
            url_lbl.get_style_context().add_class("dim-label")
            url_lbl.set_ellipsize(3)  # Pango.EllipsizeMode.END
            url_lbl.set_max_width_chars(30)
            box.pack_start(url_lbl, False, False, 0)

            row.add(box)
            row.wa_idx = idx
            self.webapp_lb.add(row)
        wa_sw.add(self.webapp_lb)
        v.pack_start(frame, False, False, 0)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add = Gtk.Button(label="+ Add Web App")
        add.connect("clicked", self._on_add_wa)
        btns.pack_start(add, False, False, 0)
        rem = Gtk.Button(label="Remove")
        rem.get_style_context().add_class("destructive-btn")
        rem.connect("clicked", self._on_del_wa)
        btns.pack_start(rem, False, False, 0)
        v.pack_start(btns, False, False, 0)
        return v

    def _on_add_wa(self, _btn):
        dialog = Gtk.Dialog(title="Add Custom Web App", transient_for=self, flags=0)
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK
        )
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(14)
        box.set_margin_end(14)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("e.g. Google Classroom")
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://classroom.google.com")
        box.pack_start(Gtk.Label(label="App name:"), False, False, 0)
        box.pack_start(name_entry, False, False, 0)
        box.pack_start(Gtk.Label(label="URL:"), False, False, 0)
        box.pack_start(url_entry, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        name = name_entry.get_text().strip()
        url = url_entry.get_text().strip()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not name or not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if any(wa["label"] == name for wa in self.data["web_apps"]):
            self._error(f"A web app named '{name}' already exists.")
            return
        self.data["web_apps"].append({"label": name, "url": url})
        self._ensure_save()
        if self.selected_cls_id:
            cls = self._get_cls(self.selected_cls_id)
            if cls:
                self._show_detail(cls)

    def _on_del_wa(self, _btn):
        if getattr(self, "webapp_lb", None) is None:
            return
        sel = self.webapp_lb.get_selected_row()
        if sel is None or not hasattr(sel, "wa_idx"):
            self._error("Select a web app to remove.")
            return
        idx = sel.wa_idx
        if idx < 0 or idx >= len(self.data.get("web_apps", [])):
            return
        wa = self.data["web_apps"][idx]
        label = wa["label"]
        confirm = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove web app '{label}'?",
        )
        resp = confirm.run()
        confirm.destroy()
        if resp != Gtk.ResponseType.YES:
            return
        self.data["web_apps"].pop(idx)
        for cls in self.data.get("classrooms", []):
            cls["enabled_apps"] = [
                a for a in cls.get("enabled_apps", []) if a.get("label") != label
            ]
            _rebuild_enabled_apps(cls, self.data)
        self._ensure_save()
        if self.selected_cls_id:
            cls = self._get_cls(self.selected_cls_id)
            if cls:
                self._show_detail(cls)

    def _build_app_checklist(self, cls):
        """
        Checkbox list combining:
          1. Static apps from available-apps.json
          2. Custom web apps from classrooms.json["web_apps"]
        Toggle = immediate save.
        """
        enabled_labels = {app["label"] for app in cls.get("enabled_apps", [])}

        # Default apps (e.g. Join Classroom) are always on for students; no checkbox
        static_apps = [a for a in load_available_apps() if not a.get("default")]
        web_apps = [_web_app_to_item(wa) for wa in self.data.get("web_apps", [])]
        all_apps = static_apps + web_apps

        frame = Gtk.Frame()
        frame.get_style_context().add_class("inner-list")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        frame.add(vbox)

        if not all_apps:
            vbox.pack_start(
                Gtk.Label(label="No apps defined. Add apps or web apps."),
                False, False, 8,
            )
            return frame

        shown_web_sep = False
        for app in all_apps:
            if app["type"] == "webapp" and not shown_web_sep:
                shown_web_sep = True
                sep_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                sep_box.set_margin_start(10)
                sep_box.set_margin_end(10)
                sep_box.set_margin_top(4)
                sep_box.set_margin_bottom(2)
                sep_lbl = Gtk.Label()
                sep_lbl.set_markup("<small><i>Custom Web Apps</i></small>")
                sep_lbl.set_halign(Gtk.Align.START)
                sep_lbl.get_style_context().add_class("dim-label")
                sep_box.pack_start(sep_lbl, False, False, 0)
                vbox.pack_start(sep_box, False, False, 0)

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_box.set_margin_start(10)
            row_box.set_margin_end(10)
            row_box.set_margin_top(6)
            row_box.set_margin_bottom(6)

            cb = Gtk.CheckButton()
            cb.set_active(app["label"] in enabled_labels)
            self._pending_connects.append((cb, app, cls["id"]))
            row_box.pack_start(cb, False, False, 0)

            desc = Gtk.Label()
            if app["type"] == "webapp":
                url = next(
                    (
                        wa["url"]
                        for wa in self.data.get("web_apps", [])
                        if wa["label"] == app["label"]
                    ),
                    "",
                )
                desc.set_markup(
                    f"<b>{app['label']}</b>  "
                    f"<small>[web]  {url.replace('&', '&amp;')}</small>"
                )
            else:
                detail = app.get("command", app.get("path", ""))
                desc.set_markup(
                    f"<b>{app['label']}</b>  "
                    f"<small>[{app['type']}]  {detail}</small>"
                )
            desc.set_halign(Gtk.Align.START)
            row_box.pack_start(desc, True, True, 0)

            vbox.pack_start(row_box, False, False, 0)

        return frame

    def _on_app_toggle(self, cb, app, cls_id):
        cls = self._get_cls(cls_id)
        if not cls:
            return
        if cb.get_active():
            if not any(a["label"] == app["label"] for a in cls["enabled_apps"]):
                cls["enabled_apps"].append(app)
        else:
            cls["enabled_apps"] = [
                a for a in cls["enabled_apps"] if a["label"] != app["label"]
            ]
        _rebuild_enabled_apps(cls, self.data)
        self._ensure_save()

    def _on_add_student(self, _btn, cls_id):
        dialog = Gtk.Dialog(title="Add Student", transient_for=self, flags=0)
        dialog.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK
        )
        box = dialog.get_content_area()
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g. studentuser")
        box.pack_start(Gtk.Label(label="Student username:"), False, False, 0)
        box.pack_start(entry, False, False, 0)
        dialog.set_default_response(Gtk.ResponseType.OK)
        entry.set_activates_default(True)
        dialog.show_all()
        response = dialog.run()
        username = entry.get_text().strip()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not username:
            return
        # Resolve live classroom after poll may have replaced self.data
        live = self._get_cls(cls_id or self.selected_cls_id)
        if not live:
            return
        if username in live.get("students", []):
            self._error(f"'{username}' is already enrolled.")
            return
        live.setdefault("students", []).append(username)
        self._ensure_save()
        self._show_detail(live)

    def _on_rem_student(self, _btn, cls_id):
        row = self.student_lb.get_selected_row()
        if not row or not hasattr(row, "student_name"):
            return
        live = self._get_cls(cls_id or self.selected_cls_id)
        if not live:
            return
        live["students"] = [s for s in live.get("students", []) if s != row.student_name]
        self._ensure_save()
        self._show_detail(live)

    def _ensure_save(self):
        try:
            save_classrooms(self.data)
        except Exception as e:
            self._error(str(e))

    def _error(self, msg):
        d = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        d.run()
        d.destroy()


def main():
    css = b"""
        window { background-color: #F2EEDE; color: #262626; }
        label { color: #262626; }
        button {
            background-color: #0238c2; color: white;
            padding: 4px 12px; border: none; border-radius: 2px; min-height: 28px;
        }
        button:hover { background-color: #001f6e; }
        .destructive-btn { background-color: #a0161a; }
        .destructive-btn:hover { background-color: #700f12; }
        .inner-list {
            background-color: #ffffff;
            border: 1px solid #cccccc;
            border-radius: 2px;
        }
        .inner-list list, list { background-color: #ffffff; }
        .inner-list row { background-color: #ffffff; }
        row:hover { background-color: #e8eef8; }
        row:selected { background-color: #c8d8f8; }
        row:selected label { color: #000000; }
        .dim-label { color: #888888; font-style: italic; }
        .join-code {
            font-size: 26px;
            font-weight: bold;
            letter-spacing: 4px;
            color: #0238c2;
        }
        .join-timer { font-size: 14px; color: #555555; }
        entry {
            background-color: #ffffff; color: #262626;
            border: 1px solid #aaaaaa; border-radius: 2px; padding: 4px;
        }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    win = ClassroomManager()
    win.realize()
    win.set_opacity(0)
    win.show_all()
    win.detail_page.hide()
    GLib.timeout_add(150, lambda: win.set_opacity(1) or False)
    Gtk.main()


if __name__ == "__main__":
    main()
