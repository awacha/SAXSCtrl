from gi.repository import Gtk
from ..hardware.instruments import genix
import itertools
from gi.repository import GObject
from gi.repository import Gdk
import logging
import multiprocessing

from .widgets import StatusLabel, ToolDialog
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)



class GenixStatus(Gtk.Frame):
    def __init__(self):
        Gtk.Frame.__init__(self, label='Status of the X-ray source')
        self.labels = {}
        
        self.labelsdict = [('Status', self.get_genixstatus, None),
                    ('Remote', 'DISTANT_MODE', None, 'YES', 'NO'),
                    ('X-rays', 'XRAY_ON', None, 'ON', 'OFF'),
                    ('Shutter', 'SHUTTER_OPENED', 'SHUTTER_CLOSED', 'OPEN', 'CLOSED'),
                    ('Interlock', 'INTERLOCK_OK', None, 'OK', 'BROKEN'),
                    ('Overridden', None, 'OVERRIDDEN_ON', 'NO', 'YES'),
                    ('Voltage', self.get_genix_HT, None),
                    ('Current', self.get_genix_current, None),
                    ('Power', self.get_genix_power, None),
                    ('Tube life', self.get_genix_tubetime, None),
                    
                    ('Warm-up', None, 'TUBE_WARM_UP_NEEDED_FAULT', 'not needed', 'needed'),
                    ('X-ray lights', None, 'X-RAY_LIGHT_FAULT'),
                    ('Shutter light', None, 'SHUTTER_LIGHT_FAULT'),
                    ('Vacuum', None, 'VACUUM_FAULT'),
                    ('Water flow', None, 'WATERFLOW_FAULT'),
                    ('Tube', None, 'TUBE_POSITION_FAULT'),
                    ('Safety shutter', None, 'SAFETY_SHUTTER_FAULT'),
                    ('Temperature', None, 'TEMPERATURE_FAULT'),
                    ('Relay interlock', None, 'RELAY_INTERLOCK_FAULT'),
                    ('Door sensor', None, 'DOOR_SENSOR_FAULT'),
                    ('Filament', None, 'FILAMENT_FAULT'),
                    ('Sensor 1', None, 'SENSOR1_FAULT'),
                    ('Sensor 2', None, 'SENSOR2_FAULT'),
                    
                    ('Conditions auto OK', 'CONDITIONS_AUTO_OK', None, 'YES', 'NO'), ]
        
        num_cols = 6
        tab = Gtk.Table()
        self.add(tab)
        
        for label, i in zip(self.labelsdict, itertools.count(0)):
            try:
                oklabel = label[3]
            except IndexError:
                oklabel = 'OK'
            try:
                errlabel = label[4]
            except IndexError:
                errlabel = 'ERROR'
            self.labels[label[0]] = StatusLabel(label[0], {'OK':oklabel, 'ERROR':errlabel, 'UNKNOWN':'inconsistent'})
            tab.attach(self.labels[label[0]], i % num_cols, i % num_cols + 1, i / num_cols, i / num_cols + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 2, 3)
            self.labels[label[0]].connect('status-changed', self.on_changed_logger)
    def on_changed_logger(self, statlabel, status, statstr, color):
        if status == 'ERROR' and statlabel.labelname not in ['Shutter', 'Remote', 'X-rays', 'Status', 'Conditions auto OK']:
            logger.error(statlabel.labelname + '; message: ' + statstr)
        else:
            logger.debug('Status changed: ' + statlabel.labelname + ', new status: ' + status + ', message: ' + statstr)
        return False
    def get_genixstatus(self, status, genixconnection):
        st = genixconnection.whichstate(status)
        return st
    def get_genix_HT(self, status, genixconnection):
        try:
            return '%.2f kV' % (genixconnection.get_ht())
        except GenixError:
            return 'ERROR'
    def get_genix_current(self, status, genixconnection):
        try:
            return '%.2f mA' % (genixconnection.get_current())
        except GenixError:
            return 'ERROR'
    def get_genix_power(self, status, genixconnection):
        try:
            return '%.2f W' % (genixconnection.get_current() * genixconnection.get_ht())
        except GeniXError:
            return 'ERROR'
    def get_genix_tubetime(self, status, genixconnection):
        try:
            return '%.2f h' % (genixconnection.get_tube_time())
        except GenixError:
            return 'ERROR'
    def update_status(self, genixconnection):
        if genixconnection is None:
            return
        try:
            status = genixconnection.get_status()
        except GenixError:
            return False
        for label in self.labelsdict:
            if hasattr(label[1], '__call__'):
                msg = label[1](status, genixconnection)
                self.labels[label[0]].set_status('UNKNOWN', msg, Gdk.color_parse('white'))
            elif label[1] is not None and label[2] is None:
                if status[label[1]]:
                    self.labels[label[0]].set_status('OK')
                else:
                    self.labels[label[0]].set_status('ERROR')
            elif label[1] is None and label[2] is not None:
                if status[label[2]]:
                    self.labels[label[0]].set_status('ERROR')
                else:
                    self.labels[label[0]].set_status('OK')
            else:
                if status[label[1]]:
                    self.labels[label[0]].set_status('OK')
                elif status[label[2]]:
                    self.labels[label[0]].set_status('ERROR')
                else:
                    self.labels[label[0]].set_status('UNKNOWN')
            
        return status
                    
