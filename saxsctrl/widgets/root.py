from gi.repository import Gtk
from gi.repository import GObject
import logging
import logging.handlers
import time
import resource
import sys
import traceback
import multiprocessing
import weakref

from ..hardware import credo
from . import genixcontrol, pilatuscontrol, samplesetup, instrumentsetup, beamalignment, scan, dataviewer, scanviewer, singleexposure, transmission, centering, qcalibration, data_reduction_setup, logdisplay, motorcontrol, instrumentconnection, saxssequence, nextfsn_monitor
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def my_excepthook(type_, value, traceback_):
    try:
        logger.critical('Unhandled exception', exc_info=(type_, value, traceback_))
    except:
        raise
#     dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
#                                str(type_) + ': ' + str(value))
#     dialog.format_secondary_text('Traceback:')
#     msgarea = dialog.get_message_area()
#     sw = Gtk.ScrolledWindow()
#     sw.set_size_request(200, 300)
#     msgarea.pack_start(sw, True, True, 0)
#     tv = Gtk.TextView()
#     sw.add(tv)
#     tv.get_buffer().set_text('\n'.join(traceback.format_tb(traceback_)))
#     tv.set_editable(False)
#     tv.set_wrap_mode(Gtk.WrapMode.WORD)
#     # tv.get_default_attributes().font = Pango.FontDescription('serif,monospace')
#     tv.set_justification(Gtk.Justification.LEFT)
#     msgarea.show_all()
#     dialog.set_title('Error!')
#     dialog.run()
#     dialog.destroy()
    
sys.excepthook = my_excepthook

class Tool(object):
    def __init__(self, credo, buttonname, windowname, windowclass, toolsection='General', equip_needed=[]):
        self.credo = weakref.proxy(credo)
        self.buttonname = buttonname
        self.windowname = windowname
        self.windowclass = windowclass
        self.equip_needed = equip_needed
        self.toolsection = toolsection
        self.window = None
        self.button = None
        self.menuitem = None
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
    def createmenuitem(self):
        if self.menuitem is None:
            self.menuitem = Gtk.MenuItem(self.buttonname)
            self.menuitem.connect('activate', self.createwindow)
        return self.menuitem
    
    def set_sensitivity(self, equips_available):
        sensitivity = all(eq in equips_available for eq in self.equip_needed)
        if self.window is not None:
            if not sensitivity:
                self.window.destroy()
                del self.window
                self.window = None
        if self.button is not None:
            self.button.set_sensitive(sensitivity)
        if self.menuitem is not None:
            self.menuitem.set_sensitive(sensitivity)
    def on_delete(self, *args):
        self.window.destroy()
        del self.window
        self.window = None

                
