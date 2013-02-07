import gtk
from ..hardware import genix
import itertools
import gobject
import logging


from widgets import StatusLabel
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)



class GenixStatus(gtk.Frame):
    def __init__(self):
        gtk.Frame.__init__(self, 'Status of the X-ray source')
        self.labels = {}
        
        self.labelsdict = [('Status', self.get_genixstatus, None),
                    ('Remote', 'DISTANT_MODE', None, 'YES', 'NO'),
                    ('X-rays', 'XRAY_ON', None, 'ON', 'OFF'),
                    ('Shutter', 'SHUTTER_OPENED', 'SHUTTER_CLOSED', 'OPEN', 'CLOSED'),
                    ('Interlock', 'INTERLOCK_OK', None, 'OK', 'BROKEN'),
                    ('Overridden', None, 'OVERRIDDEN_ON', 'NO', 'YES'),
                    ('Voltage', self.get_genix_HT, None),
                    ('Current', self.get_genix_current, None),
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
                    ('Sensor 2', None, 'SENSOR2_FAULT')]
        
        num_cols = 6
        tab = gtk.Table()
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
            tab.attach(self.labels[label[0]], i % num_cols, i % num_cols + 1, i / num_cols, i / num_cols + 1, gtk.FILL | gtk.EXPAND, gtk.FILL | gtk.EXPAND, 2, 3)
            self.labels[label[0]].connect('status-changed', self.on_changed_logger)
    def on_changed_logger(self, statlabel, status, statstr, color):
        if status == 'ERROR' and statlabel.labelname not in ['Shutter', 'Remote', 'X-rays', 'Status']:
            logger.error(statlabel.labelname + '; message: ' + statstr)
        else:
            logger.info('Status changed: ' + statlabel.labelname + ', new status: ' + status + ', message: ' + statstr)
        return False
    def get_genixstatus(self, status, genixconnection):
        if status['CYCLE_TUBE_WARM_UP_ON']:
            return 'Warm-up'
        elif status['CYCLE_AUTO_ON']:
            return 'Ramping up'
        elif status['CYCLE_RESET_ON']:
            return 'Powering off'
        elif status['STANDBY_ON']:
            return 'Going to standby'
        else:
            return 'Idle'
    def get_genix_HT(self, status, genixconnection):
        try:
            return '%.2f kV' % (genixconnection.get_ht())
        except genix.GenixError:
            return 'ERROR'
    def get_genix_current(self, status, genixconnection):
        try:
            return '%.2f mA' % (genixconnection.get_current())
        except genix.GenixError:
            return 'ERROR'
    def get_genix_tubetime(self, status, genixconnection):
        try:
            return '%.2f h' % (genixconnection.get_tube_time())
        except genix.GenixError:
            return 'ERROR'
    def update_status(self, genixconnection):
        try:
            status = genixconnection.get_status()
        except genix.GenixError:
            return False
        for label in self.labelsdict:
            if hasattr(label[1], '__call__'):
                msg = label[1](status, genixconnection)
                self.labels[label[0]].set_status('UNKNOWN', msg, gtk.gdk.color_parse('white'))
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
        return True
                    
