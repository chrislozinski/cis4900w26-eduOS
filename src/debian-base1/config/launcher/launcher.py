#!/usr/bin/env python3
"""
Minimal GTK Launcher
Displays clickable icons for apps and folders defined in appbar-config.json
"""
import gi
import grp
import json
import os
import subprocess
import sys
import getpass
from datetime import datetime
from zoneinfo import ZoneInfo

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
from tray_indicators import TRAY_INDICATORS, GLYPH_TRAY_MORE, tray_css, show_flyout

EASTERN = ZoneInfo('America/New_York')

CLASSROOMS_FILE     = '/shared/classrooms.json'
VIEWER_DIR          = os.path.expanduser('~/.cache/launcher_viewers')
AVAILABLE_APPS_FILE = os.path.join(
    os.path.expanduser('~/.config/launcher'), 'available-apps.json')
LOCAL_STUDENT_STATE_FILE = os.path.expanduser('~/.cache/cis4900/student-state.json')

# Role detection & config loading
def get_user_role():
    """Return 'teacher' if the current user is in the teacher group, else 'student'"""
    username = getpass.getuser()
    try:
        if username in grp.getgrnam('teacher').gr_mem:
            return 'teacher'
    except KeyError:
        pass
    return 'student'


def _load_catalog():
    """Return {label: item} from available-apps.json so theres only one file for all apps"""
    try:
        with open(AVAILABLE_APPS_FILE, 'r') as f:
            apps = json.load(f).get('available_apps', [])
        return {app['label']: app for app in apps}
    except Exception:
        return {}


def _resolve_refs(config):
    """
    Expand {"ref": "Label"} shorthand items into their full definitions
    from available-apps.json. Lets role configs stay thin while
    available-apps.json is the single place to update icons/commands/paths
    """
    catalog = _load_catalog()
    resolved = []
    for item in config.get('items', []):
        if 'ref' in item:
            label = item['ref']
            if label in catalog:
                resolved.append(catalog[label])
        else:
            resolved.append(item)
    config['items'] = resolved
    return config


def load_config(config_dir, role):
    """
    Load the role-specific sidebar config
    this falls back to the generic appbar-config.json if no role file exists
    Resolves {"ref": "Label"} items from available-apps.json
    
    For students the sidebar is entirely set by their classroom enabled_apps
    Resolves /home/USER placeholders for the current user
    """
    role_file = os.path.join(config_dir, f'appbar-config-{role}.json')
    fallback  = os.path.join(config_dir, 'appbar-config.json')
    path      = role_file if os.path.exists(role_file) else fallback

    with open(path, 'r') as f:
        config = json.load(f)

    # Expand any ref shorthand before anything else
    config = _resolve_refs(config)

    if role == 'student':
        config = _set_classroom_apps(config)

    # Resolve /home/USER placeholder for this user
    home = os.path.expanduser('~')
    raw  = json.dumps(config).replace('/home/USER', home).replace('~/', home + '/')
    return json.loads(raw)


def _default_apps():
    """Catalog entries marked "default": true. Always on every student sidebar,
    even when unenrolled or the teacher's enabled_apps list is empty."""
    try:
        with open(AVAILABLE_APPS_FILE, 'r') as f:
            catalog = json.load(f).get('available_apps', [])
        return [a for a in catalog if a.get('default')]
    except Exception:
        return []


def _with_default_apps(items):
    labels = {i.get('label') for i in items if isinstance(i, dict)}
    return list(items) + [a for a in _default_apps() if a['label'] not in labels]


