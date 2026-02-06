#!/usr/bin/env python3 

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk  

win = Gtk.Window(title="AppWindow")
win.set_type_hint(Gdk.WindowTypeHint.NORMAL)
win.set_default_size(880, 1080)

win.connect('delete-event', lambda w, e: True) 
win.connect("destroy", Gtk.main_quit)

label = Gtk.Label(label="Viewer Area - Apps will tab here")
win.add(label)

win.show_all()
Gtk.main()