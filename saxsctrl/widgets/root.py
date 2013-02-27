import gtk
import gobject
import logging
import sasgui
import time
import resource


from ..hardware import pilatus, genix, credo
from . import genixcontrol, pilatuscontrol, samplesetup, instrumentsetup, beamalignment, timedscan, dataviewer, scanviewer, singleexposure, transmission, centering, qcalibration
logger = logging.getLogger('SAXSCtrl')

@sasgui.PyGTKCallback.PyGTKCallback
class RootWindow(gtk.Window):
    pilatus = None
    genix = None
    _filechooserdialogs = None
    _tools = None
    _memusage = None
    _uptime = None
    def __init__(self):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self._starttime = time.time()
        self.set_title('SAXS Control -- ROOT')
        self.set_resizable(False)
        self._tools = {}  # dict of currently open tool windows.
        self._genix_tools = []  # list of toolbuttons depending on a working connection to genix controller
        self._pilatus_tools = []  # list of toolbuttons depending on a working connection to camserver
        self.credo = credo.Credo()
        vb = gtk.VBox()
        self.add(vb)
        f = gtk.Frame('Status')
        vb.pack_start(f, False)
        tab = gtk.Table()
        f.add(tab)
        row = 0
        
        l = gtk.Label('Allocated memory:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.statuslabel_memory = gtk.Label(''); self.statuslabel_memory.set_alignment(0, 0.5)
        tab.attach(self.statuslabel_memory, 1, 2, row, row + 1, gtk.FILL | gtk.EXPAND, gtk.FILL | gtk.EXPAND, 10, 0)
        row += 1
        
        l = gtk.Label('Uptime:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.statuslabel_uptime = gtk.Label(''); self.statuslabel_uptime.set_alignment(0, 0.5)
        tab.attach(self.statuslabel_uptime, 1, 2, row, row + 1, gtk.FILL | gtk.EXPAND, gtk.FILL | gtk.EXPAND, 10, 0)
        row += 1
        
        
        f = gtk.Frame('Instrument connection')
        vb.pack_start(f, False)
        tab = gtk.Table()
        f.add(tab)
        row = 0
        
        l = gtk.Label('Pilatus host:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.camserverhost_entry = gtk.Entry()
        self.camserverhost_entry.set_text('pilatus300k.saxs:41234')
        tab.attach(self.camserverhost_entry, 1, 2, row, row + 1)
        self.camserverconnect_button = gtk.Button(stock=gtk.STOCK_CONNECT)
        tab.attach(self.camserverconnect_button, 2, 3, row, row + 1, gtk.FILL, gtk.FILL)
        self.camserverconnect_button.connect('clicked', self.on_camserver_connect)
        row += 1
        
        l = gtk.Label('GeniX host:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.genixhost_entry = gtk.Entry()
        self.genixhost_entry.set_text('genix.saxs:502')
        tab.attach(self.genixhost_entry, 1, 2, row, row + 1)
        self.genixconnect_button = gtk.Button(stock=gtk.STOCK_CONNECT)
        tab.attach(self.genixconnect_button, 2, 3, row, row + 1, gtk.FILL, gtk.FILL)
        self.genixconnect_button.connect('clicked', self.on_genix_connect)
        row += 1

        l = gtk.Label('Image path:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.imagepath_entry = gtk.Entry()
        self.imagepath_entry.set_text('/net/pilatus300k.saxs/disk2/images')
        self.imagepath_entry.connect('changed', self.on_entry_changed, 'imagepath')
        tab.attach(self.imagepath_entry, 1, 2, row, row + 1)
        self.imagepath_button = gtk.Button(stock=gtk.STOCK_OPEN)
        tab.attach(self.imagepath_button, 2, 3, row, row + 1, gtk.FILL, gtk.FILL)
        self.imagepath_button.connect('clicked', self.on_pathbutton, self.imagepath_entry, gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        row += 1

        l = gtk.Label('File path:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.filepath_entry = gtk.Entry()
        self.filepath_entry.set_text('/home/labuser/credo_data/current')
        self.filepath_entry.connect('changed', self.on_entry_changed, 'filepath')
        tab.attach(self.filepath_entry, 1, 2, row, row + 1)
        self.filepath_button = gtk.Button(stock=gtk.STOCK_OPEN)
        tab.attach(self.filepath_button, 2, 3, row, row + 1, gtk.FILL, gtk.FILL)
        self.filepath_button.connect('clicked', self.on_pathbutton, self.filepath_entry, gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        row += 1
        
        l = gtk.Label('User name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.username_entry = gtk.Entry()
        self.username_entry.set_text(self.credo.username)
        self.username_entry.connect('changed', self.on_entry_changed, 'username')
        self.on_entry_changed(self.username_entry, 'username')
        tab.attach(self.username_entry, 1, 3, row, row + 1)
        row += 1
        
        l = gtk.Label('Project name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.projectname_entry = gtk.Entry()
        self.projectname_entry.set_text(self.credo.projectname)
        self.projectname_entry.connect('changed', self.on_entry_changed, 'projectname')
        self.on_entry_changed(self.projectname_entry, 'projectname')
        tab.attach(self.projectname_entry, 1, 3, row, row + 1)
        row += 1
        
        f = gtk.Frame('Tools')
        vb.pack_start(f, False)
        vb1 = gtk.VBox()
        tab = gtk.Table()
        f.add(vb1)
        vb1.pack_start(tab, False)

        self.toolbutton_genixcontrol = gtk.Button('GeniX controller')
        tab.attach(self.toolbutton_genixcontrol, 0, 1, 0, 1)
        self.toolbutton_genixcontrol.connect('clicked', self.starttool)
        self._genix_tools.append(self.toolbutton_genixcontrol)
        self.toolbutton_genixcontrol.set_sensitive(False)

        self.toolbutton_pilatuscontrol = gtk.Button('Pilatus controller')
        tab.attach(self.toolbutton_pilatuscontrol, 1, 2, 0, 1)
        self.toolbutton_pilatuscontrol.connect('clicked', self.starttool)
        self._pilatus_tools.append(self.toolbutton_pilatuscontrol)
        self.toolbutton_pilatuscontrol.set_sensitive(False)
        
        self.toolbutton_samplesetup = gtk.Button('Set-up sample')
        tab.attach(self.toolbutton_samplesetup, 0, 1, 1, 2)
        self.toolbutton_samplesetup.connect('clicked', self.starttool)

        self.toolbutton_instrumentsetup = gtk.Button('Set-up instrument')
        tab.attach(self.toolbutton_instrumentsetup, 1, 2, 1, 2)
        self.toolbutton_instrumentsetup.connect('clicked', self.starttool)

        self.toolbutton_beamalignment = gtk.Button('Beam alignment')
        tab.attach(self.toolbutton_beamalignment, 0, 1, 2, 3)
        self.toolbutton_beamalignment.connect('clicked', self.starttool)
        self._genix_tools.append(self.toolbutton_beamalignment)
        self._pilatus_tools.append(self.toolbutton_beamalignment)
        self.toolbutton_beamalignment.set_sensitive(False)

        self.toolbutton_timedscan = gtk.Button('Timed scan')
        tab.attach(self.toolbutton_timedscan, 1, 2, 2, 3)
        self.toolbutton_timedscan.connect('clicked', self.starttool)
        self._genix_tools.append(self.toolbutton_timedscan)
        self._pilatus_tools.append(self.toolbutton_timedscan)
        self.toolbutton_timedscan.set_sensitive(False)

        self.toolbutton_singleexposure = gtk.Button('Single exposure')
        tab.attach(self.toolbutton_singleexposure, 0, 1, 3, 4)
        self.toolbutton_singleexposure.connect('clicked', self.starttool)
        self._genix_tools.append(self.toolbutton_singleexposure)
        self._pilatus_tools.append(self.toolbutton_singleexposure)
        self.toolbutton_singleexposure.set_sensitive(False)

        self.toolbutton_transmission = gtk.Button('Transmission')
        tab.attach(self.toolbutton_transmission, 1, 2, 3, 4)
        self.toolbutton_transmission.connect('clicked', self.starttool)
        self._genix_tools.append(self.toolbutton_transmission)
        self._pilatus_tools.append(self.toolbutton_transmission)
        self.toolbutton_transmission.set_sensitive(False)
        
        vb1.pack_start(gtk.HSeparator(), False)
        tab = gtk.Table()
        vb1.pack_start(tab, False)

        self.toolbutton_dataviewer = gtk.Button('Data viewer')
        tab.attach(self.toolbutton_dataviewer, 0, 1, 0, 1)
        self.toolbutton_dataviewer.connect('clicked', self.starttool)
    
        self.toolbutton_scanviewer = gtk.Button('Scan viewer')
        tab.attach(self.toolbutton_scanviewer, 1, 2, 0, 1)
        self.toolbutton_scanviewer.connect('clicked', self.starttool)

        
        self.toolbutton_centering = gtk.Button('Centering')
        tab.attach(self.toolbutton_centering, 0, 1, 1, 2)
        self.toolbutton_centering.connect('clicked', self.starttool)

        self.toolbutton_qcalib = gtk.Button('Q calibration')
        tab.attach(self.toolbutton_qcalib, 1, 2, 1, 2)
        self.toolbutton_qcalib.connect('clicked', self.starttool)


        gobject.timeout_add_seconds(1, self.update_statuslabels)
    def update_statuslabels(self):
        self._memusage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        self.statuslabel_memory.set_text('%.1f MB' % (self._memusage / 1024))
        self._uptime = int(time.time() - self._starttime)
        self.statuslabel_uptime.set_text('%02d:%02d:%02d' % (self._uptime / 3600, (self._uptime % 3600) / 60, self._uptime % 60))
        return True
    def on_entry_changed(self, entry, entrytext):
        self.credo.__setattr__(entrytext, entry.get_text())
    def starttool(self, button=None):
        if button not in self._tools:
            if button is self.toolbutton_genixcontrol:
                self._tools[button] = genixcontrol.GenixControl(self.genix, 'SAXSControl -- GeniX controller')
            elif button is self.toolbutton_pilatuscontrol:
                self._tools[button] = pilatuscontrol.PilatusControl(self.credo, 'SAXSControl -- Pilatus controller')
            elif button is self.toolbutton_samplesetup:
                self._tools[button] = samplesetup.SampleListDialog(self.credo, 'SAXSControl -- Sample parameters')
            elif button is self.toolbutton_instrumentsetup:
                self._tools[button] = instrumentsetup.InstrumentSetup(self.credo, 'SAXSControl -- Instrument parameters')
            elif button is self.toolbutton_beamalignment:
                self._tools[button] = beamalignment.BeamAlignment(self.credo, 'SAXSControl -- Beam alignment')
            elif button is self.toolbutton_timedscan:
                self._tools[button] = timedscan.TimedScan(self.credo, 'SAXSControl -- Timed scan')
            elif button is self.toolbutton_dataviewer:
                self._tools[button] = dataviewer.DataViewer(self.credo, 'SAXSControl -- Data viewer')
            elif button is self.toolbutton_scanviewer:
                self._tools[button] = scanviewer.ScanViewer(self.credo, 'SAXSControl -- Scan viewer')
            elif button is self.toolbutton_singleexposure:
                self._tools[button] = singleexposure.SingleExposure(self.credo, 'SAXSControl -- Single exposure')
            elif button is self.toolbutton_transmission:
                self._tools[button] = transmission.TransmissionMeasurement(self.credo, 'SAXSControl -- Transmission measurement')
            elif button is self.toolbutton_centering:
                self._tools[button] = centering.CenteringDialog(self.credo, 'SAXSControl -- Center finding')
            elif button is self.toolbutton_qcalib:
                self._tools[button] = qcalibration.QCalibrationDialog(self.credo, 'SAXSControl -- Q calibration')
            else:
                raise NotImplementedError('Tool button "%s" is not implemented' % button.get_label())
            self._tools[button].connect('delete-event', self.stoptool, button)
            self._tools[button].show_all()
        else:
            self._tools[button].present()
    def stoptool(self, widget, event, button):
        del self._tools[button]

    def on_camserver_connect(self, button):
        if self.is_pilatus_connected():
            self.disconnect_from_camserver()
            self.camserverconnect_button.set_label(gtk.STOCK_CONNECT)
        else:
            host = self.camserverhost_entry.get_text()
            if ':' in host:
                host, port = host.rsplit(':', 1)
                port = int(port)
            else:
                port = 41234
            try:
                self.connect_to_camserver(host, port)
            except pilatus.PilatusError:
                md = gtk.MessageDialog(self, gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, message_format='Cannot connect to the Pilatus camserver!')
                md.run()
                md.destroy()
                return
            self.camserverconnect_button.set_label(gtk.STOCK_DISCONNECT)
    def on_genix_connect(self, button):
        if self.is_genix_connected():
            self.disconnect_from_genix()
            self.genixconnect_button.set_label(gtk.STOCK_CONNECT)
        else:
            host = self.genixhost_entry.get_text()
            if ':' in host:
                host, port = host.rsplit(':', 1)
                port = int(port)
            else:
                port = 502
            try:
                self.connect_to_genix(host, port)
            except genix.GenixError:
                md = gtk.MessageDialog(self, gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, message_format='Cannot connect to genix controller!')
                md.run()
                md.destroy()
                return
            self.genixconnect_button.set_label(gtk.STOCK_DISCONNECT)
    def on_pathbutton(self, button, entry, action):
        if self._filechooserdialogs is None:
            self._filechooserdialogs = {}
        if entry not in self._filechooserdialogs:
            self._filechooserdialogs[entry] = gtk.FileChooserDialog('Select a folder...', None, action, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == gtk.RESPONSE_OK:
            entry.set_text(self._filechooserdialogs[entry].get_filename())
        self._filechooserdialogs[entry].hide()
        return True
    def is_pilatus_connected(self):
        return self.pilatus is not None
    def disconnect_from_camserver(self):
        if self.is_pilatus_connected():
            self.pilatus.disconnect()
            del self.pilatus
            del self.credo.pilatus
            self.credo.pilatus = None
            self.pilatus = None
    def update_sensitivities(self):
        pilatusonly = [p for p in self._pilatus_tools if p not in self._genix_tools]
        genixonly = [p for p in self._genix_tools if p not in self._pilatus_tools]
        both = [p for p in self._pilatus_tools if p in self._genix_tools]
        
        if not self.is_pilatus_connected():
            for p in pilatusonly + both:
                p.set_sensitive(False)
        if not self.is_genix_connected():
            for p in genixonly + both:
                p.set_sensitive(False)
        if self.is_pilatus_connected():
            for p in pilatusonly:
                p.set_sensitive(True)
        if self.is_genix_connected():
            for p in genixonly:
                p.set_sensitive(True)
        if self.is_pilatus_connected() and self.is_genix_connected():
            for p in both:
                p.set_sensitive(True)
            
    def connect_to_camserver(self, host, port=41234):
        if not self.is_pilatus_connected():
            self.pilatus = pilatus.PilatusConnection(host, port)
            def _handler(arg, arg1):
                gobject.idle_add(self.on_disconnect_from_camserver, arg)
            self.pilatus.register_event_handler('disconnect_from_camserver', _handler)
            self.credo.pilatus = self.pilatus
            self.pilatus.setthreshold(4024, 'highG')
        self.update_sensitivities()
    def on_disconnect_from_camserver(self, arg):
        if arg == 'error':
            logger.error('Lost connection to camserver')
            md = gtk.MessageDialog(self, gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, message_format='Lost connection to the Pilatus camserver!')
            md.run()
            md.destroy()
        self.disconnect_from_camserver()
        self.camserverconnect_button.set_label(gtk.STOCK_CONNECT)
        for p in self._pilatus_tools:
            if p in self._tools:
                self._tools[p].destroy()
                del self._tools[p]
        self.update_sensitivities()
        self.emit('camserver_disconnect')
    def is_genix_connected(self):
        return self.genix is not None
    def disconnect_from_genix(self):
        if self.is_genix_connected():
            # self.genix.disconnect()
            self.genix.shutter_close(False)
            del self.genix
            self.genix = None
            del self.credo.genix
            self.credo.genix = None
            self.on_disconnect_from_genix('normal')
    def connect_to_genix(self, host, port=502):
        if not self.is_genix_connected():
            self.genix = genix.GenixConnection(host, port)
            self.credo.genix = self.genix
            self.genix.error_handler = self.on_disconnect_from_genix
        self.update_sensitivities()
    def on_disconnect_from_genix(self, arg):
        if arg == 'error':
            logger.error('Lost connection to genix controller')
            md = gtk.MessageDialog(self, gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, message_format='Lost connection to the genix controller!')
            md.run()
            md.destroy()
        self.disconnect_from_genix()
        self.genixconnect_button.set_label(gtk.STOCK_CONNECT)
        for p in self._genix_tools:
            if p in self._tools:
                self._tools[p].destroy()
                del self._tools[p]
        self.update_sensitivities()
        self.emit('camserver_disconnect')

    def get_pilatus(self):
        return self.pilatus
    def get_genix(self):
        return self.genix
    def get_credo(self):
        return self.credo
    def __del__(self):
        print "DEL ROOT"
        del self.credo