def _set_classroom_apps(config):
    """Replace the student item list entirely with classroom enabled_apps
    The teacher fully controls what appears, checking or unchecking add/ removesan app
    Default apps (available-apps.json "default": true) are always appended
    Also records which classroom the app list came from (config['classroom_id']/
    ['classroom_name']) so the sidebar can show the student which class is active."""
    username = getpass.getuser()
    # Prefer local state cache applied by student-state
    try:
        with open(LOCAL_STUDENT_STATE_FILE, 'r') as f:
            state = json.load(f)
        items = state.get('environment', {}).get('enabled_apps', [])
        if isinstance(items, list):
            config['items'] = _with_default_apps(items)
            session = state.get('session', {})
            config['classroom_id'] = session.get('classroom_id')
            config['classroom_name'] = session.get('classroom_name')
            return config
    except Exception:
        pass
    items = []
    try:
        with open(CLASSROOMS_FILE, 'r') as f:
            data = json.load(f)
        for classroom in data.get('classrooms', []):
            if username in classroom.get('students', []):
                items = list(classroom.get('enabled_apps', []))
                config['classroom_id'] = classroom.get('id')
                config['classroom_name'] = classroom.get('name')
                break
    except Exception:
        pass  # no classrooms file or not enrolled; only default apps show
    config['items'] = _with_default_apps(items)
    return config


