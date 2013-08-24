# encoding: utf-8
from .widgets import ToolDialog
from .instrumentstatus import InstrumentStatus
from ..hardware.instruments.pilatus import PilatusStatus, PilatusError, InstrumentError
from gi.repository import Gtk

class PilatusControl(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_PilatusControlWindow'
    def __init__(self, credo, title='Pilatus300k X-ray detector control'):
        ToolDialog.__init__(self, credo, title)
        status = InstrumentStatus(self.credo.get_equipment('pilatus'), ncolumns=6)
        self.get_content_area().pack_start(status, True, True, 0)
        status.add_label('status', 'Status')
        status.add_label('timeleft', 'Time left', '%d sec')
        status.add_label('imagesremaining', 'Images remaining')
        status.add_label('exptime', 'Exposure time', '%g sec')
        status.add_label('expperiod', 'Exposure period', '%g sec')
        status.add_label('nimages', 'Number of images', '%d')

        status.add_label('temperature0', 'Powerboard temp.', '%.1f°C')
        status.add_label('temperature1', 'Baseplate temp.', '%.1f°C')
        status.add_label('temperature2', 'Sensor temp.', '%.1f°C')
        status.add_label('humidity0', 'Powerboard hum.', '%.1f %%')
        status.add_label('humidity1', 'Baseplate hum.', '%.1f %%')
        status.add_label('humidity2', 'Sensor humidity', '%.1f %%')
        
        status.add_label('threshold', 'Threshold', '%d eV')
        status.add_label('gain', 'Gain')
        status.add_label('vcmp', 'Vcmp', '%.2f V')
        status.add_label('tau', 'Tau', lambda x:'%.1f ns' % (x * 1e9))
        status.add_label('cutoff', 'Saturation cut-off', '%d cts')
        
        status.refresh_statuslabels()
        
        buttonbar = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        self.get_content_area().pack_start(buttonbar, False, False, 10)
        self._buttons = {}

        self.show_all()
        
