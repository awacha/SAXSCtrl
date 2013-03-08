from gi.repository import Gtk
from gi.repository import GObject
import logging
import time
import resource
import sys
import traceback

from ..hardware import pilatus, genix, credo
from . import genixcontrol, pilatuscontrol, samplesetup, instrumentsetup, beamalignment, timedscan, dataviewer, scanviewer, singleexposure, transmission, centering, qcalibration, data_reduction_setup
logger = logging.getLogger('SAXSCtrl')

def my_excepthook(type_, value, traceback_):
    try:
        logger.critical('Unhandled exception', exc_info=(type_, value, traceback_))
    except:
        raise
    dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                               str(type_) + ': ' + str(value))
    dialog.format_secondary_text('Traceback:')
    msgarea = dialog.get_message_area()
    sw = Gtk.ScrolledWindow()
    sw.set_size_request(200, 300)
    msgarea.pack_start(sw, True, True, 0)
    tv = Gtk.TextView()
    sw.add(tv)
    tv.get_buffer().set_text('\n'.join(traceback.format_tb(traceback_)))
    tv.set_editable(False)
    tv.set_wrap_mode(Gtk.WrapMode.WORD)
    # tv.get_default_attributes().font = Pango.FontDescription('serif,monospace')
    tv.set_justification(Gtk.Justification.LEFT)
    msgarea.show_all()
    dialog.set_title('Error!')
    dialog.run()
    dialog.destroy()
    
# sys.excepthook = my_excepthook

class Tool(object):
    def __init__(self, credo, buttonname, windowname, windowclass, toolsection='General', genixneeded=False, pilatusneeded=False):
        self.credo = credo
        self.buttonname = buttonname
        self.windowname = windowname
        self.windowclass = windowclass
        self.genixneeded = genixneeded
        self.pilatusneeded = pilatusneeded
        self.toolsection = toolsection
        self.window = None
        self.button = None
    def createwindow(self, button):
        if self.window is None:
            try:
                self.window = self.windowclass(self.credo, self.windowname)
            except:
                del self.window
                self.window = None
                raise
            else:
                self.window.connect('delete-event', self.on_delete)
                self.window.show_all()
        if self.window is not None:
            self.window.present()
        return self.window
    def createbutton(self):
        if self.button is None:
            self.button = Gtk.Button(self.buttonname)
            self.button.connect('clicked', self.createwindow)
        return self.button
    def set_sensitivity(self, genix=False, pilatus=False):
        if self.window is not None:
            if not (((not self.genixneeded) or genix) and 
                    ((not self.pilatusneeded) or pilatus)):
                self.window.hide()
        if self.button is not None:
            self.button.set_sensitive(((not self.genixneeded) or genix) and 
                                      ((not self.pilatusneeded) or pilatus))
    def on_delete(self, *args):
        self.window.destroy()
        del self.window
        self.window = None
                