class RootWindow(Gtk.Window):
    _memusage = None
    _uptime = None
    _entrychanged_delayhandlers = None
    __gsignals__ = {'destroy':'override'}
    def __init__(self):
        Gtk.Window.__init__(self, Gtk.WindowType.TOPLEVEL)
        self._connections = []
        self.logdisplay = logdisplay.LogDisplay()
        self.logdisplay.set_size_request(600, 400)
        loghandler = logdisplay.Gtk3LogHandler(self.logdisplay)
        loghandler.setLevel(logging.DEBUG)
        logging.root.addHandler(loghandler)
        loghandler.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s: %(message)s  (Origin: %(name)s)'))
        self._starttime = time.time()
        self._entrychanged_delayhandlers = {}
        self.set_title('SAXS Control -- ROOT')
        # self.set_resizable(False)
        self.credo = credo.Credo()
        self._connections.append((self.credo.subsystems['Equipments'],
                                  self.credo.subsystems['Equipments'].connect('equipment-connection', lambda crd, name, state, equip: self.update_sensitivities())))
        
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vb)
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, False, False, 0)
        menubar = Gtk.MenuBar()
        hb.pack_start(menubar, True, True, 0)

        menus = {}     
        
        for mname in ['File', 'Configuration', 'Hardware', 'Scan', 'Expose', 'View']:
            mi = Gtk.MenuItem(label='_' + mname, use_underline=True)
            menubar.append(mi)
            menus[mname] = Gtk.Menu()
            mi.set_submenu(menus[mname])   
        
        mi = Gtk.ImageMenuItem(label='Save settings')
        menus['File'].append(mi)
        mi.connect('activate', lambda menuitem:self.credo.savestate())
        mi = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_QUIT, None)
        menus['File'].append(mi)
        mi.connect('activate', lambda menuitem:Gtk.main_quit())
        
        self.statuslabel_memory = Gtk.Label(label=''); self.statuslabel_memory.set_alignment(0, 0.5)
        hb.pack_start(self.statuslabel_memory, False, False, 3)
        self.statuslabel_uptime = Gtk.Label(label=''); self.statuslabel_uptime.set_alignment(0, 0.5)
        hb.pack_start(self.statuslabel_uptime, False, False, 3)
        
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, False, True, 0)
        f = Gtk.Frame(label='Accounting')
        hb.pack_start(f, True, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        l = Gtk.Label(label='User name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.username_entry = Gtk.Entry()
        self.username_entry.set_text(self.credo.username)
        self._connections.append((self.username_entry, self.username_entry.connect('changed', self.on_entry_changed, 'username')))
        tab.attach(self.username_entry, 1, 3, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Project name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.projectname_entry = Gtk.Entry()
        self.projectname_entry.set_text(self.credo.projectname)
        self._connections.append((self.projectname_entry, self.projectname_entry.connect('changed', self.on_entry_changed, 'projectname')))
        tab.attach(self.projectname_entry, 1, 3, row, row + 1)
        row += 1
        
        hb.pack_start(nextfsn_monitor.NextFSNMonitor(weakref.proxy(self.credo), 'Next exposure:'), False, True, 0)
        
        
        self.toolbuttons = [Tool(self.credo, 'GeniX', 'GeniX X-ray source controller', genixcontrol.GenixControl, 'Hardware', ['genix']),
                            Tool(self.credo, 'Pilatus-300k', 'Pilatus-300k controller', pilatuscontrol.PilatusControl, 'Hardware', ['pilatus']),
                            Tool(self.credo, 'Connections', 'Connections to equipment', instrumentconnection.InstrumentConnections, 'Configuration'),
                            Tool(self.credo, 'Set-up sample', 'Set-up samples', samplesetup.SampleListDialog, 'Configuration'),
                            Tool(self.credo, 'Set-up instrument', 'Instrument parameters', instrumentsetup.InstrumentSetup, 'Configuration'),
                            Tool(self.credo, 'Set-up data reduction', 'Data reduction setup', data_reduction_setup.DataRedSetup, 'Configuration'),
                            Tool(self.credo, 'Beam alignment', 'Beam alignment', beamalignment.BeamAlignment, 'Expose', ['genix', 'pilatus']),
                            Tool(self.credo, 'Scan', 'Scan', scan.Scan, 'Scan', ['genix', 'pilatus']),
                            Tool(self.credo, 'Single exposure', 'Single exposure', singleexposure.SingleExposure, 'Expose', ['genix', 'pilatus']),
                            Tool(self.credo, 'Transmission', 'Measure transmission', transmission.TransmissionMeasurement, 'Expose', ['genix', 'pilatus', 'tmcm351']),
                            Tool(self.credo, 'Data viewer & masking', '2D data viewer and masking', dataviewer.DataViewer, 'View'),
                            Tool(self.credo, 'Scan viewer', 'Scan viewer', scanviewer.ScanViewer, 'View'),
                            Tool(self.credo, 'Q calibration', 'Q calibration', qcalibration.QCalibrationDialog, 'Configuration'),
                            Tool(self.credo, 'Centering', 'Center finding', centering.CenteringDialog, 'Configuration'),
                            Tool(self.credo, 'Motors', 'Motor control', motorcontrol.MotorMonitor, 'Hardware', ['tmcm351']),
                            Tool(self.credo, 'Automatic sequence', 'Automatic sequence', saxssequence.SAXSSequence, 'Expose')  # , genixneeded=True, pilatusneeded=True, motorneeded=True)
                            ]
        for t in self.toolbuttons:
            mi = t.createmenuitem()
            menus[t.toolsection].append(mi)
        self.update_sensitivities()
        
        ssetupmenuitem = Gtk.MenuItem(label='Subsystems...')
        menus['Configuration'].append(ssetupmenuitem)
        sm = Gtk.Menu()
        ssetupmenuitem.set_submenu(sm)
        
        for ss in sorted(self.credo.subsystems):
            mi = Gtk.MenuItem(label=ss)
            sm.append(mi)
            mi.connect('activate', lambda menuitem, ssname:self._run_subsystem_setup(ssname), ss)
        
        f = Gtk.Frame(label='Log')
        vb.pack_start(f, True, True, 0)
        
        f.add(self.logdisplay)
        self.update_statuslabels()
        GObject.timeout_add_seconds(1, self.update_statuslabels)
    def _run_subsystem_setup(self, ssname):
        dia = self.credo.subsystems[ssname].create_setup_dialog(title='Set-up %s subsystem' % ssname)
        while dia.run() not in [Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT]:
            pass
        dia.destroy()
        del dia
    def update_statuslabels(self):
        self._memusage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        self.statuslabel_memory.set_text('%.1f MB' % (self._memusage / 1024))
        self._uptime = int(time.time() - self._starttime)
        self.statuslabel_uptime.set_text('%02d:%02d:%02d' % (self._uptime / 3600, (self._uptime % 3600) / 60, self._uptime % 60))
        return True
    def update_sensitivities(self):
        for t in self.toolbuttons:
            t.set_sensitivity(self.credo.subsystems['Equipments'].connected_equipments())
        return False
    def do_destroy(self):
        logger.debug('Destroying root window.')
        self.credo.savestate()
        for obj, c in self._connections:
            obj.disconnect(c)
        self._connections = []
        del self.credo
    def __del__(self):
        logger.debug('Destructing root window.')
    def on_entry_changed(self, entry, entrytext):
        if entrytext in self._entrychanged_delayhandlers:
            GObject.source_remove(self._entrychanged_delayhandlers[entrytext])
        self._entrychanged_delayhandlers[entrytext] = GObject.timeout_add_seconds(1, self.on_entry_changed_finalize, entry, entrytext)
    def on_entry_changed_finalize(self, entry, entrytext):
        self.credo.__setattr__(entrytext, entry.get_text())
        
