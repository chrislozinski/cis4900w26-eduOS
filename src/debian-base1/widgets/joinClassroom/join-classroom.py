#!/usr/bin/env python3
"""
Join Classroom
Student-facing app: enter the timed code from the teacher's Classroom Network panel.
"""
import getpass
import os
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

_HERE = os.path.dirname(os.path.abspath(__file__))
for p in (
    "/usr/local/share/cis4900-src/src/debian-base1",
    "/opt/cis4900",
    os.path.dirname(os.path.dirname(_HERE)),
    os.path.dirname(os.path.dirname(os.path.dirname(_HERE))),
):
    if os.path.isdir(os.path.join(p, "network")) and p not in sys.path:
        sys.path.insert(0, p)

from network import agent as agent_mod  # noqa: E402


class JoinClassroom(Gtk.Window):
    def __init__(self):
        super().__init__(title="Join Classroom")
        self.set_default_size(440, 280)
        self.set_wmclass("join_classroom", "JoinClassroom")
        self.connect("destroy", Gtk.main_quit)

        self._username = os.environ.get("USER") or getpass.getuser()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(24)
        box.set_margin_end(24)
        self.add(box)

        title = Gtk.Label()
        title.set_markup("<big><b>Join Classroom</b></big>")
        title.set_halign(Gtk.Align.START)
        box.pack_start(title, False, False, 0)

        note = Gtk.Label(
            label="Enter the code shown on the teacher's Classroom Network panel."
        )
        note.set_halign(Gtk.Align.START)
        note.set_line_wrap(True)
        note.get_style_context().add_class("dim-label")
        box.pack_start(note, False, False, 0)

        user_lbl = Gtk.Label(label="Username")
        user_lbl.set_halign(Gtk.Align.START)
        box.pack_start(user_lbl, False, False, 0)
        # Keep the field visible but locked to the logged-in user
        self.student_entry = Gtk.Entry()
        self.student_entry.set_text(self._username)
        self.student_entry.set_editable(False)
        self.student_entry.set_sensitive(False)
        box.pack_start(self.student_entry, False, False, 0)

        code_lbl = Gtk.Label(label="Join code")
        code_lbl.set_halign(Gtk.Align.START)
        box.pack_start(code_lbl, False, False, 0)
        self.code_entry = Gtk.Entry()
        self.code_entry.set_placeholder_text("6-character code")
        self.code_entry.set_activates_default(True)
        box.pack_start(self.code_entry, False, False, 0)

        self.status = Gtk.Label(label="")
        self.status.set_halign(Gtk.Align.START)
        self.status.set_line_wrap(True)
        box.pack_start(self.status, False, False, 0)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn = Gtk.Button(label="Join")
        btn.set_size_request(100, -1)
        btn.connect("clicked", self._on_join)
        btn_row.pack_start(btn, False, False, 0)
        box.pack_start(btn_row, False, False, 0)
        self.set_default(btn)

    def _on_join(self, _btn):
        student = self._username
        code = self.code_entry.get_text().strip()
        if not code:
            self.status.set_text("Enter the join code.")
            return
        self.status.set_text("Joining…")

        def work():
            try:
                agent_mod.runJoin(student, code)
                # Start background sync right away; the wrapper dedupes itself
                # and survives this window closing (new session).
                try:
                    subprocess.Popen(
                        ["/usr/local/bin/student-agent-session.sh"],
                        start_new_session=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass  # source-tree runs without the wrapper: autostart covers next login
                GLib.idle_add(self._join_ok)
            except SystemExit as e:
                GLib.idle_add(self.status.set_text, str(e))
            except Exception as e:
                GLib.idle_add(self.status.set_text, f"Join failed: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _join_ok(self):
        self.status.set_markup(
            "<b>Joined successfully.</b> Sync continues in the background."
        )
        return False


def main():
    css = b"""
        window { background-color: #F2EEDE; color: #262626; }
        label { color: #262626; }
        button {
            background-color: #0238c2; color: white;
            padding: 6px 16px; border: none; border-radius: 2px; min-height: 28px;
        }
        button:hover { background-color: #001f6e; }
        .dim-label { color: #888888; font-style: italic; }
        entry {
            background-color: #ffffff; color: #262626;
            border: 1px solid #aaaaaa; border-radius: 2px; padding: 6px;
        }
        entry:disabled {
            background-color: #f0ebe0; color: #555555;
        }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    win = JoinClassroom()
    win.realize()
    win.set_opacity(0)
    win.show_all()
    GLib.timeout_add(150, lambda: win.set_opacity(1) or False)
    Gtk.main()


if __name__ == "__main__":
    main()
