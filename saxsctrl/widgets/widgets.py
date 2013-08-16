from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk
import sasgui
import warnings
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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

class ToolDialog(Gtk.Dialog):
    def __init__(self, credo, title, parent=None, flags=0, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.credo = credo
        # self.set_resizable(False)

class ToolDialog(Gtk.Window):
    __gsignals__ = {'response':(GObject.SignalFlags.RUN_FIRST, None, (int,))}
    def __init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Window.__init__(self)
        self.set_title(title)
        self.credo = credo
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vb)
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vb.pack_start(self._content, True, True, 0)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(sep, False, True, 0)
        self._action = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        self._action.set_layout(Gtk.ButtonBoxStyle.END)
        vb.pack_start(self._action, False, True, 0)
        self._responsewidgets = {}
        for i in range(len(buttons) / 2):
            respid = buttons[i * 2 + 1]
            self._responsewidgets[respid] = Gtk.Button(stock=buttons[i * 2])
            self._action.add(self._responsewidgets[respid])
            self._responsewidgets[respid].connect('clicked', lambda b, respid:self.emit('response', respid), buttons[i * 2 + 1])
    def get_content_area(self):
        return self._content
    def get_action_area(self):
        return self._action
    def set_response_sensitive(self, respid, sensitive):
        self._responsewidgets[respid].set_sensitive(sensitive)
    def get_widget_for_response(self, respid):
        return self._responsewidgets[respid]
    def set_default_response(self, respid):
        warnings.warn('set_default_response() of ToolDialog is not supported', DeprecationWarning)
    def do_response(self, respid):
        logger.debug('Destroying a ToolDialog.')
        self.destroy()
        logger.debug('End of destroying a ToolDialog.')
     