class RootWindow(Gtk.Window):
    __gsignals__ = {'camserver_disconnect':(GObject.SignalFlags.RUN_FIRST, None, ())}
    pilatus = None
    genix = None
    _filechooserdialogs = None
    _tools = None
    _memusage = None
    _uptime = None
    def __init__(self):
        Gtk.Window.__init__(self, Gtk.WindowType.TOPLEVEL)
        self._starttime = time.time()
        self.set_title('SAXS Control -- ROOT')
        self.set_resizable(False)
        self._tools = {}  # dict of currently open tool windows.
        self._genix_tools = []  # list of toolbuttons depending on a working connection to genix controller
        self._pilatus_tools = []  # list of toolbuttons depending on a working connection to camserver
        self.credo = credo.Credo()
        vb = Gtk.VBox()
        self.add(vb)
        f = Gtk.Frame(label='Status')
        vb.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        l = Gtk.Label(label='Allocated memory:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.statuslabel_memory = Gtk.Label(label=''); self.statuslabel_memory.set_alignment(0, 0.5)
        tab.attach(self.statuslabel_memory, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 10, 0)
        row += 1
        
        l = Gtk.Label(label='Uptime:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.statuslabel_uptime = Gtk.Label(label=''); self.statuslabel_uptime.set_alignment(0, 0.5)
        tab.attach(self.statuslabel_uptime, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 10, 0)
        row += 1
        
        
        f = Gtk.Frame(label='Instrument connection')
        vb.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        l = Gtk.Label(label='Pilatus host:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.camserverhost_entry = Gtk.Entry()
        self.camserverhost_entry.set_text('pilatus300k.saxs:41234')
        tab.attach(self.camserverhost_entry, 1, 2, row, row + 1)
        self.camserverconnect_button = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        tab.attach(self.camserverconnect_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.camserverconnect_button.connect('clicked', self.on_camserver_connect)
        row += 1
        
        l = Gtk.Label(label='GeniX host:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.genixhost_entry = Gtk.Entry()
        self.genixhost_entry.set_text('genix.saxs:502')
        tab.attach(self.genixhost_entry, 1, 2, row, row + 1)
        self.genixconnect_button = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        tab.attach(self.genixconnect_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.genixconnect_button.connect('clicked', self.on_genix_connect)
        row += 1

        l = Gtk.Label(label='Image path:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.imagepath_entry = Gtk.Entry()
        self.imagepath_entry.set_text('/net/pilatus300k.saxs/disk2/images')
        self.imagepath_entry.connect('changed', self.on_entry_changed, 'imagepath')
        tab.attach(self.imagepath_entry, 1, 2, row, row + 1)
        self.imagepath_button = Gtk.Button(stock=Gtk.STOCK_OPEN)
        tab.attach(self.imagepath_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.imagepath_button.connect('clicked', self.on_pathbutton, self.imagepath_entry, Gtk.FileChooserAction.SELECT_FOLDER)
        row += 1

        l = Gtk.Label(label='File path:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.filepath_entry = Gtk.Entry()
        self.filepath_entry.set_text('/home/labuser/credo_data/current')
        self.filepath_entry.connect('changed', self.on_entry_changed, 'filepath')
        tab.attach(self.filepath_entry, 1, 2, row, row + 1)
        self.filepath_button = Gtk.Button(stock=Gtk.STOCK_OPEN)
        tab.attach(self.filepath_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.filepath_button.connect('clicked', self.on_pathbutton, self.filepath_entry, Gtk.FileChooserAction.SELECT_FOLDER)
        row += 1
        
        l = Gtk.Label(label='User name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.username_entry = Gtk.Entry()
        self.username_entry.set_text(self.credo.username)
        self.username_entry.connect('changed', self.on_entry_changed, 'username')
        self.on_entry_changed(self.username_entry, 'username')
        tab.attach(self.username_entry, 1, 3, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Project name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.projectname_entry = Gtk.Entry()
        self.projectname_entry.set_text(self.credo.projectname)
        self.projectname_entry.connect('changed', self.on_entry_changed, 'projectname')
        self.on_entry_changed(self.projectname_entry, 'projectname')
        tab.attach(self.projectname_entry, 1, 3, row, row + 1)
        row += 1
        
        self.toolbuttons = [Tool(self.credo, 'GeniX', 'GeniX X-ray source controller', genixcontrol.GenixControl, 'Hardware control', genixneeded=True, pilatusneeded=False),
                            Tool(self.credo, 'Pilatus-300k', 'Pilatus-300k controller', pilatuscontrol.PilatusControl, 'Hardware control', genixneeded=False, pilatusneeded=True),
                            Tool(self.credo, 'Set-up sample', 'Set-up samples', samplesetup.SampleListDialog, 'Setup & Calibration'),
                            Tool(self.credo, 'Set-up instrument', 'Instrument parameters', instrumentsetup.InstrumentSetup, 'Setup & Calibration'),
                            Tool(self.credo, 'Set-up data reduction', 'Data reduction setup', data_reduction_setup.DataRedSetup, 'Setup & Calibration'),
                            Tool(self.credo, 'Beam alignment', 'Beam alignment', beamalignment.BeamAlignment, 'Exposure', genixneeded=True, pilatusneeded=True),
                            Tool(self.credo, 'Timed scan', 'Timed scan', timedscan.TimedScan, 'Scan', genixneeded=True, pilatusneeded=True),
                            Tool(self.credo, 'Single exposure', 'Single exposure', singleexposure.SingleExposure, 'Exposure', genixneeded=True, pilatusneeded=True),
                            Tool(self.credo, 'Transmission', 'Measure transmission', transmission.TransmissionMeasurement, 'Exposure', genixneeded=True, pilatusneeded=True),
                            Tool(self.credo, 'Data viewer & masking', '2D data viewer and masking', dataviewer.DataViewer, 'Viewer'),
                            Tool(self.credo, 'Scan viewer', 'Scan viewer', scanviewer.ScanViewer, 'Viewer'),
                            Tool(self.credo, 'Q calibration', 'Q calibration', qcalibration.QCalibrationDialog, 'Setup & Calibration'),
                            Tool(self.credo, 'Centering', 'Center finding', centering.CenteringDialog, 'Setup & Calibration'),
                            ]
        toolsections = ['Hardware control', 'Scan', 'Setup & Calibration', 'Exposure', 'Viewer']
        toolsections.extend(list(set([t.toolsection for t in self.toolbuttons]) - set(toolsections)))
        for ts in toolsections:
            f = Gtk.Frame(label=ts)
            vb.pack_start(f, False, True, 0)
            tab = Gtk.Table()
            f.add(tab)
            for i, t in enumerate([t for t in self.toolbuttons if t.toolsection == ts]):
                b = t.createbutton()
                tab.attach(b, i % 2, i % 2 + 1, i / 2, i / 2 + 1)
        self.update_sensitivities()


        GObject.timeout_add_seconds(1, self.update_statuslabels)
    def update_statuslabels(self):
        self._memusage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        self.statuslabel_memory.set_text('%.1f MB' % (self._memusage / 1024))
        self._uptime = int(time.time() - self._starttime)
        self.statuslabel_uptime.set_text('%02d:%02d:%02d' % (self._uptime / 3600, (self._uptime % 3600) / 60, self._uptime % 60))
        return True
    def on_entry_changed(self, entry, entrytext):
        self.credo.__setattr__(entrytext, entry.get_text())

    def on_camserver_connect(self, button):
        if self.is_pilatus_connected():
            self.disconnect_from_camserver()
            self.camserverconnect_button.set_label(Gtk.STOCK_CONNECT)
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
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message_format='Cannot connect to the Pilatus camserver!')
                md.run()
                md.destroy()
                return
            self.camserverconnect_button.set_label(Gtk.STOCK_DISCONNECT)
    def on_genix_connect(self, button):
        if self.is_genix_connected():
            self.disconnect_from_genix()
            self.genixconnect_button.set_label(Gtk.STOCK_CONNECT)
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
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message_format='Cannot connect to genix controller!')
                md.run()
                md.destroy()
                return
            self.genixconnect_button.set_label(Gtk.STOCK_DISCONNECT)
    def on_pathbutton(self, button, entry, action):
        if self._filechooserdialogs is None:
            self._filechooserdialogs = {}
        if entry not in self._filechooserdialogs:
            self._filechooserdialogs[entry] = Gtk.FileChooserDialog('Select a folder...', None, action, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == Gtk.ResponseType.OK:
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
        for t in self.toolbuttons:
            t.set_sensitivity(genix=self.is_genix_connected(), pilatus=self.is_pilatus_connected())
            
    def connect_to_camserver(self, host, port=41234):
        if not self.is_pilatus_connected():
            self.pilatus = pilatus.PilatusConnection(host, port)
            def _handler(arg, arg1):
                GObject.idle_add(self.on_disconnect_from_camserver, arg)
            self.pilatus.register_event_handler('disconnect_from_camserver', _handler)
            self.credo.pilatus = self.pilatus
            self.pilatus.setthreshold(4024, 'highG')
        self.update_sensitivities()
    def on_disconnect_from_camserver(self, arg):
        if arg == 'error':
            logger.error('Lost connection to camserver')
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message_format='Lost connection to the Pilatus camserver!')
            md.run()
            md.destroy()
        self.disconnect_from_camserver()
        self.camserverconnect_button.set_label(Gtk.STOCK_CONNECT)
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
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message_format='Lost connection to the genix controller!')
            md.run()
            md.destroy()
        self.disconnect_from_genix()
        self.genixconnect_button.set_label(Gtk.STOCK_CONNECT)
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
        del self.credo
