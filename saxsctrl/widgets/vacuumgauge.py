from .widgets import ToolDialog
from gi.repository import Gtk
from gi.repository import GObject

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class VacuumGauge(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_Widgets_VacuumGauge'
    __gsignals__ = {'destroy':'override'}
    def __init__(self, credo, title='Vacuum status'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        vb = self.get_content_area()
        
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        row = 0
        
        l = Gtk.Label('Refresh interval (sec):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._interval = Gtk.SpinButton(adjustment=Gtk.Adjustment(1.0, 1, 1e6, 1, 10), digits=2)
        tab.attach(self._interval, 1, 2, row, row + 1)
        self._interval.connect('value-changed', lambda sb:self._on_interval_changed())
        
        f = Gtk.Frame(label='Current vacuum:')
        vb.pack_start(f, True, True, 0)
        self._vaclabel = Gtk.Label('N/A')
        f.add(self._vaclabel)
        self._on_interval_changed()
    def _readout(self):
        self._vaclabel.set_label('%.4f mbar' % (self.credo.get_equipment('vacgauge').readout()))
        return True
    def _on_interval_changed(self):
        if hasattr(self, '_timeouthandle') and self._timeouthandle is not None:
            GObject.source_remove(self._timeouthandle)
        self._timeouthandle = GObject.timeout_add(int(self._interval.get_value() * 1000), self._readout)
    def do_destroy(self):
        if hasattr(self, '_timeouthandle') and self._timeouthandle is not None:
            GObject.source_remove(self._timeouthandle)
            self._timeouthandle = None
    def do_response(self, respid):
        self.destroy()
