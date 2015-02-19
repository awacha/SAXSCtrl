# encoding: utf-8
from .widgets import ToolDialog
from gi.repository import Gtk
from .instrumentstatus import InstrumentStatus
from ..hardware.instruments.instrument import InstrumentPropertyUnknown


class HaakePhoenix(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_HaakePhoenixWindow'
    def __init__(self, credo, title='Haake Phoenix Circulator'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_MEDIA_PLAY, Gtk.ResponseType.YES, Gtk.STOCK_MEDIA_STOP, Gtk.ResponseType.NO))
        vb = self.get_content_area()
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        self.set_response_sensitive(Gtk.ResponseType.YES, False)
        self.set_response_sensitive(Gtk.ResponseType.NO, False)
        
        status = InstrumentStatus(self.credo.get_equipment('haakephoenix'), ncolumns=5)
        status.add_label('setpoint', 'Set temperature', '%.02f°C')
        status.add_label('temperature', 'Current temperature', '%.02f°C')
        status.add_label('difftemp', 'Temperature difference', '%.02f°C')
        status.add_label('pumppower', 'Pump running at', '%d %%')
        status.add_label('temperaturecontrol', 'Temperature control', lambda x:['NO', 'YES'][int(x) % 2])
        status.add_label('iscooling', 'Cooling', lambda x:['OFF', 'ON'][int(x) % 2])
        status.add_label('externalcontrol', 'Temperature sensor', lambda x:['Internal', 'External'][int(x) % 2])
        status.add_label('mainrelay_fault', 'Main relay', lambda x:['OK', 'ERROR'][int(x) % 2])
        status.add_label('overtemperature_fault', 'Overtemperature', lambda x:['NO', 'ERROR'][int(x) % 2])
        status.add_label('liquidlevel_fault', 'Liquid level', lambda x:['OK', 'ERROR'][int(x) % 2])
        status.add_label('motor_overload_fault', 'Motor or pump overload', lambda x:['NO', 'ERROR'][int(x) % 2])
        status.add_label('external_connection_fault', 'External connection', lambda x:['OK', 'ERROR'][int(x) % 2])
        status.add_label('cooling_fault', 'Cooling system', lambda x:['OK', 'ERROR'][int(x) % 2])
        status.add_label('internal_pt100_fault', 'Internal Pt100 sensor', lambda x:['OK', 'ERROR'][int(x) % 2])
        status.add_label('external_pt100_fault', 'External Pt100 sensor', lambda x:['OK', 'ERROR'][int(x) % 2])
        vb.pack_start(status, True, True, 0)
        tab = Gtk.Table()
        vb.pack_start(tab, False, False, 0)
        row = 0
        
        
        l = Gtk.Label(label='Setpoint (C):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._setpoint_sb = Gtk.SpinButton(adjustment=Gtk.Adjustment(25, -50, 200, 1, 10), digits=2)
        tab.attach(self._setpoint_sb, 1, 2, row, row + 1)
        self._setpoint_sb.connect('changed', lambda sb:self.set_response_sensitive(Gtk.ResponseType.APPLY, True))
        row += 1
        self._setpoint_sb.set_value(self.credo.get_equipment('haakephoenix').setpoint)
        
        f = Gtk.Frame(label='Manual programming:')
        vb.pack_start(f, False, False, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        l = Gtk.Label(label='Command:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._command_entry = Gtk.Entry();
        tab.attach(self._command_entry, 1, 2, row, row + 1, xpadding=3)
        row += 1

        
        l = Gtk.Label(label='Reply:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._result_label = Gtk.Label(label=''); self._result_label.set_alignment(0, 0.5)
        tab.attach(self._result_label, 1, 2, row, row + 1, xpadding=3)
        row += 1
        self._command_entry.connect('activate', lambda entry: self._result_label.set_text(self.credo.get_equipment('haakephoenix').execute(entry.get_text())))
        status.refresh_statuslabels()
        
        if self.credo.get_equipment('haakephoenix').pumppower > 0:
            self.set_response_sensitive(Gtk.ResponseType.NO, True)
        else:
            self.set_response_sensitive(Gtk.ResponseType.YES, True)
        
        self._connection = self.credo.get_equipment('haakephoenix').connect('instrumentproperty-notify', self._on_instrumentproperty_notify)
        self.show_all()
    def _on_instrumentproperty_notify(self, instrument, propname):
        if propname == 'pumppower':
            try:
                self.set_response_sensitive(Gtk.ResponseType.NO, instrument.pumppower > 0)
                self.set_response_sensitive(Gtk.ResponseType.YES, instrument.pumppower == 0)
            except InstrumentPropertyUnknown:
                pass
        return False
            
    def do_response(self, respid):
        if respid == Gtk.ResponseType.APPLY:
            self._setpoint_sb.update()
            self.credo.get_equipment('haakephoenix').set_setpoint(self._setpoint_sb.get_value())
            self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        elif respid == Gtk.ResponseType.YES:
            self.credo.get_equipment('haakephoenix').start_circulation()
        elif respid == Gtk.ResponseType.NO:
            self.credo.get_equipment('haakephoenix').stop_circulation()
        else:
            ToolDialog.do_response(self, respid)
