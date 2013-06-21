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

class ToolDialog(Gtk.Dialog):
    def __init__(self, credo, title, parent=None, flags=0, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.credo = credo
        # self.set_resizable(False)
    
class ExposureInterface(object):
    def start_exposure(self, exptime, nimages=1, dwelltime=0.003, header_template={}, sensitive=[], insensitive=[]):
        if not hasattr(self, '_exposure_signal_handles'):
            self._exposure_signal_handles = {}
        if self._exposure_signal_handles:
            raise ValueError('Another exposure is running!')
        self._exposure_signal_handles['exposure-done'] = self.credo.connect('exposure-done', self.on_exposure_done)
        self._exposure_signal_handles['exposure-end'] = self.credo.connect('exposure-end', self.on_exposure_end)
        self._exposure_signal_handles['exposure-fail'] = self.credo.connect('exposure-fail', self.on_exposure_fail)
        self._expose_args = (exptime, nimages, dwelltime, header_template)
        self.credo.expose(*self._expose_args)
        for s in sensitive:
            try:
                s.set_sensitive(True)
            except:
                pass
        for s in insensitive:
            try:
                s.set_sensitive(False)
            except:
                pass
        self._exposure_sensitive = sensitive
        self._exposure_insensitive = insensitive
    def on_exposure_end(self, credo, state, restart=None):
        if not state:
            restart = None
        if restart is not None:
            GObject.timeout_add(int(float(restart) * 1000), self.credo.expose, *(self._expose_args))
            return True
        for s in self._exposure_sensitive:
            try:
                s.set_sensitive(False)
            except:
                pass
        for s in self._exposure_insensitive:
            try:
                s.set_sensitive(True)
            except:
                pass
        for k in self._exposure_signal_handles:
            credo.disconnect(self._exposure_signal_handles[k])
        del self._expose_args
        del self._exposure_insensitive
        del self._exposure_sensitive
        del self._exposure_signal_handles
        if not state:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, 'User break!')
            md.run()
            md.destroy()
            del md
        return True
    def on_exposure_fail(self, credo, message):
        md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Failed to load exposure file!')
        md.format_secondary_markup('<b>Error message:</b> ' + message)
        md.run()
        md.destroy()
        del md
    def on_exposure_done(self, credo, exposure):
        pass
    def do_destroy(self):
        if hasattr(self, '_exposure_signal_handles'):
            for c in self._exposure_signal_handles:
                self.credo.disconnect(self._exposure_signal_handles[c])
            del self._exposure_signal_handles
            
