#!/usr/bin/env python3
"""
Simple Folder Viewer 
"""
import gi
import os
import sys
import json
import getpass

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf

# file type handlers that will map extensions to a command template, using {path} as placeholder atm
# basically will be used so that specific apps run different file types
# add those entries here when apps become available.
FILE_HANDLERS = {
    # '.pdf':  'evince {path}',
    # '.txt':  'xterm -e nano {path}',
    # '.png':  'eog {path}',
}

# map extensions to icon filenames under ~/.config/launcher/icons/
# any unlisted extensions just fall back to the default file icon
FILE_TYPE_ICONS = {
    '.png':  'stylized/photoFileSTYL.svg',
    '.jpg':  'stylized/photoFileSTYL.svg',
    '.jpeg': 'stylized/photoFileSTYL.svg',
    '.gif':  'stylized/photoFileSTYL.svg',
    '.bmp':  'stylized/photoFileSTYL.svg',
    '.svg':  'stylized/photoFileSTYL.svg',
    '.webp': 'stylized/photoFileSTYL.svg',
}

# central icon paths relative to ~/.config/launcher/icons/
FOLDER_ICON = 'dark/folder.svg'
DEFAULT_FILE_ICON = 'dark/book.svg'

class FolderViewer(Gtk.Window):
    def __init__(self, folder_label):
        super().__init__(title=folder_label)
        
        self.folder_label = folder_label
        self.set_wmclass("folder_viewer", "FolderViewer")

        # read the config to get the actual path
        config_path = os.path.expanduser('~/.config/launcher/appbar-config.json')
        folder_path = None

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # find folder with this label
            for item in config.get('items', []):
                if item.get('type') == 'folder' and item.get('label').strip() == folder_label.strip():
                    folder_path = item.get('path')
                    folder_path = folder_path.replace('USER', getpass.getuser())
                    break
                    
            if not folder_path:
                raise Exception(f"Folder '{folder_label}' not found in config")
                
        except Exception as e:
            self.show_error(f"Error: {e}")
            sys.exit(1)
        
        self.root_path = os.path.abspath(folder_path)
        self.current_path = self.root_path
        self.history_back = []
        self.history_forward = []
        
        if not os.path.exists(self.root_path):
            self.show_error(f"Folder does not exist: {self.root_path}")
            sys.exit(1)
            
        if not os.path.isdir(self.root_path):
            self.show_error(f"Path is not a directory: {self.root_path}")
            sys.exit(1)
        
        # define absolute icon paths
        self.icon_base = os.path.expanduser("~/.config/launcher/icons/")
        self.folder_icon_path = os.path.join(self.icon_base, FOLDER_ICON)
        self.file_icon_path   = os.path.join(self.icon_base, DEFAULT_FILE_ICON)
        
        # main container
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)
        
        # nav bar
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        nav_box.set_name("nav_bar")
        nav_box.set_margin_top(0)
        nav_box.set_margin_bottom(0)
        nav_box.set_margin_start(0)
        nav_box.set_margin_end(0)
        vbox.pack_start(nav_box, False, False, 0)

        # inner padding box so content has breathing room without cutting the bar short
        inner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        inner_box.set_margin_top(8)
        inner_box.set_margin_bottom(8)
        inner_box.set_margin_start(10)
        inner_box.set_margin_end(10)
        nav_box.pack_start(inner_box, True, True, 0)

        reset_btn = Gtk.Button(label="^")
        reset_btn.set_name("nav_btn")
        reset_btn.set_tooltip_text("Return to root")
        reset_btn.connect('clicked', self.on_reset)
        inner_box.pack_start(reset_btn, False, False, 0)

        self.back_btn = Gtk.Button(label="<")
        self.back_btn.set_name("nav_btn")
        self.back_btn.set_sensitive(False)
        self.back_btn.connect('clicked', self.on_back)
        inner_box.pack_start(self.back_btn, False, False, 0)

        self.forward_btn = Gtk.Button(label=">")
        self.forward_btn.set_name("nav_btn")
        self.forward_btn.set_sensitive(False)
        self.forward_btn.connect('clicked', self.on_forward)
        inner_box.pack_start(self.forward_btn, False, False, 0)

        self.header = Gtk.Label()
        self.header.set_name("nav_title")
        self.header.set_markup(f"<b>{os.path.basename(self.root_path)}</b>")
        self.header.set_halign(Gtk.Align.CENTER)
        self.header.set_valign(Gtk.Align.CENTER)
        inner_box.pack_start(self.header, True, True, 0)

        # scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_margin_top(8)
        scrolled.set_margin_bottom(8)
        scrolled.set_margin_start(8)
        scrolled.set_margin_end(8)
        vbox.pack_start(scrolled, True, True, 0)
        
        # grid for files
        self.grid = Gtk.FlowBox()
        self.grid.set_valign(Gtk.Align.START)
        self.grid.set_max_children_per_line(6)
        self.grid.set_column_spacing(6)
        self.grid.set_row_spacing(6)
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(self.grid)
        
        self.load_files()
    
    def show_error(self, message):
        print(f"ERROR: {message}")
        dialog = Gtk.MessageDialog(
            transient_for=None, flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=message
        )
        dialog.run()
        dialog.destroy()
    
    def navigate_to(self, path):
        """Navigate to a directory, pushing current onto back stack"""
        if not os.path.isdir(path):
            return
        self.history_back.append(self.current_path)
        self.history_forward.clear()
        self.current_path = os.path.abspath(path)
        self.refresh_view()
    
    def on_back(self, button):
        if not self.history_back:
            return
        self.history_forward.append(self.current_path)
        self.current_path = self.history_back.pop()
        self.refresh_view()
    
    def on_forward(self, button):
        if not self.history_forward:
            return
        self.history_back.append(self.current_path)
        self.current_path = self.history_forward.pop()
        self.refresh_view()
    
    def on_reset(self, button):
        """Reset to root folder and clear all history"""
        if self.current_path != self.root_path:
            self.history_back.append(self.current_path)
        self.history_forward.clear()
        self.current_path = self.root_path
        self.refresh_view()
    
    def refresh_view(self):
        """Clear grid and reload files for current_path, update nav state"""
        # Update header
        self.header.set_markup(f"<b>{os.path.basename(self.current_path)}</b>")
        
        # Update button sensitivity
        self.back_btn.set_sensitive(len(self.history_back) > 0)
        self.forward_btn.set_sensitive(len(self.history_forward) > 0)
        
        # Clear grid
        for child in self.grid.get_children():
            self.grid.remove(child)
        
        # Reload
        self.load_files()
        self.grid.show_all()
    
    def load_files(self):
        """Load and display files from folder"""
        try:
            items = os.listdir(self.current_path)
            for item in sorted(items):
                if item.startswith('.'):
                    continue
                item_path = os.path.join(self.current_path, item)
                is_dir    = os.path.isdir(item_path)
                self.grid.add(self.create_file_widget(item, is_dir))
        except Exception as e:
            self.grid.add(Gtk.Label(label=f"Error: {e}"))
    
    def create_file_widget(self, name, is_dir):
        """Each file item: EventBox > Box(icon + label) with a hover/press feedback via CSS names"""
        event_box = Gtk.EventBox()
        event_box.set_name("file_item")
        item_path = os.path.join(self.current_path, name)

        # Hover feedback
        event_box.connect('enter-notify-event',  self._on_item_enter,  event_box)
        event_box.connect('leave-notify-event',  self._on_item_leave,  event_box)
        # Press / release feedback
        event_box.connect('button-press-event',   self._on_item_press,   event_box)
        event_box.connect('button-release-event', self._on_item_release, event_box, item_path, is_dir)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        # slightly smaller tiles to fit one more column
        box.set_size_request(78, 88)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        
        # Pick icon: folder, file-type-specific, or default file
        if is_dir:
            svg_path = self.folder_icon_path
        else:
            ext = os.path.splitext(name)[1].lower()
            type_icon = FILE_TYPE_ICONS.get(ext)
            if type_icon:
                svg_path = os.path.join(self.icon_base, type_icon)
            else:
                svg_path = self.file_icon_path

        if os.path.exists(svg_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(svg_path, 48, 48, True)
                box.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 0)
            except Exception:
                box.pack_start(Gtk.Label(label="!"), False, False, 0)
        else:
            box.pack_start(Gtk.Label(label="[?]"), False, False, 0)
        
        display_name = name if len(name) <= 15 else name[:12] + "..."
        name_label   = Gtk.Label(label=display_name)
        name_label.set_line_wrap(True)
        name_label.set_max_width_chars(15)
        box.pack_start(name_label, False, False, 0)
        
        event_box.add(box)
        return event_box

    # Item hover / press helpers
    def _on_item_enter(self, widget, event, event_box):
        event_box.set_name("file_item_hover")
        return False

    def _on_item_leave(self, widget, event, event_box):
        event_box.set_name("file_item")
        return False

    def _on_item_press(self, widget, event, event_box):
        if event.button == 1:
            event_box.set_name("file_item_active")
        return False

    def _on_item_release(self, widget, event, event_box, item_path, is_dir):
        """Restore hover state and act only on single left-click release."""
        event_box.set_name("file_item_hover")
        if event.button == 1:
            if is_dir:
                self.navigate_to(item_path)
            else:
                self.open_file(item_path)
        return False

    def open_file(self, path):
        ext     = os.path.splitext(path)[1].lower()
        handler = FILE_HANDLERS.get(ext)
        if handler:
            import subprocess
            subprocess.Popen(handler.replace('{path}', path), shell=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: folder_viewer.py <folder_label>")
        sys.exit(1)
    
    folder_label = sys.argv[1]
    
    css = """
        window {
            background-color: #F2EEDE;
        }

        #nav_bar {
            background-color: #E6E1D4;
            padding: 0;
            margin: 0;
        }

        #nav_title {
            color: #262626;
            font-size: 13px;
        }

        button#nav_btn {
            background-image: none;
            background-color: #2C2C2C;
            color: #F2EEDE;
            border: none;
            border-radius: 2px;
            padding: 2px 8px;
            font-size: 13px;
            font-weight: bold;
            min-width: 0;
            box-shadow: none;
            text-shadow: none;
            -gtk-icon-shadow: none;
        }
        button#nav_btn:hover {
            background-image: none;
            background-color: #1A1A1A;
            color: #F2EEDE;
        }
        button#nav_btn:active {
            background-image: none;
            background-color: #0A0A0A;
            color: #F2EEDE;
        }
        button#nav_btn:disabled {
            background-image: none;
            background-color: #C8C4BE;
            color: #AAAAAA;
        }
        button#nav_btn label {
            color: #F2EEDE;
        }
        button#nav_btn:disabled label {
            color: #AAAAAA;
        }

        label {
            color: #262626;
        }

        #file_item {
            background-color: transparent;
            border-radius: 6px;
            padding: 4px;
        }
        #file_item_hover {
            background-color: rgba(0, 0, 0, 0.045);
            border-radius: 6px;
            padding: 4px;
        }
        #file_item_active {
            background-color: rgba(0, 0, 0, 0.09);
            border-radius: 6px;
            padding: 4px;
        }

        image, image * {
            background-color: transparent;
            box-shadow: none;
        }

        scrolledwindow {
            border: none;
        }
    """

    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode('utf-8'))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    
    win = FolderViewer(folder_label)
    win.show_all()
    Gtk.main()

if __name__ == '__main__':
    main()