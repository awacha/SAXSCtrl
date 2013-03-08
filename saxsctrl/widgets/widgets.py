from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk
import sasgui

class StatusLabel(Gtk.VBox):
    __gsignals__ = {'status-changed':(GObject.SignalFlags.RUN_FIRST, None, (str, str, object)), }
    def __init__(self, name, names={'OK':'OK', 'WARNING':'WARNING', 'ERROR':'ERROR', 'UNKNOWN':'UNKNOWN'},
                 colors={'OK':Gdk.color_parse('green'),
                         'WARNING':Gdk.color_parse('orange'),
                         'ERROR':Gdk.color_parse('red'),
                         'UNKNOWN':Gdk.color_parse('lightgray'), },
                 state='UNKNOWN'):
        Gtk.VBox.__init__(self, homogeneous=True, spacing=2)
        self.namelabel = Gtk.Label(label=name)
        self.pack_start(self.namelabel, True, True, 0)
        self.statuslabel = Gtk.Label()
        self.statusevtbox = Gtk.EventBox()
        self.statusevtbox.add(self.statuslabel)
        self.pack_start(self.statusevtbox, True, True, 0)
        self.statusnames = names
        self.statuscolors = colors
        self.currentstatus = state
        self.labelname = name
    def set_status(self, status, name=None, color=None):
        if name is not None:
            statstr = name
        else:
            statstr = self.statusnames[status]
        self.statuslabel.set_text(statstr)
        if color is None:
            color = self.statuscolors[status]
        self.statusevtbox.modify_bg(Gtk.StateType.NORMAL, color)
        oldstatus = self.currentstatus
        self.currentstatus = status
        if status != oldstatus:
            self.emit('status-changed', status, statstr, color)

