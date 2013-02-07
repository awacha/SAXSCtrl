import gtk
import sasgui

@sasgui.PyGTKCallback.PyGTKCallback
class StatusLabel(gtk.VBox):
    def __init__(self, name, names={'OK':'OK', 'WARNING':'WARNING', 'ERROR':'ERROR', 'UNKNOWN':'UNKNOWN'},
                 colors={'OK':gtk.gdk.color_parse('green'),
                         'WARNING':gtk.gdk.color_parse('orange'),
                         'ERROR':gtk.gdk.color_parse('red'),
                         'UNKNOWN':gtk.gdk.color_parse('lightgray'), },
                 state='UNKNOWN'):
        gtk.VBox.__init__(self, homogeneous=True, spacing=2)
        self.namelabel = gtk.Label(name)
        self.pack_start(self.namelabel)
        self.statuslabel = gtk.Label()
        self.statusevtbox = gtk.EventBox()
        self.statusevtbox.add(self.statuslabel)
        self.pack_start(self.statusevtbox)
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
        self.statusevtbox.modify_bg(gtk.STATE_NORMAL, color)
        oldstatus = self.currentstatus
        self.currentstatus = status
        if status != oldstatus:
            self.emit('status-changed', status, statstr, color)

class LabelWindow(gtk.Window):
    def __init__(self, title):
        gtk.Window.__init__()
        self.frame = gtk.Frame(title)
        self.label = gtk.Label()
        self.label.set_
