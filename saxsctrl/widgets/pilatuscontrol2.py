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

        f = Gtk.Frame(label='Threshold trimming')
        self.get_content_area().pack_start(f, False, False, 0)
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        f.add(hb)
        grid = Gtk.Grid()
        hb.pack_start(grid, True, True, 0)
        row = 0
        l = Gtk.Label('Threshold (eV):')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        self._threshold_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(4024, 4000, 18000, 100, 1000), digits=0)
        self._threshold_entry.set_value(self.credo.get_equipment('pilatus').threshold)
        self._threshold_entry.set_hexpand(True)
        grid.attach(self._threshold_entry, 1, row, 1, 1)
        row += 1
        l = Gtk.Label('Gain:')
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        self._gain_combo = Gtk.ComboBoxText()
        self._gain_combo.append_text('default')
        self._gain_combo.append_text('keep current')
        self._gain_combo.append_text('lowG')
        self._gain_combo.append_text('midG')
        self._gain_combo.append_text('highG')
        self._gain_combo.set_active(0)
        self._gain_combo.set_hexpand(True)
        grid.attach(self._gain_combo, 1, row, 1, 1)
        row += 1
        
        b = Gtk.Button(label='Trim\ndetector')
        grid.attach(b, 2, row - 2, 1, 2)
        b.connect('clicked', self._on_trim_clicked)
        
        l = Gtk.Label("""Available threshold settings for Pilatus 300k:
        LOWG     6685  -->  20202  eV
        MIDG     4425  -->  14328  eV
        HIGHG     3814  -->  11614  eV
        """)
        l.set_alignment(0, 0.5)
        hb.pack_start(l, False, False, 0)

        self.show_all()

    def _on_trim_clicked(self, button):
        threshold = self._threshold_entry.get_value()
        gain = self._gain_combo.get_active_text()
        if gain == 'keep current':
            gain = self.credo.get_equipment('pilatus').gain
        elif gain == 'default':
            gain = None
        try:
            self._gain_combo.set_sensitive(False)
            self._threshold_entry.set_sensitive(False)
            button.set_sensitive(False)
            self.credo.get_equipment('pilatus').set_threshold(threshold, gain)
            self._idleconn = self.credo.get_equipment('pilatus').connect('idle', self._on_pilatus_idle, button)
        except InstrumentError as ie:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot set threshold!')
            md.format_secondary_text('Reason: ' + str(ie))
            md.run()
            md.destroy()
            del md
            self._gain_combo.set_sensitive(True)
            self._threshold_entry.set_sensitive(True)
            button.set_sensitive(True)
    def _on_pilatus_idle(self, pilatus, button):
        self._gain_combo.set_sensitive(True)
        self._threshold_entry.set_sensitive(True)
        button.set_sensitive(True)
        md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, 'Threshold successfully set.')
        md.format_secondary_text('New threshold: %.0f eV\nNew gain: %s' % (pilatus.threshold, pilatus.gain))
        md.run()
        md.destroy()
        pilatus.disconnect(self._idleconn)
        del self._idleconn
        del md
        
