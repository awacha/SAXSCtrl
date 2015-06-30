# encoding: utf-8
from .widgets import ToolDialog
from gi.repository import Gtk, GLib
from .instrumentstatus import InstrumentStatus
from ..hardware.instruments.instrument import InstrumentPropertyUnknown
import logging
logger = logging.getLogger(__name__)


class HaakePhoenix(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_HaakePhoenixWindow'
    __gsignals__ = {'destroy': 'override'}

    def __init__(self, credo, title='Haake Phoenix Circulator'):
        ToolDialog.__init__(self, credo, title, buttons=('Close', Gtk.ResponseType.CLOSE,
                                                         'Apply set-point', Gtk.ResponseType.APPLY))
        vb = self.get_content_area()
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)

        status = InstrumentStatus(
            self.credo.get_equipment('haakephoenix'), ncolumns=5)
        status.add_label('setpoint', 'Set temperature', '%.02f°C')
        status.add_label('temperature', 'Current temperature', '%.02f°C')
        status.add_label('difftemp', 'Temperature difference', '%.02f°C')
        status.add_label('pumppower', 'Pump running at', '%d %%')
        status.add_label(
            'temperaturecontrol', 'Temperature control', lambda x: ['NO', 'YES'][int(x) % 2])
        status.add_label(
            'iscooling', 'Cooling', lambda x: ['OFF', 'ON'][int(x) % 2])
        status.add_label('externalcontrol', 'Temperature sensor', lambda x: [
                         'Internal', 'External'][int(x) % 2])
        status.add_label(
            'mainrelay_fault', 'Main relay', lambda x: ['OK', 'ERROR'][int(x) % 2])
        status.add_label('overtemperature_fault', 'Overtemperature', lambda x: [
                         'NO', 'ERROR'][int(x) % 2])
        status.add_label(
            'liquidlevel_fault', 'Liquid level', lambda x: ['OK', 'ERROR'][int(x) % 2])
        status.add_label('motor_overload_fault', 'Motor or pump overload', lambda x: [
                         'NO', 'ERROR'][int(x) % 2])
        status.add_label('external_connection_fault', 'External connection', lambda x: [
                         'OK', 'ERROR'][int(x) % 2])
        status.add_label(
            'cooling_fault', 'Cooling system', lambda x: ['OK', 'ERROR'][int(x) % 2])
        status.add_label('internal_pt100_fault', 'Internal Pt100 sensor', lambda x: [
                         'OK', 'ERROR'][int(x) % 2])
        status.add_label('external_pt100_fault', 'External Pt100 sensor', lambda x: [
                         'OK', 'ERROR'][int(x) % 2])
        vb.pack_start(status, True, True, 0)

        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, False, False, 0)

        l = Gtk.Label(label='Setpoint (C):')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        hb.pack_start(l, False, True, 0)
        self._setpoint_sb = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=25, lower=-50, upper=200, step_increment=1, page_increment=10), digits=2)
        hb.pack_start(self._setpoint_sb, True, True, 0)
        self._setpoint_sb.connect(
            'changed', lambda sb: self.set_response_sensitive(Gtk.ResponseType.APPLY, True))
        self._setpoint_sb.set_value(
            self.credo.get_equipment('haakephoenix').setpoint)

        l = Gtk.Label('Circulator pump:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        hb.pack_start(l, False, True, 0)
        self._circulatorpump_switch = Gtk.Switch()
        hb.pack_start(self._circulatorpump_switch, False, True, 0)
        self._circulatorpump_switch.connect(
            'state-set', self._on_circulatorpump_switch)

        if logger.level == logging.DEBUG:
            f = Gtk.Frame(label='Manual programming:')
            vb.pack_start(f, False, False, 0)
            tab = Gtk.Table()
            f.add(tab)
            row = 0
            l = Gtk.Label(label='Command:')
            l.set_halign(Gtk.Align.START)
            l.set_valign(Gtk.Align.CENTER)
            tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
            self._command_entry = Gtk.Entry()
            tab.attach(self._command_entry, 1, 2, row, row + 1, xpadding=3)
            row += 1

            l = Gtk.Label(label='Reply:')
            l.set_halign(Gtk.Align.START)
            l.set_valign(Gtk.Align.CENTER)
            tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
            self._result_label = Gtk.Label(label='')
            self._result_label.set_halign(Gtk.Align.START)
            self._result_label.set_valign(Gtk.Align.CENTER)
            tab.attach(self._result_label, 1, 2, row, row + 1, xpadding=3)
            row += 1
            self._command_entry.connect('activate', lambda entry: self._result_label.set_text(
                self.credo.get_equipment('haakephoenix').execute(entry.get_text())))
        status.refresh_statuslabels()

        hp = self.credo.get_equipment('haakephoenix')
        self._circulatorpump_switch.set_state(hp.pumppower > 0)
        self._connection = hp.connect(
            'instrumentproperty-notify', self._on_instrumentproperty_notify)
        self.show_all()

    def do_destroy(self):
        try:
            self.credo.get_equipment(
                'haakephoenix').disconnect(self._connection)
            del self._connection
        except AttributeError:
            pass

    def _on_circulatorpump_switch(self, switch, state):
        hp = self.credo.get_equipment('haakephoenix')
        if state:
            hp.start_circulation()
            if hp.pumppower <= 0:
                self._timeouthandler = GLib.timeout_add(
                    5000, self._cancel_start_circulation)
        else:
            hp.stop_circulation()
        return True

    def _cancel_start_circulation(self):
        self._circulatorpump_switch.set_active(False)
        try:
            del self._timeouthandler
        except AttributeError:
            pass
        return False

    def _on_instrumentproperty_notify(self, instrument, propname):
        if propname == 'pumppower':
            self._circulatorpump_switch.set_state(instrument.pumppower > 0)
            try:
                GLib.source_remove(self._timeouthandler)
                del self._timeouthandler
                logger.debug('Removed cancel shutter timeout.')
            except AttributeError:
                pass
            except InstrumentPropertyUnknown:
                pass
        return False

    def do_response(self, respid):
        if respid == Gtk.ResponseType.APPLY:
            self._setpoint_sb.update()
            self.credo.get_equipment('haakephoenix').set_setpoint(
                self._setpoint_sb.get_value())
            self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        else:
            ToolDialog.do_response(self, respid)
