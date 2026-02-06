#!/usr/bin/env python3
"""
Minimal GTK Launcher
Displays clickable icons for apps and folders defined in appbar-config.json
"""
import gi
import json
import os
import subprocess
import sys
import getpass

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf

class LauncherWindow(Gtk.Window):
    def __init__(self, config_path):
        super().__init__(title="Appbar")
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # icon directory
        self.icon_dir = os.path.join(os.path.dirname(config_path), 'icons')
        
        # idebar dimensions
        self.set_default_size(200, 1080)
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
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        header_box.set_margin_bottom(15)
        
        # Username label
        username = getpass.getuser()
        username_label = Gtk.Label()
        username_label.set_markup(f"<span size='large' weight='bold'>{username}</span>")
        username_label.set_halign(Gtk.Align.START)
        header_box.pack_start(username_label, True, True, 0)
        
        # Logout button
        logout_button = Gtk.Button(label=">")
        logout_button.set_size_request(30, 30)
        logout_button.set_tooltip_text("Logout")
        logout_button.connect('clicked', self.on_logout_clicked)
        header_box.pack_end(logout_button, False, False, 0)
        
        main_box.pack_start(header_box, False, False, 0)
        
        # Scrolled window for launcher items
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        main_box.pack_start(scrolled, True, True, 0)
        
        # Vertical box for launcher items
        items_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        scrolled.add(items_box)
        
        # Create buttons from config
        items = self.config.get('items', [])
        
        for item in items:
            button = self.create_launcher_button(item)
            items_box.pack_start(button, False, False, 0)
        
        # Connect window close event
        self.connect('delete-event', self.on_delete_event)
        self.connect('destroy', Gtk.main_quit)
    
    def create_launcher_button(self, item):
        """create button for sidebar option"""
        button = Gtk.Button()
        button.set_size_request(180, 50)
        button.set_relief(Gtk.ReliefStyle.NONE)
        
        #  container for button
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_margin_start(5)
        hbox.set_margin_end(5)
        
        icon_name = item.get('icon', '')
        icon_widget = self.create_icon_widget(icon_name)
        hbox.pack_start(icon_widget, False, False, 0)
        
        # Label
        label = Gtk.Label(label=item.get('label', 'Unknown'))
        label.set_halign(Gtk.Align.START)
        hbox.pack_start(label, True, True, 0)
        
        button.add(hbox)
        
        # Connect click handler
        item_type = item.get('type')
        if item_type == 'app':
            button.connect('clicked', self.on_app_click, item.get('command'))
        elif item_type == 'folder':
            button.connect('clicked', self.on_folder_click, item.get('label'))
        
        return button
    
    def create_icon_widget(self, icon_name):
        """Create program widget icon"""
        if icon_name.endswith('.svg'):
            icon_path = os.path.join(self.icon_dir, icon_name)
            if os.path.exists(icon_path):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        icon_path, 24, 24, True
                    )
                    image = Gtk.Image.new_from_pixbuf(pixbuf)
                    return image
                except Exception as e:
                    print(f"Error loading icon {icon_path}: {e}")
        
        label = Gtk.Label()
        label.set_markup(f"<span size='large'>{icon_name}</span>")
        return label
    
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
        
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.YES:
            # Kill i3 session to logout
            subprocess.Popen(['i3-msg', 'exit'])
    
    def on_app_click(self, button, command):
        """Launch an application"""
        if command:
            try:
                subprocess.Popen(['i3-msg', '[con_mark="viewer_tabs"] focus; focus child; exec ' + command])

            except Exception as e:
                print(f"Error launching app: {e}")
     
    def on_folder_click(self, button, folder_label):
        """Open folder viewer """
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            folder_viewer = os.path.join(script_dir, 'folder_viewer.py')
            
            #  open the folder viewer with the label from the config launcher
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
    
    def on_delete_event(self, widget, event):
        """Prevent Sidebar from being closed"""
        return True  # Returning True prevents the window from closing

def main():
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = os.path.expanduser('~/.config/launcher/appbar-config.json')
    
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
    
    win = LauncherWindow(config_path)
    win.show_all()
    Gtk.main()

if __name__ == '__main__':
    main()