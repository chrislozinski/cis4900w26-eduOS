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

class FolderViewer(Gtk.Window):
    def __init__(self, folder_label):
        super().__init__(title=folder_label)
        
        
        self.set_wmclass("folder_viewer", "FolderViewer")

        # Read the config to get the actual path
        config_path = os.path.expanduser('~/.config/launcher/appbar-config.json')
        folder_path = None

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # Find the folder with this label
            # In folder_viewer.py loop:
            for item in config.get('items', []):
                # Use .strip() to ensure no hidden newline/space kills the match
                if item.get('type') == 'folder' and item.get('label').strip() == folder_label.strip():
                    folder_path = item.get('path')
                    folder_path = folder_path.replace('USER', getpass.getuser())
                    break
                    
            if not folder_path:
                raise Exception(f"Folder '{folder_label}' not found in config")
                
        except Exception as e:
            # Show error and exit
            self.show_error(f"Error: {e}")
            sys.exit(1)
        
        self.folder_path = os.path.abspath(folder_path)
        
        if not os.path.exists(self.folder_path):
            self.show_error(f"Folder does not exist: {self.folder_path}")
            sys.exit(1)
            
        if not os.path.isdir(self.folder_path):
            self.show_error(f"Path is not a directory: {self.folder_path}")
            sys.exit(1)
        
        # Define absolute icon paths
        icon_dir = os.path.expanduser("~/.config/launcher/icons/dark/")
        self.folder_icon_path = os.path.join(icon_dir, "folder.svg")
        self.file_icon_path = os.path.join(icon_dir, "book.svg")
        
        # Main container
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        self.add(vbox)
        
        # Folder name header
        header = Gtk.Label()
        header.set_markup(f"<b>{os.path.basename(self.folder_path)}</b>")
        vbox.pack_start(header, False, False, 0)
        
        # Scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        vbox.pack_start(scrolled, True, True, 0)
        
        # Grid for files
        self.grid = Gtk.FlowBox()
        self.grid.set_valign(Gtk.Align.START)
        self.grid.set_max_children_per_line(5)
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.add(self.grid)
        
        # Load files
        self.load_files()
    
    def show_error(self, message):
        """Show error message"""
        print(f"ERROR: {message}")
        dialog = Gtk.MessageDialog(
            transient_for=None,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()
    
    def load_files(self):
        """Load and display files from folder"""
        try:
            items = os.listdir(self.folder_path)
            for item in sorted(items):
                if item.startswith('.'):
                    continue
                    
                item_path = os.path.join(self.folder_path, item)
                is_dir = os.path.isdir(item_path)
                
                # Create file widget
                file_box = self.create_file_widget(item, is_dir)
                self.grid.add(file_box)
                
        except Exception as e:
            error_label = Gtk.Label(label=f"Error: {e}")
            self.grid.add(error_label)
    
    def create_file_widget(self, name, is_dir):
        """Create a widget for one file using specific SVGs"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.set_size_request(100, 100)
        
        # Select the specific SVG path
        svg_path = self.folder_icon_path if is_dir else self.file_icon_path
        
        if os.path.exists(svg_path):
            try:
                # Load the SVG and scale it
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(svg_path, 48, 48, True)
                image = Gtk.Image.new_from_pixbuf(pixbuf)
                box.pack_start(image, False, False, 0)
            except Exception as e:
                # Fallback to a text label only if the SVG file is corrupted
                err_label = Gtk.Label(label="!")
                box.pack_start(err_label, False, False, 0)
        else:
            # Fallback if path is wrong
            missing_label = Gtk.Label(label="[X]")
            box.pack_start(missing_label, False, False, 0)
        
        # Filename
        name_label = Gtk.Label()
        display_name = name if len(name) <= 15 else name[:12] + "..."
        name_label.set_text(display_name)
        name_label.set_line_wrap(True)
        name_label.set_max_width_chars(15)
        box.pack_start(name_label, False, False, 0)
        
        return box

def main():
    if len(sys.argv) < 2:
        print("Usage: folder_viewer.py <folder_label>")
        sys.exit(1)
    
    folder_label = sys.argv[1]
    
    # CSS fix for dark theme
    css = b"""
        * {
            background-color: #F2EEDE;
            color: #262626;
        }
        
        window {
            background-color: #F2EEDE;
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
        }
        
        button:hover {
            background-color: #001f6e;
        }
        
        scrolledwindow {
            border: none;
        }
    """
    
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
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