from .widgets import ToolDialog
from gi.repository import Gtk
from gi.repository import GObject

class HaakePhoenix(ToolDialog):
    __gsignals__ = {'destroy':'override'}
    def __init__(self, credo, title='Haake Phoenix Circulator'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_MEDIA_PLAY, Gtk.ResponseType.YES, Gtk.STOCK_MEDIA_STOP, Gtk.ResponseType.NO))
        vb = self.get_content_area()
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        self.set_response_sensitive(Gtk.ResponseType.YES, False)
        self.set_response_sensitive(Gtk.ResponseType.NO, False)
        tab = Gtk.Table()
        vb.pack_start(tab, False, False, 0)
        row = 0
        
        l = Gtk.Label('Refresh interval (sec):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._interval_sb = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 1, 3600, 1, 10), digits=1)
        tab.attach(self._interval_sb, 1, 2, row, row + 1)
        self._interval_sb.connect('value-changed', lambda sb:self._restart_updater())
        row += 1
        
        l = Gtk.Label('Setpoint (C):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._setpoint_sb = Gtk.SpinButton(adjustment=Gtk.Adjustment(25, -50, 200, 1, 10), digits=2)
        tab.attach(self._setpoint_sb, 1, 2, row, row + 1)
        self._setpoint_sb.connect('value-changed', lambda sb:self.set_response_sensitive(Gtk.ResponseType.APPLY, True))
        row += 1

        f = Gtk.Frame(label='Current state:')
        vb.pack_start(f, True, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        l = Gtk.Label('Temperature (C):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._temperature_label = Gtk.Label('N/A'); self._temperature_label.set_alignment(0, 0.5)
        tab.attach(self._temperature_label, 1, 2, row, row + 1, xpadding=3)
        row += 1
        
        l = Gtk.Label('Setpoint (C):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._setpoint_label = Gtk.Label('N/A'); self._setpoint_label.set_alignment(0, 0.5)
        tab.attach(self._setpoint_label, 1, 2, row, row + 1, xpadding=3)
        row += 1
        
        l = Gtk.Label('Pump running at:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._running_label = Gtk.Label('N/A'); self._running_label.set_alignment(0, 0.5)
        tab.attach(self._running_label, 1, 2, row, row + 1, xpadding=3)
        row += 1
        
        f = Gtk.Frame(label='Manual programming:')
        vb.pack_start(f, False, False, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        l = Gtk.Label('Command:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._command_entry = Gtk.Entry();
        tab.attach(self._command_entry, 1, 2, row, row + 1, xpadding=3)
        row += 1

        
        l = Gtk.Label('Reply:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._result_label = Gtk.Label(''); self._setpoint_label.set_alignment(0, 0.5)
        tab.attach(self._result_label, 1, 2, row, row + 1, xpadding=3)
        row += 1
        self._command_entry.connect('activate', lambda entry: self._result_label.set_text(self.credo.get_equipment('haakephoenix').execute(entry.get_text())))
        
        self._restart_updater()
    def _restart_updater(self):
        if hasattr(self, '_timeout_handler'):
            GObject.source_remove(self._timeout_handler)
            del self._timeout_handler
        GObject.timeout_add(1000 * self._interval_sb.get_value(), self._updater)
    def _updater(self):
        self._setpoint_label.set_text(str(self.credo.get_equipment('haakephoenix').get_setpoint()))
        self._temperature_label.set_text(str(self.credo.get_equipment('haakephoenix').get_temperature()))
        pump = self.credo.get_equipment('haakephoenix').get_pumppower()
        if pump > 0:
            self.set_response_sensitive(Gtk.ResponseType.YES, False)
            self.set_response_sensitive(Gtk.ResponseType.NO, True)
            self._running_label.set_text('%.2f %%' % pump)
        else:
            self.set_response_sensitive(Gtk.ResponseType.YES, True)
            self.set_response_sensitive(Gtk.ResponseType.NO, False)
            self._running_label.set_text('%.2f %%' % pump)
        return True
    def do_response(self, respid):
        if respid == Gtk.ResponseType.APPLY:
            self.credo.get_equipment('haakephoenix').set_setpoint(self._setpoint_sb.get_value())
            self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        elif respid == Gtk.ResponseType.YES:
            self.credo.get_equipment('haakephoenix').start_circulation()
        elif respid == Gtk.ResponseType.NO:
            self.credo.get_equipment('haakephoenix').stop_circulation()
        else:
            ToolDialog.do_response(self, respid)
    def do_destroy(self):
        if hasattr(self, '_timeout_handler'):
            GObject.source_remove(self._timeout_handler)
            del self._timeout_handler
            logger.debug('Unregistered timeout handler on destroy.')