class GenixControl(gtk.Dialog):
    _timeout_handler = None
    _aux_timeout_handler = None
    error_handler = None
    def __init__(self, connection=None, title='GeniX3D control', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=None):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_resizable(False)
        vbox = self.get_content_area()
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
        vbox.pack_start(sw, False)
        sw.set_size_request(-1, 50 * 4)
        self.status = GenixStatus()
        sw.add_with_viewport(self.status)
        
        bb = gtk.HButtonBox()
        vbox.pack_start(bb, False)        
        self.xraybutton = gtk.Button('X-rays ON')
        self.xraybutton.connect('clicked', self.on_xrays)
        bb.add(self.xraybutton)
        
        self.shutterbutton = gtk.Button('Open shutter')
        self.shutterbutton.connect('clicked', self.on_shutter)
        bb.add(self.shutterbutton)
        
        self.resetbutton = gtk.Button('Reset failures')
        self.resetbutton.connect('clicked', self.on_reset)
        bb.add(self.resetbutton)
        
        self.warmupbutton = gtk.Button('Warm up')
        self.warmupbutton.connect('clicked', self.on_warmup)
        bb.add(self.warmupbutton)
        
        self.powerdownbutton = gtk.Button('Power down')
        self.powerdownbutton.connect('clicked', self.on_powerdown)
        bb.add(self.powerdownbutton)
        
        self.standbybutton = gtk.Button('Stand by')
        self.standbybutton.connect('clicked', self.on_standby)
        bb.add(self.standbybutton)
        
        self.rampupbutton = gtk.Button('Ramp up')
        self.rampupbutton.connect('clicked', self.on_rampup)
        bb.add(self.rampupbutton)
        
        if connection is None:
            self.connection = genix.GenixConnection('10.0.1.10')
        else:
            self.connection = connection
        self._timeout_handler = gobject.timeout_add_seconds(1, self.status.update_status, self.connection)
        self.status.labels['X-rays'].connect('status-changed', self.on_xrays)
        self.status.labels['Shutter'].connect('status-changed', self.on_shutter)
        self.status.labels['Status'].connect('status-changed', self.on_warmup)
    def finalize(self, *args, **kwargs):
        if self._timeout_handler is not None:
            gobject.source_remove(self._timeout_handler)
            self._timeout_handler = None
        if self._aux_timeout_handler is not None:
            gobject.source_remove(self._aux_timeout_handler)
            self._aux_timeout_handler = None
            
    def __del__(self):
        self.finalize()
    def on_warmup(self, widget, status=None, statstr=None, color=None):
        if not self.connection.xrays_state():
            return
        try:
            self.connection.do_warmup()
        except genix.GenixError:
            return
        for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
            x.set_sensitive(False)
        self._aux_timeout_handler = gobject.timeout_add_seconds(1, self.wait_for_warmup)
    def wait_for_warmup(self):
        if not self.connection.get_status()['CYCLE_TUBE_WARM_UP_ON']:
            for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
                x.set_sensitive(True)
            self._aux_timeout_handler = None
            return False
        return True
    def on_powerdown(self, widget):
        if not self.connection.xrays_state():
            return
        try:
            self.connection.do_poweroff()
        except genix.GenixError:
            return
        for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
            x.set_sensitive(False)
        self._aux_timeout_handler = gobject.timeout_add_seconds(1, self.wait_for_powerdown)
    def wait_for_powerdown(self):
        if self.connection.get_ht() == 0 and self.connection.get_current() == 0:
            for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
                x.set_sensitive(True)
            self._aux_timeout_handler = None
            return False
        return True
    def on_standby(self, widget):
        if not self.connection.xrays_state():
            return
        try:
            self.connection.do_standby()
        except genix.GenixError:
            return
        for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
            x.set_sensitive(False)
        self._aux_timeout_handler = gobject.timeout_add_seconds(1, self.wait_for_standby)
    def wait_for_standby(self):
        if self.connection.get_ht() == 30 and self.connection.get_current() == 0.30:
            for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
                x.set_sensitive(True)
            self._aux_timeout_handler = None
            return False
        return True
        
    def on_rampup(self, widget):
        if not self.connection.xrays_state():
            return
        try:
            self.connection.do_rampup()
        except genix.GenixError:
            return
        for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
            x.set_sensitive(False)
        self._aux_timeout_handler = gobject.timeout_add_seconds(1, self.wait_for_rampup)
    def wait_for_rampup(self):
        if self.connection.get_ht() == 50 and self.connection.get_current() == 0.60:
            for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
                x.set_sensitive(True)
            self._aux_timeout_handler = None
            return False
        return True
        
    def on_reset(self, widget):
        try:
            self.connection.reset_faults()
        except genix.GenixError:
            return True
        return True
    
    def on_xrays(self, widget, status=None, statstr=None, color=None):
        if isinstance(widget, gtk.Button):
            try:
                if self.connection.xrays_state():
                    self.connection.xrays_off()
                else:
                    self.connection.xrays_on()
            except genix.GenixError:
                pass
        else:
            if self.connection.xrays_state():
                self.xraybutton.set_label('X-rays OFF')
                for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
                    x.set_sensitive(True)
            else:
                self.xraybutton.set_label('X-rays ON')
                for x in [self.powerdownbutton, self.warmupbutton, self.standbybutton, self.rampupbutton]:
                    x.set_sensitive(False)
    def on_shutter(self, widget, status=None, statstr=None, color=None):
        if isinstance(widget, gtk.Button):
            try:
                if self.connection.shutter_state():
                    self.connection.shutter_close(wait_for_completion=False)
                else:
                    self.connection.shutter_open(wait_for_completion=False)
            except genix.GenixError:
                pass
        else:
            if self.connection.shutter_state():
                self.shutterbutton.set_label('Close shutter')
            else:
                self.shutterbutton.set_label('Open shutter')
            
if __name__ == '__main__':
    gcont = GenixControl()
    gcont.show_all()
    try:
        __IPYTHON__
    except NameError:
        def func(*args, **kwargs):
            gtk.main_quit()
        gcont.connect('delete-event', func)
        gtk.main()