class GenixControl(ToolDialog):
    _timeout_handler = None
    _aux_timeout_handler = None
    error_handler = None
    __gsignals__ = {'response':'override'}
    def __init__(self, credo, title='GeniX3D control'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        vbox = self.get_content_area()
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        vbox.pack_start(sw, False, True, 0)
        sw.set_size_request(-1, 50 * 4)
        self.status = GenixStatus()
        sw.add_with_viewport(self.status)
        
        bb = Gtk.HButtonBox()
        vbox.pack_start(bb, False, True, 0)        
        self.xraybutton = Gtk.Button('X-rays ON')
        self.xraybutton.connect('clicked', self.on_xrays)
        bb.add(self.xraybutton)
        
        self.shutterbutton = Gtk.Button('Open shutter')
        self.shutterbutton.connect('clicked', self.on_shutter)
        bb.add(self.shutterbutton)
        
        self.resetbutton = Gtk.Button('Reset failures')
        self.resetbutton.connect('clicked', self.on_reset)
        bb.add(self.resetbutton)
        
        self.warmupbutton = Gtk.Button('Warm up')
        self.warmupbutton.connect('clicked', self.on_warmup)
        bb.add(self.warmupbutton)
        
        self.powerdownbutton = Gtk.Button('Power down')
        self.powerdownbutton.connect('clicked', self.on_powerdown)
        bb.add(self.powerdownbutton)
        
        self.standbybutton = Gtk.Button('Stand by')
        self.standbybutton.connect('clicked', self.on_standby)
        bb.add(self.standbybutton)
        
        self.rampupbutton = Gtk.Button('Ramp up')
        self.rampupbutton.connect('clicked', self.on_rampup)
        bb.add(self.rampupbutton)

        self.status.labels['X-rays'].connect('status-changed', self.on_xrays)
        self.status.labels['Shutter'].connect('status-changed', self.on_shutter)
        self.status.labels['Status'].connect('status-changed', self.on_warmup)
        self.update_status()
        self._timeout_handler = GObject.timeout_add_seconds(1, self.update_status)
    def update_status(self):
        g = self.credo.get_equipment('genix')
        if not g.connected():
            self.hide()
            return False
        self.status.update_status(g)
        status = g.status
        self.shutterbutton.set_sensitive(status != genix.GenixStatus.XRaysOff)
        self.powerdownbutton.set_sensitive(status in (genix.GenixStatus.FullPower, genix.GenixStatus.Standby, genix.GenixStatus.Idle))
        self.xraybutton.set_sensitive(status in (genix.GenixStatus.PowerDown, genix.GenixStatus.Idle, genix.GenixStatus.XRaysOff))
        self.standbybutton.set_sensitive(status in (genix.GenixStatus.FullPower, genix.GenixStatus.PowerDown, genix.GenixStatus.Idle))
        self.rampupbutton.set_sensitive(status in (genix.GenixStatus.Standby, genix.GenixStatus.Idle))
        self.warmupbutton.set_sensitive(status in (genix.GenixStatus.PowerDown, genix.GenixStatus.Idle))
        return True
    def finalize(self, *args, **kwargs):
        if self._timeout_handler is not None:
            GObject.source_remove(self._timeout_handler)
            self._timeout_handler = None
        if self._aux_timeout_handler is not None:
            GObject.source_remove(self._aux_timeout_handler)
            self._aux_timeout_handler = None
            
    def __del__(self):
        self.finalize()
    def on_warmup(self, widget, status=None, statstr=None, color=None):
        if not self.credo.get_equipment('genix').xrays_state():
            return
        try:
            self.credo.get_equipment('genix').do_warmup()
        except GenixError:
            return
        self.update_status()
    def on_powerdown(self, widget):
        if not self.credo.get_equipment('genix').xrays_state():
            return
        try:
            self.credo.get_equipment('genix').do_poweroff()
        except GenixError:
            return
        self.update_status()
    def on_standby(self, widget):
        if not self.credo.get_equipment('genix').xrays_state():
            return
        try:
            self.credo.get_equipment('genix').do_standby()
        except GenixError:
            return
        self.update_status()
    def on_rampup(self, widget):
        if not self.credo.get_equipment('genix').xrays_state():
            return
        try:
            self.credo.get_equipment('genix').do_rampup()
        except GenixError:
            return
        self.update_status()
        
    def on_reset(self, widget):
        try:
            self.credo.get_equipment('genix').reset_faults()
        except GenixError:
            return True
        return True
    
    def on_xrays(self, widget, status=None, statstr=None, color=None):
        if isinstance(widget, Gtk.Button):
            try:
                if self.credo.get_equipment('genix').xrays_state():
                    self.credo.get_equipment('genix').xrays_off()
                else:
                    self.credo.get_equipment('genix').xrays_on()
            except GenixError:
                pass
        else:
            if self.credo.get_equipment('genix').xrays_state():
                self.xraybutton.set_label('X-rays OFF')
            else:
                self.xraybutton.set_label('X-rays ON')
        self.update_status()
    def on_shutter(self, widget, status=None, statstr=None, color=None):
        if isinstance(widget, Gtk.Button):
            try:
                if self.credo.get_equipment('genix').shutter_state():
                    self.credo.get_equipment('genix').shutter_close(wait_for_completion=False)
                else:
                    self.credo.get_equipment('genix').shutter_open(wait_for_completion=False)
            except GenixError:
                pass
        else:
            if self.credo.get_equipment('genix').shutter_state():
                self.shutterbutton.set_label('Close shutter')
            else:
                self.shutterbutton.set_label('Open shutter')
    def do_response(self, respid):
        self.hide()        