# Main app window
class LauncherWindow(Gtk.Window):
    def __init__(self, config_path):
        super().__init__(title="Appbar")
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # icon directory
        self.icon_dir = os.path.join(os.path.dirname(config_path), 'icons')
        
        # sidebar dimensions proportional to the screen
        # the original dimensions for my laptop were self.expanded_width = 200 and self.collapsed_width = 58
        screen     = Gdk.Screen.get_default()
        screen_w   = screen.get_width()
        screen_h   = screen.get_height()

        self.expanded_width  = int(screen_w * 0.11)
        #self.collapsed_width = 58
        self.button_height   = int(screen_h * 0.046)
        self.icon_size = int(screen_h * 0.0223)
        self.font_px = self.expanded_width * 0.065

        self.hbox_margin     = max(2, int(self.expanded_width * 0.03))
        self.collapsed_width = 20 + 2 * self.hbox_margin + self.icon_size

        self.is_collapsed = False

        # CSS text sizing: font_px compensates for changing dpi based on the system, so theres dynamic sizing
        _css = Gtk.CssProvider()
        _css.load_from_data(f"""
            #username_label     {{ font-size: {self.font_px}px; font-weight: bold; }}
            #sidebar_item_label {{ font-size: {self.font_px}px; }}
            #icon_fallback      {{ font-size: {self.font_px}px; }}
            #toggle_label       {{ font-size: {self.font_px}px; }}
            #classroom_label    {{ font-size: {self.font_px*0.85}px; color: #cccccc; }}
            #clock_label        {{ font-size: {self.font_px*0.9}px; }}
        """.encode('utf-8'))  # font_px is a float, GTK3 CSS parses as double
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), _css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.set_default_size(self.expanded_width, Gdk.Screen.get_default().get_height())
        self.set_position(Gtk.WindowPosition.NONE)
        self.move(0, 0)
        self.set_decorated(False)  # Remove window decorations

        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        self.add(main_box)
        
        # username and logout
        self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.header_box.set_margin_bottom(15)
        # added 1234
        self.header_box.set_size_request(-1, 40)
        
        # Home icon to the left of username
        home_icon = self.create_icon_widget('stylized/homeSTYL.png', size=self.icon_size)
        home_event = Gtk.EventBox()
        home_event.add(home_icon)
        home_event.set_tooltip_text("Home")
        #home_event.set_margin_start(11)
        home_event.set_margin_start(self.hbox_margin)
        home_event.connect('button-release-event', self.on_home_clicked)
        self.header_box.pack_start(home_event, False, False, 0)
        
        # Username label
        username = getpass.getuser()
        self.username_label = Gtk.Label()
        self.username_label.set_name("username_label")
        self.username_label.set_text(username)
        self.username_label.set_halign(Gtk.Align.START)
        self.username_label.set_ellipsize(Pango.EllipsizeMode.NONE)
        self.header_box.pack_start(self.username_label, True, True, 0)
        
        # Logout button 
        self.logout_button = Gtk.Button()
        self.logout_button.set_size_request(30, 30)
        self.logout_button.set_tooltip_text("Logout")
        logout_icon_path = os.path.join(self.icon_dir, 'stylized/logoutSTYL.png')
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                logout_icon_path, self.icon_size - 4, self.icon_size - 4, True)
            self.logout_button.set_image(Gtk.Image.new_from_pixbuf(pixbuf))
            self.logout_button.set_always_show_image(True)
        except Exception:
            self.logout_button.set_label(">")  # fallback for logout to just an arrow
        self.logout_button.connect('clicked', self.on_logout_clicked)
        self.header_box.pack_end(self.logout_button, False, False, 0)
        
        main_box.pack_start(self.header_box, False, False, 0)
        
        # Scrolled window for launcher items
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        main_box.pack_start(scrolled, True, True, 0)
        
        # Vertical box for launcher items
        self.items_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.items_box.set_hexpand(True)
        scrolled.add(self.items_box)
        
        # Track label widgets so we can show/hide them on toggle
        self.item_labels = []
        
        # Create buttons from config
        items = self.config.get('items', [])
        
        for item in items:
            button = self.create_launcher_button(item)
            self.items_box.pack_start(button, False, False, 0)
        
        # Open viewers section, sits below last item inside the scroll area
        self.viewer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.viewer_box.set_margin_top(6)
        self._viewer_widgets = {}  # pid to (button, filename_label)
        self.items_box.pack_start(self.viewer_box, False, False, 0)
        GLib.timeout_add(1500, self.refresh_viewer_widgets)

        # Minimize or expand toggle button at the bottom of bar
        self.toggle_button = Gtk.Button()
        self.toggle_button.set_relief(Gtk.ReliefStyle.NONE)
        # added 1234
        #self.toggle_button.set_size_request(-1, 50)
        self.toggle_button.set_size_request(-1, self.button_height)

        self.toggle_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.toggle_hbox.set_margin_start(5)
        self.toggle_arrow = Gtk.Label(label="<")
        self.toggle_arrow.set_name("toggle_label") 
        self.toggle_label = Gtk.Label(label="Minimize")
        self.toggle_label.set_name("toggle_label")

        self.toggle_hbox.pack_start(self.toggle_arrow, False, False, 0)
        self.toggle_hbox.pack_start(self.toggle_label, False, False, 0)
        self.toggle_button.add(self.toggle_hbox)
        self.toggle_button.connect('clicked', self.on_toggle_sidebar)
        main_box.pack_end(self.toggle_button, False, False, 0)

        # Status row: network, volume, and battery icons, plus the clock
        # Added after toggle_button so it renders above "Minimize"
        # TRAY_INDICATORS in tray_indicators.py decides what shows up here
        self.indicators = [cls() for cls in TRAY_INDICATORS]

        status_section = self._build_status_section()
        main_box.pack_end(status_section, False, False, 0)

        GLib.timeout_add(1000, self._update_clock)
        GLib.timeout_add(5000, self._refresh_indicators)

        # Connect window close event
        self.connect('delete-event', self.on_delete_event)
        self.connect('destroy', Gtk.main_quit)

    def _build_status_section(self):
        """Horizontal row of indicator icons, wifi vol battery, then from top to bottom, classroom id, time, date
        Collapsing hides everything here except the "..."."""
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=self.hbox_margin)
        status_row.set_margin_start(self.hbox_margin)
        status_row.set_margin_end(self.hbox_margin)
        size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        # Tracked separately so on_toggle_sidebar can hide these when the sidebar collapses to icon-only
        # (but not "..." below)
        self.indicator_widgets = []
        for indicator in self.indicators:
            widget = indicator.create_icon_widget()
            size_group.add_widget(widget)
            widget.set_halign(Gtk.Align.CENTER)
            self.indicator_widgets.append(widget)
            status_row.pack_start(widget, True, False, 0)

        more_label = Gtk.Label(label=GLYPH_TRAY_MORE)
        more_label.set_name('tray_icon_label')
        more_event = Gtk.EventBox()
        more_event.add(more_label)
        more_event.set_tooltip_text('Status Menu')
        more_event.set_halign(Gtk.Align.CENTER)
        size_group.add_widget(more_event)
        more_event.connect('button-release-event', self.on_status_row_clicked)
        status_row.pack_start(more_event, True, False, 0)

        section.pack_start(status_row, False, False, 0)

        # Only set for students with a classroom, see _set_classroom_apps
        # max_width_chars(1) plus ellipsize keeps this from widening the sidebar
        self.classroom_label = None
        classroom_id = self.config.get('classroom_id')
        if classroom_id:
            self.classroom_label = Gtk.Label(label=f'Classroom: {classroom_id}')
            self.classroom_label.set_name('classroom_label')
            self.classroom_label.set_halign(Gtk.Align.START)
            self.classroom_label.set_margin_start(self.hbox_margin * 6)
            self.classroom_label.set_margin_end(self.hbox_margin * 6)
            self.classroom_label.set_ellipsize(Pango.EllipsizeMode.END)
            self.classroom_label.set_max_width_chars(1)
            self.classroom_label.set_tooltip_text(self.config.get('classroom_name') or classroom_id)
            section.pack_start(self.classroom_label, True, True, 0)

        # for time and date i have a homogeneous 2-cell row with the same margins / mechanism as status_row above
        # this ensures that the edges are pinned to the same x-positions as the icon row's
        #time_date_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=self.hbox_margin)
        time_date_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=max(1, self.hbox_margin * 6))
        time_date_row.set_margin_start(self.hbox_margin)
        time_date_row.set_margin_end(self.hbox_margin)

        #time_date_row.set_homogeneous(True)
        time_date_row.set_halign(Gtk.Align.CENTER)
        # No max_width_chars, diff than classroom_label
        # cap the layout width down to basically nothing
        self.time_label = Gtk.Label()
        self.time_label.set_name('clock_label')
        self.time_label.set_halign(Gtk.Align.START)
        self.time_label.set_ellipsize(Pango.EllipsizeMode.END)
        time_date_row.pack_start(self.time_label, True, True, 0)

        self.date_label = Gtk.Label()
        self.date_label.set_name('clock_label')
        self.date_label.set_halign(Gtk.Align.END)
        self.date_label.set_ellipsize(Pango.EllipsizeMode.END)
        time_date_row.pack_start(self.date_label, True, True, 0)

        section.pack_start(time_date_row, False, False, 0)

        self._update_clock()
        return section

    def on_status_row_clicked(self, widget, event):
        """Combined 'Windows Quick Settings'-style flyout: all 3 tiles at once."""
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for i, indicator in enumerate(self.indicators):
            if i > 0:
                content.pack_start(Gtk.Separator(), False, False, 4)
            indicator.build_tile(content)
        show_flyout(widget, content)

    def _refresh_indicators(self):
        for indicator in self.indicators:
            indicator.refresh()
        return True  # keep polling, matches refresh_viewer_widgets' convention

    def _update_clock(self):
        now = datetime.now(EASTERN)
        self.time_label.set_text(now.strftime('%-I:%M%p').lower())   # e.g. "2:55pm"
        self.date_label.set_text(now.strftime('%d/%m/%Y'))            # e.g. "03/08/2026"
        return True

    # i3 tab checker helper functions
    def get_open_tabs(self):
        """Return {window_title: con_id} for every leaf inside viewer_tabs."""
        try:
            raw  = subprocess.check_output(
                ['i3-msg', '-t', 'get_tree'], stderr=subprocess.DEVNULL)
            tree = json.loads(raw.decode())
        except Exception:
            return {}
        result = {}
        self._find_marked(tree, 'viewer_tabs', result)
        return result

    def _find_marked(self, node, mark, result):
        if mark in node.get('marks', []):
            self._collect_leaves(node, result)
            return True
        for child in node.get('nodes', []) + node.get('floating_nodes', []):
            if self._find_marked(child, mark, result):
                return True
        return False

    def _collect_leaves(self, node, result):
        children = node.get('nodes', [])
        if not children:
            name = node.get('name', '')
            cid  = node.get('id')
            if name and cid:
                result[name] = cid
        else:
            for child in children:
                self._collect_leaves(child, result)

    # functions for the buttons in the sidebar
    def create_launcher_button(self, item):
        """create button for sidebar option"""
        button = Gtk.Button()
        button.set_size_request(-1, self.button_height)
        button.set_hexpand(True)
        button.set_relief(Gtk.ReliefStyle.NONE)
        
        # container for button, proportional to sidebar width
        #hbox_margin  = max(2, int(self.expanded_width * 0.03))
        hbox_margin = self.hbox_margin
        hbox_spacing = max(4, int(self.expanded_width * 0.04))
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=hbox_spacing)
        hbox.set_margin_start(hbox_margin)
        hbox.set_margin_end(hbox_margin)

        icon_name = item.get('icon', '')
        icon_widget = self.create_icon_widget(icon_name)
        hbox.pack_start(icon_widget, False, False, 0)
        
        # Label
        label = Gtk.Label(label=item.get('label', 'Unknown'))
        label.set_name("sidebar_item_label")
        label.set_halign(Gtk.Align.START)
        hbox.pack_start(label, True, True, 0)
        
        # Track this label for collapse/expand toggling
        self.item_labels.append(label)
        
        button.add(hbox)
        
        # Connect click handler
        item_type = item.get('type')
        if item_type in ('app', 'webapp'):
            # Pass full item dict so on_app_click can read window_title if set
            button.connect('clicked', self.on_app_click, item)
        elif item_type == 'folder':
            button.connect('clicked', self.on_folder_click, item.get('label'))
        
        return button
    
    def create_icon_widget(self, icon_name, size=None):
        """Create program widget icon that supports .svg and .png"""
        size = size if size is not None else self.icon_size
        if icon_name.endswith('.svg') or icon_name.endswith('.png'):
            icon_path = os.path.join(self.icon_dir, icon_name)
            if os.path.exists(icon_path):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        icon_path, size, size, True
                    )
                    image = Gtk.Image.new_from_pixbuf(pixbuf)
                    return image
                except Exception as e:
                    print(f"Error loading icon {icon_path}: {e}")
        
        label = Gtk.Label()
        label.set_name("icon_fallback")
        label.set_text(icon_name)
        return label
    
    def on_home_clicked(self, widget, event):
        """Focus the AppWindow tab inside viewer_tabs."""
        open_tabs = self.get_open_tabs()
        if 'AppWindow' in open_tabs:
            subprocess.Popen(['i3-msg', f'[con_id="{open_tabs["AppWindow"]}"] focus'])

    def on_logout_clicked(self, button):
        """Handle logout"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Logout?"
        )
        dialog.format_secondary_text("Are you sure you want to logout?")
        
        # Style the dialog
        self.style_dialog(dialog)

        # Position before show_all to avoid flash
        screen = Gdk.Screen.get_default()
        try:
            screen_w = screen.get_width()
            screen_h = screen.get_height()
        except Exception:
            screen_w = 800
            screen_h = 600

        dialog.resize(360, 160)
        dialog.move((screen_w - 360) // 2, (screen_h - 160) // 2)

        dialog.show_all()
        
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.YES:
            # Kill i3 session to logout
            subprocess.Popen(['i3-msg', 'exit'])
    
    def on_app_click(self, button, item):
        """Launch an application, or focus its existing tab if app open

        Config items may carry an optional 'window_title' field whose value
        must match the actual title the launched process sets on its window
        If this is omitted the item's 'label' is used as the expected title instead
        """
        command = item.get('command')
        if not command:
            return

        # determine which title to look for in the open tabs
        expected_title = item.get('window_title', item.get('label', ''))

        try:
            open_tabs = self.get_open_tabs()
            if expected_title in open_tabs:
                # already open then focus that tab
                subprocess.Popen(['i3-msg', f'[con_id="{open_tabs[expected_title]}"] focus'])
            else:
                # not open yet? then launch it into viewer_tabs like usual
                subprocess.Popen(['i3-msg', '[con_mark="viewer_tabs"] focus; focus child; exec ' + command])
        except Exception as e:
            print(f"Error launching app: {e}")
     
    def on_folder_click(self, button, folder_label):
        """Open folder viewer, or focus its existing tab if already open.

        folder_viewer.py sets its window title to folder_label, so that is
        the exact string we look for in the open tabs.
        """
        try:
            script_dir    = os.path.dirname(os.path.abspath(__file__))
            folder_viewer = os.path.join(script_dir, 'folder_viewer.py')

            open_tabs = self.get_open_tabs()
            if folder_label in open_tabs:
                # Already open — focus that tab
                subprocess.Popen(['i3-msg', f'[con_id="{open_tabs[folder_label]}"] focus'])
            else:
                # Not open yet — launch as before
                subprocess.Popen(['i3-msg', f'[con_mark="viewer_tabs"] focus; focus child; exec python3 {folder_viewer} {folder_label}'])

        except Exception as e:
            print(f"Error opening folder: {e}")
        
        
    def show_error(self, message):
        """Show error dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        
        # Style dialog
        self.style_dialog(dialog)
        
        dialog.run()
        dialog.destroy()
    
    def style_dialog(self, dialog):
        """Apply consistent styling to dialogs"""
        content = dialog.get_content_area()
        action = dialog.get_action_area()
        
        dialog_css = Gtk.CssProvider()
        dialog_css.load_from_data(b"""
            messagedialog {
                background-color: #3c3c3c;
                border: 2px solid #ffffff;
            }
            messagedialog label {
                color: #ffffff;
            }
            messagedialog button {
                background-color: #505050;
                color: #ffffff;
                border: 1px solid #ffffff;
                padding: 8px 16px;
                margin: 4px;
            }
            messagedialog button:hover {
                background-color: #606060;
            }
        """)
        
        # Apply to dialog and its children
        dialog_context = dialog.get_style_context()
        dialog_context.add_provider(dialog_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        # Recursively apply to all children
        def apply_to_children(widget):
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    child_context = child.get_style_context()
                    child_context.add_provider(dialog_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                    apply_to_children(child)
        
        apply_to_children(dialog)
    
    def refresh_viewer_widgets(self):
        """Poll VIEWER_DIR and sync sidebar buttons with currently open viewers."""
        try:
            os.makedirs(VIEWER_DIR, exist_ok=True)
            entries = {f for f in os.listdir(VIEWER_DIR) if f.endswith('.json')}
            current_pids = {int(f[:-5]) for f in entries}
        except Exception:
            return True

        existing_pids = set(self._viewer_widgets.keys())

        for pid in existing_pids - current_pids:
            btn, lbl = self._viewer_widgets.pop(pid)
            if lbl in self.item_labels:
                self.item_labels.remove(lbl)
            self.viewer_box.remove(btn)

        for pid in current_pids - existing_pids:
            try:
                with open(os.path.join(VIEWER_DIR, f'{pid}.json')) as f:
                    info = json.load(f)
                name = info.get('name', '?')
            except Exception:
                continue

            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_size_request(-1, self.button_height)
            btn.set_hexpand(True)

            #hbox_margin  = max(2, int(self.expanded_width * 0.03))
            hbox_margin = self.hbox_margin

            hbox_spacing = max(4, int(self.expanded_width * 0.04))
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=hbox_spacing)
            hbox.set_margin_start(hbox_margin)
            hbox.set_margin_end(hbox_margin)
            icon_widget = self.create_icon_widget('stylized/htmlWebFileSTYL.png')
            hbox.pack_start(icon_widget, False, False, 0)
            lbl = Gtk.Label(label=name)
            lbl.set_name("sidebar_item_label")
            lbl.set_halign(Gtk.Align.START)
            hbox.pack_start(lbl, True, True, 0)
            btn.add(hbox)
            btn.connect('clicked', self._on_viewer_click, pid)

            self.viewer_box.pack_start(btn, False, False, 0)
            self.viewer_box.show_all()
            self.item_labels.append(lbl)
            if self.is_collapsed:
                lbl.hide()

            self._viewer_widgets[pid] = (btn, lbl)
            # cleanup when the viewer process exits to avoid poll delay
            GLib.child_watch_add(pid, lambda *_: self.refresh_viewer_widgets())

        return True  # keep polling

    def _on_viewer_click(self, button, pid):
        """Focus the viewer tab
            Uses same lookup pattern as on_app_click
        """
        try:
            with open(os.path.join(VIEWER_DIR, f'{pid}.json')) as f:
                title = json.load(f).get('name', '')
            open_tabs = self.get_open_tabs()
            if title in open_tabs:
                subprocess.Popen(['i3-msg', f'[con_id="{open_tabs[title]}"] focus'])
                return
        except Exception:
            pass
        subprocess.Popen(['i3-msg', f'[pid={pid}] focus'])

    def on_delete_event(self, widget, event):
        """Prevent Sidebar from being closed"""
        return True  # Returning True prevents the window from closing

    def on_toggle_sidebar(self, button):
        """Collapse sidebar to icon-only or expand back to full width."""
        self.is_collapsed = not self.is_collapsed
        diff = self.expanded_width - self.collapsed_width

        if self.is_collapsed:
            self.username_label.hide()
            self.logout_button.hide()
            self.toggle_label.hide()
            self.toggle_arrow.set_text(">")
            
            for lbl in self.item_labels:
                lbl.hide()
            for w in self.indicator_widgets:
                w.hide()
            if self.classroom_label:
                self.classroom_label.hide()
            self.date_label.hide()
            target = self.collapsed_width
            
            self.set_size_request(target, -1)
            self.resize(target, self.get_size()[1])
            GLib.idle_add(lambda: subprocess.Popen(['i3-msg', f'[title="Appbar"] resize shrink width {diff} px']) and False)
            
            #subprocess.Popen(['i3-msg', f'[title="Appbar"] resize shrink width {diff} px'])
            #GLib.timeout_add(50, lambda: (self.set_size_request(target, -1),self.resize(target, self.get_size()[1]),False)[-1])
        else:
            self.username_label.show()
            self.logout_button.show()
            self.toggle_label.show()
            self.toggle_arrow.set_text("<")
            for lbl in self.item_labels:
                lbl.show()
            for w in self.indicator_widgets:
                w.show()
            if self.classroom_label:
                self.classroom_label.show()
            self.date_label.show()
            target = self.expanded_width
            self.set_size_request(target, -1)
            self.resize(target, self.get_size()[1])
            GLib.idle_add(lambda: subprocess.Popen(['i3-msg', f'[title="Appbar"] resize grow width {diff} px']) and False)

def main():
    role       = get_user_role()
    config_dir = os.path.expanduser('~/.config/launcher')

    if len(sys.argv) > 1:
        # Explicit config path passed 
        config_path = sys.argv[1]
    else:
        # Resolve the role specific config, write it to a temp file so LauncherWindow receives a plain file path 
        resolved    = load_config(config_dir, role)
        config_path = os.path.join(config_dir, f'appbar-config-{role}-resolved.json')
        with open(config_path, 'w') as f:
            json.dump(resolved, f)
    
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        sys.exit(1)
    
    #  CSS 
    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(b"""
        window {
            background-color: #262626;
        }
        button {
            background: transparent;
            color: #ffffff;
            border: none;
            border-radius: 4px;
            padding: 0;                   
        }
        button:hover {
            background-color: rgba(255, 255, 255, 0.1);
        }
        label {
            color: #ffffff;
        }
    """)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    # Call the css for the tile widgets like wifi etc
    tray_css()

    win = LauncherWindow(config_path)
    win.show_all()
    Gtk.main()

if __name__ == '__main__':
    main()