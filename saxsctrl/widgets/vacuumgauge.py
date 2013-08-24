from .widgets import ToolDialog
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk
from .instrumentstatus import InstrumentStatus
import math

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MIN_PRESSURE = 0.01
def colourintensity(value):
    return 1 - max(min((math.log10(value) - math.log10(MIN_PRESSURE)) / (math.log10(1000.0) - math.log10(MIN_PRESSURE)), 1), 0)

class VacuumGauge(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_Widgets_VacuumGauge'
    def __init__(self, credo, title='Vacuum status'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        vb = self.get_content_area()
        
        self._statusgrid = InstrumentStatus(self.credo.get_equipment('vacgauge'))
        vb.pack_start(self._statusgrid, True, True, 0)
        
        self._statusgrid.add_label('pressure', 'Vacuum pressure', '%.04f mbar', lambda value, category:Gdk.RGBA(1 - colourintensity(value), colourintensity(value), 0, 1))
        # self._statusgrid.add_label('pressure', 'Vacuum pressure', '%.04f mbar', lambda value, category:Gdk.RGBA(1, 0, 0, 1))
        self._statusgrid.refresh_statuslabels()
    def do_destroy(self):
        if hasattr(self, '_connection'):
            self.credo.get_equipment('vacgauge').disconnect(self._connection)
            del self._connection
    def do_response(self, respid):
        self.destroy()
