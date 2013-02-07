# -*- coding: utf-8 -*-
"""
pilatus_exposure.py

Make exposures.
"""

import gobject
gobject.threads_init()
import itertools
import ConfigParser
import gtk
from ..hardware import pilatus
import collections
import resource
import os
import sastool
import sasgui
import datetime
import logging
import time
import glob
from widgets import StatusLabel

logger = logging.getLogger(__name__)

class PilatusStatus(gtk.Frame):
    _monitor_timeout = 1
    _slowmonitor_timeout = 30
    timeouthandler_slow = None
    timeouthandler = None
    def __init__(self, controller):
        gtk.Frame.__init__(self, 'Status monitor')
        self._controller = controller
        sw = gtk.ScrolledWindow()
        self.add(sw)
        hbox = gtk.HBox(True)
        sw.add_with_viewport(hbox)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
        self.statuslabels = collections.OrderedDict()
        self.statuslabels['camstate'] = StatusLabel('State', {'exposing':'exposing', 'idle':'idle', 'error':'error', 'UNKNOWN':'offline'},
                                         {'exposing':gtk.gdk.color_parse('turquoise'), 'idle':gtk.gdk.color_parse('green'), 'error':gtk.gdk.color_parse('red'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')}, 'UNKNOWN')
        self.statuslabels['Timeleft'] = StatusLabel('Time left', {'OK':'OK', 'UNKNOWN':'UNKNOWN'}, {'OK':gtk.gdk.color_parse('white'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')}, 'UNKNOWN')
        self.statuslabels['Done'] = StatusLabel('Done %', {'OK':'OK', 'UNKNOWN':'UNKNOWN'}, {'OK':gtk.gdk.color_parse('white'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')}, 'UNKNOWN')
        self.statuslabels['t0'] = StatusLabel('P.board temp.')
        self.statuslabels['h0'] = StatusLabel('P.board hum.')
        self.statuslabels['t1'] = StatusLabel('Baseplate temp.')
        self.statuslabels['h1'] = StatusLabel('Baseplate hum.')
        self.statuslabels['t2'] = StatusLabel('Det.head temp.')
        self.statuslabels['h2'] = StatusLabel('Det.head hum.')
        self.statuslabels['mem'] = StatusLabel('memory', {'OK':'N/A', 'UNKNOWN':'UNKNOWN'}, {'OK':gtk.gdk.color_parse('white'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')})
        for l in self.statuslabels.itervalues():
            hbox.pack_start(l, False)
        self.set_size_request(80 * 8, 100)
        self.show_all()
        for l in self.statuslabels.values():
            l.connect('status-changed', self.on_status_changed_logger)
    def on_status_changed_logger(self, statlabel, status, statstr, color):
        if status.upper() == 'ERROR' and statlabel.labelname not in ['Shutter', 'Remote', 'X-rays', 'Status']:
            logger.error(statlabel.labelname + '; message: ' + statstr)
        elif status.upper() == 'WARNING':
            logger.warning(statlabel.labelname + '; message: ' + statstr)
        else:
            logger.info('Status changed: ' + statlabel.labelname + ', new status: ' + status + ', message: ' + statstr)
        return False
    def get_exposure_mode(self):
        return self._controller.is_exposure_mode()
        
    def updatemonitor_slow(self, pc=None):
        u = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        self['mem'].set_status('OK', '%.2f MB' % (u / 1024))
        if pc is None or not pc.connected():
            for l in self.statuslabels:
                if l != 'mem':
                    self[l] = 'UNKNOWN'
            return True
        if self._controller.is_exposure_mode() and self._controller.get_timeleft() < 10:
            logger.debug('Skipping slow update operation because nearing end of exposure.')
            return True
        
        try:
            thdata = pc.temphum()
            if not thdata:
                thdata = pc.temphum(12)
                thdata = pc.temphum()
        except pilatus.PilatusError:
            for widgetname in ('t0', 't1', 't2', 'h0', 'h1', 'h2'):
                self.__getitem__(widgetname).set_status('UNKNOWN') 
        else:
            tempsoft = [(20, 35), (20, 30), (20, 35)]
            temphard = [(15, 55), (15, 35), (15, 45)]
            humsoft = [30, 30, 20]
            humhard = [80, 80, 30]
            for data, ts, th, hs, hh, twidget, hwidget in zip(thdata, tempsoft, temphard, humsoft, humhard, (self['t0'], self['t1'], self['t2']), (self['h0'], self['h1'], self['h2'])):
                if (data['Temp'] <= max(ts)) and (data['Temp'] >= min(ts)):
                    twidget.set_status('OK', u'%.1f°C' % data['Temp'])
                elif (data['Temp'] <= max(th)) and (data['Temp'] >= min(th)):
                    twidget.set_status('WARNING', u'%.1f°C' % data['Temp'])
                else:
                    twidget.set_status('ERROR', u'%.1f°C' % data['Temp'])
                if data['Humidity'] < hs:
                    hwidget.set_status('OK', u'%.1f%%' % data['Humidity'])
                elif data['Humidity'] < hh:
                    hwidget.set_status('WARNING', u'%.1f%%' % data['Humidity'])
                else:
                    hwidget.set_status('ERROR', u'%.1f%%' % data['Humidity'])
                        
        return True
    def updatemonitor(self, pc=None):
        u = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        self['mem'].set_status('OK', '%.2f MB' % (u / 1024))
        if not pc.connected():
            for l in self.statuslabels:
                if l != 'mem':
                    self[l] = 'UNKNOWN'
            return True
        try:
            self['camstate'] = self._controller.get_camstate()
            self['Done'].set_status('OK', '%.2f %%' % (self._controller.get_percentdone()))
            tl = self._controller.get_timeleft()
            self['Timeleft'].set_status('OK', '%02d:%02.0f' % (int(tl) / 60, int(tl) % 60))
        except pilatus.PilatusError:
            self['camstate'] = 'error'
            self['Done'].set_status('UNKNOWN')
            self['Timeleft'].set_status('UNKNOWN')
        return True
    def __setitem__(self, key, value):
        self.statuslabels[key].set_status(value)
    def __getitem__(self, key):
        return self.statuslabels[key]
    def start(self, pilatusconnection):
        if self.timeouthandler is None:
            self.updatemonitor(pilatusconnection)
            self.timeouthandler = gobject.timeout_add_seconds(self._monitor_timeout, self.updatemonitor, pilatusconnection)
        if self.timeouthandler_slow is None:
            self.timeouthandler_slow = gobject.timeout_add_seconds(self._slowmonitor_timeout, self.updatemonitor_slow, pilatusconnection)
        self.updatemonitor_slow(pilatusconnection)
    def stop(self):
        if self.timeouthandler is not None:
            gobject.source_remove(self.timeouthandler)
            self.timeouthandler = None
        if self.timeouthandler_slow is not None:
            gobject.source_remove(self.timeouthandler_slow)
            self.timeouthandler_slow = None
    def restart(self, pilatusconnection):
        self.stop()
        self.start(pilatusconnection)
        
def append_and_select_text_to_combo(combo, txt):
    if txt not in [x[0] for x in combo.get_model()]:
        combo.append_text(txt)
    idx = [x for x in range(len(combo.get_model())) if combo.get_model()[x][0] == txt][0]
    combo.set_active(idx)
    
    
class PilatusControl(gtk.Dialog):
    _gtk_quit_on_close = False
    _insensitive_on_exposure = None
    _exposure_start_data = None
    _filechooserdialogs = None
    _exposure_mode = False
    _lastplot2dwindow = None
    def __init__(self, credo, title='Control the Pilatus detector', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        vbox = self.get_content_area()
        self.statusmonitor = PilatusStatus(self)
        vbox.pack_start(self.statusmonitor, False)
        nb = gtk.Notebook()
        vbox.pack_start(nb)
        self.credo = credo
        self._insensitive_on_exposure = []
        setuppage = gtk.ScrolledWindow()
        setuppage.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        nb.append_page(setuppage, gtk.Label('Set-up detector'))
        
        commonparamspage = gtk.VBox()
        nb.append_page(commonparamspage, gtk.Label('Common parameters'))
        
        exposepage = gtk.VBox()
        nb.append_page(exposepage, gtk.Label('Exposure'))
        
        plotpage = gtk.ScrolledWindow()
        plotpage.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        nb.append_page(plotpage, gtk.Label('Display'))
        
        timedscanpage = gtk.ScrolledWindow()
        nb.append_page(timedscanpage, gtk.Label('Timed scan'))
        
        self.timeouthandler = None
        
        
        #-------------- commonparamspage -----------------------------------------
        
        vb = gtk.VBox()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        commonparamspage.add(vb)
        row = 0
        
        l = gtk.Label('Owner:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.ownerentry = gtk.combo_box_entry_new_text()
        tab.attach(self.ownerentry, 1, 2, row, row + 1)
        self.ownerentry.append_text('Wacha')
        self.ownerentry.set_active(0)
        self._insensitive_on_exposure.append(self.ownerentry)
        row += 1

        l = gtk.Label('Project:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.projectentry = gtk.combo_box_entry_new_text()
        tab.attach(self.projectentry, 1, 2, row, row + 1)
        self.projectentry.append_text('in-house')
        self.projectentry.set_active(0)
        self._insensitive_on_exposure.append(self.projectentry)
        row += 1
        
        l = gtk.Label(u'Wavelength (Å):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.wavelengthentry = gtk.SpinButton(gtk.Adjustment(1.542, 0, 300, 0.1, 1), digits=4)
        tab.attach(self.wavelengthentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.wavelengthentry)
        row += 1
        
        l = gtk.Label('Beam position (row coord.):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.beamposxentry = gtk.SpinButton(gtk.Adjustment(200, -1e8, 1e8, 0.1, 1), digits=3)
        tab.attach(self.beamposxentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.beamposxentry)
        row += 1
        
        l = gtk.Label('Beam position (col. coord.):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.beamposyentry = gtk.SpinButton(gtk.Adjustment(200, -1e8, 1e8, 0.1, 1), digits=3)
        tab.attach(self.beamposyentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.beamposyentry)
        row += 1
        
        l = gtk.Label('Pixel size (mm):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.pixsizeentry = gtk.SpinButton(gtk.Adjustment(0.172, 0, 100, 0.1, 1), digits=3)
        tab.attach(self.pixsizeentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.pixsizeentry)
        row += 1
        
        #-------------- exposepage -----------------------------------------

        vb = gtk.VBox()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        # exposepage.add_with_viewport(tab)
        exposepage.add(vb)
        row = 0

        
        l = gtk.Label('Sample name:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.samplenameentry = gtk.combo_box_entry_new_text()
        tab.attach(self.samplenameentry, 1, 2, row, row + 1)
        self.samplenameentry.append_text('Dummy')
        self.samplenameentry.set_active(0)
        self._insensitive_on_exposure.append(self.samplenameentry)
        row += 1
        
        l = gtk.Label('File sequence number:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fsnentry = gtk.SpinButton(gtk.Adjustment(1, 1, 1e8, 1, 10), digits=0)
        tab.attach(self.fsnentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.fsnentry)
        row += 1
        
        l = gtk.Label('Exposure time (sec):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.exptimeentry = gtk.SpinButton(gtk.Adjustment(60, 0.0001, 1e8, 1, 10), digits=2)
        tab.attach(self.exptimeentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.exptimeentry)
        row += 1
        
        l = gtk.Label(u'Temperature (°C):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.tempentry = gtk.SpinButton(gtk.Adjustment(25, -300, 1e8, 1, 10), digits=2)
        tab.attach(self.tempentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.tempentry)
        row += 1
        
        l = gtk.Label(u'Thickness (cm):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.thicknessentry = gtk.SpinButton(gtk.Adjustment(1, 0, 1e8, 1, 10), digits=5)
        tab.attach(self.thicknessentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.thicknessentry)
        row += 1
        
        l = gtk.Label('Sample-detector distance (mm):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.distentry = gtk.SpinButton(gtk.Adjustment(1000, 0, 1e6, 1, 10), digits=2)
        tab.attach(self.distentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.distentry)
        row += 1
        
        l = gtk.Label('Transmission:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.transmentry = gtk.SpinButton(gtk.Adjustment(0, 0, 1, 0.01, 0.1), digits=5)
        tab.attach(self.transmentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.transmentry)
        row += 1
        
        l = gtk.Label('Filter:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.filterentry = gtk.combo_box_entry_new_text()
        self.filterentry.append_text('None')
        self.filterentry.set_active(0)
        tab.attach(self.filterentry, 1, 2, row, row + 1)
        self._insensitive_on_exposure.append(self.filterentry)
        row += 1
        
        
        self.exposebutton = gtk.Button(stock=gtk.STOCK_EXECUTE)
        tab.attach(self.exposebutton, 0, 2, row, row + 1, gtk.FILL, gtk.FILL)
        self.exposebutton.connect('clicked', self.on_exposebutton)
        row += 1
        
        # ---------------- setuppage ---------------------------------------------
        
        vb = gtk.VBox()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        setuppage.add_with_viewport(vb)
        l = gtk.Label('Threshold (eV):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 0, 1, gtk.FILL, gtk.FILL)
        self.thresholdentry = gtk.SpinButton(gtk.Adjustment(4024, 4000, 18000, 100, 1000), digits=0)
        tab.attach(self.thresholdentry, 1, 2, 0, 1)
        self._insensitive_on_exposure.append(self.thresholdentry)

        l = gtk.Label('Gain:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 1, 2, gtk.FILL, gtk.FILL)
        self.gainselector = gtk.combo_box_new_text()
        self.gainselector.append_text('lowG')
        self.gainselector.append_text('midG')
        self.gainselector.append_text('highG')
        self.gainselector.set_active(0)
        tab.attach(self.gainselector, 1, 2, 1, 2)
        self._insensitive_on_exposure.append(self.gainselector)
        
        b = gtk.Button('Trim\ndetector')
        tab.attach(b, 2, 3, 0, 2, gtk.FILL, gtk.FILL)
        b.connect('clicked', self.on_trim)
        self._insensitive_on_exposure.append(b)
        
        l = gtk.Label('Filename prefix:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 2, 3, gtk.FILL, gtk.FILL)
        self.filetemplateentry = gtk.Entry()
        self.filetemplateentry.set_text('crd_')
        tab.attach(self.filetemplateentry, 1, 3, 2, 3)
        self._insensitive_on_exposure.append(self.filetemplateentry)

        l = gtk.Label('Digits in FSN:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 3, 4, gtk.FILL, gtk.FILL)
        self.digitsentry = gtk.SpinButton(gtk.Adjustment(5, 3, 100, 1, 10), digits=0)
        tab.attach(self.digitsentry, 1, 3, 3, 4)
        self._insensitive_on_exposure.append(self.digitsentry)
        
        bb = gtk.HButtonBox()
        tab.attach(bb, 0, 3, 4, 5, gtk.FILL, gtk.FILL)
        b = gtk.Button('Calibrate')
        b.connect('clicked', self.on_calibrate)
        self._insensitive_on_exposure.append(b)
        bb.add(b)
        b = gtk.Button('Read back detector')
        b.connect('clicked', self.on_rbd)
        self._insensitive_on_exposure.append(b)
        bb.add(b)
        
        # -------------------- plotpage ------------------------------------
        
        vb = gtk.VBox()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        plotpage.add_with_viewport(vb)
        self.plot2d = gtk.CheckButton('Display acquired image')
        self.plot2d.set_alignment(0, 0.5)
        self.plot2d.set_active(True)
        tab.attach(self.plot2d, 0, 2, 0, 1)
        self.plot2d_reuse = gtk.CheckButton('Re-use 2D window if exists')
        self.plot2d_reuse.set_alignment(0, 0.5)
        self.plot2d_reuse.set_active(True)
        tab.attach(self.plot2d_reuse, 0, 2, 1, 2)
        
        self.plot1d = gtk.CheckButton('Plot radial average')
        self.plot1d.set_alignment(0, 0.5)
        tab.attach(self.plot1d, 0, 2, 2, 3)

        # -------------------- timedscanpage
        
        vb = gtk.VBox()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        timedscanpage.add_with_viewport(vb)
        
        
        
        # --------------------------------------------------------------------------
        
        self.loadstate()
        
#        def _handler(arg, arg1):
#            gobject.idle_add(self.on_exposure_finished, arg)
#        self.credo.pilatus.register_event_handler('exposure_finished', _handler)
        
        def _handler(arg, arg1):
            gobject.idle_add(self.on_disconnect_from_camserver, arg)
        self.credo.pilatus.register_event_handler('disconnect_from_camserver', _handler)
        
        self.get_action_area().get_children()[0].connect('clicked', self.closewindow)
        self.startmonitor()
        self.load_comboentries()
        self.show_all()
    def is_exposure_mode(self):
        return self._exposure_mode
    def get_camstate(self):
        if self.is_exposure_mode():
            return 'exposing'
        elif self.credo.is_pilatus_connected():
            return self.credo.pilatus.camstate
        else:
            return 'disconnected'
    def get_exptime(self):
        # self._exposure_start_data = {'FSN':fsn, 'StartTime0':t0, 'StartTime1':t1, 'ExpTime':exptime, 'ExpFilename':filename, 'StartDate':starttime}
        
        if self.is_exposure_mode():
            return self._exposure_start_data['ExpTime']
        elif self.credo.is_pilatus_connected():
            return self.credo.pilatus.exptime
        else:
            return None
    def get_timeleft(self):
        if self.is_exposure_mode():
            return self._exposure_start_data['ExpTime'] - (time.time() - 0.5 * (self._exposure_start_data['StartTime1'] + self._exposure_start_data['StartTime0']))
        elif self.credo.is_pilatus_connected():
            return self.credo.pilatus.timeleft
        else:
            return None
    def get_percentdone(self):
        if self.is_exposure_mode():
            return (1 - self.get_timeleft() / self.get_exptime()) * 100.
        elif self.credo.is_pilatus_connected():
            return self.credo.pilatus.percentdone
        else:
            return None
    def load_comboentries(self):
        return
        logger.debug('Loading combobox entries.')
        filebegin = self.filetemplateentry.get_text()
        folder = self.credo.parampath
        files = glob.glob(os.path.join(folder, filebegin + '*.param'))
        def loadheader(name):
            try:
                return sastool.classes.SASHeader(name)
            except:
                return None
        headers = [x for x in [loadheader(f) for f in files] if x is not None]
        for headerfield, combo in zip(['Project', 'Title', 'Owner', 'Filter'], [self.projectentry, self.samplenameentry, self.ownerentry, self.filterentry]):
            def getitem_safe(d, name):
                try:
                    return d[name]
                except KeyError:
                    return None
            possibilities = sorted(set([x for x in [getitem_safe(h, headerfield) for h in headers] if x is not None]))
            active = combo.get_active_text()
            combo.get_model().clear()
            for p, i in zip(possibilities, itertools.count(0)):
                combo.get_model().append((p,))
                if p == active:
                    combo.set_active(i)
    def on_calibrate(self, button):
        logger.info('Starting calibration')
        self.credo.pilatus.calibrate()
    def on_rbd(self, button):
        logger.info('Starting read-back-detector')
        self.credo.pilatus.rbd()
    def on_trim(self, button):
        logger.info('Trimming detector')
        threshold = self.thresholdentry.get_value_as_int()
        gain = self.gainselector.get_active_text()
        self.credo.pilatus.setthreshold(threshold, gain)
    def _exposethread(self):
        self.credo
    def on_exposure_finished(self, arg, broken=False):
        logger.info('Exposure finished')
        t = time.time()
        for w in self._insensitive_on_exposure:
            w.set_sensitive(True)
        self.exposebutton.set_label(gtk.STOCK_EXECUTE)
        if arg is None or broken:
            logger.info('User break in exposure')
            return
        if '/' in arg:
            filename = os.path.split(arg)[1]
        else:
            filename = arg
        headername = os.path.join(self.credo.parampath, filename.replace('.cbf', '.param'))
        logger.info('Writing header to ' + headername)
        h.write(headername)
        self.fsnentry.set_value(self.fsnentry.get_value_as_int() + 1)
        logger.debug('Leaving exposure mode')
        self._exposure_mode = False
        self.load_comboentries()
        if self.plot2d.get_active():
            if (self._lastplot2dwindow is None or not self._lastplot2dwindow.get_visible()) or not self.plot2d_reuse.get_active():
                w = gtk.Dialog(title=filename, parent=self, flags=gtk.DIALOG_DESTROY_WITH_PARENT)
                self._lastplot2dwindow = sasgui.plot2dsasimage.PlotSASImage()
                w.get_content_area().pack_start(self._lastplot2dwindow)
                w.show_all()
            time.sleep(2)
            try:
                self._lastplot2dwindow.exposure = sastool.SASExposure(filename, dirs=(self.credo.parampath, self.credo.imagepath, self.credo.offlineimagepath))
            except IOError, ioe:
                logger.error('Cannot open exposure file ' + filename + ". Message: " + ioe.message)
        return False  # this is needed since we are called as a pygtk idle function.
    def on_exposebutton(self, widget):
        if not self.credo.pilatus.connected():
            return True
        if widget.get_label() == gtk.STOCK_EXECUTE:
            exptime = self.exptimeentry.get_value()
            fsn = self.fsnentry.get_value_as_int()
            digits = self.digitsentry.get_value_as_int()
            formatstring = '%' + '0' + '%d' % digits + 'd'
            filename = fileprefix + (formatstring % fsn) + '.cbf'
            t0 = time.time()
            logger.info('Starting %f seconds exposure to file %s' % (exptime, filename))
            expstartdata = self.pilatusconnection.expose(exptime, filename)
            t1 = time.time()
            self._exposure_start_data = {'FSN':fsn, 'StartTime':0.5 * (t0 + t1), 'ExpTime':exptime, 'ExpFilename':filename, 'StartDate':dateutil.parser.parse(expstartdata['expdatetime'])}
            logger.debug('Entering exposure mode')
            self._exposure_mode = True
            widget.set_label(gtk.STOCK_STOP)
            for w in self._insensitive_on_exposure:
                w.set_sensitive(False)
            return True
        else:
            logger.info('Breaking current exposure.')
            self.on_exposure_finished(self.pilatusconnection.stopexposure(), broken=True)
            widget.set_label(gtk.STOCK_EXECUTE)
            return True

    def restartmonitor(self):
        self.statusmonitor.restart(self.credo.pilatus)
    def startmonitor(self):
        self.statusmonitor.start(self.credo.pilatus)
    def stopmonitor(self):
        self.statusmonitor.stop()
    def closewindow(self, *args, **kwargs):
        self.stopmonitor()
        self.disconnect_pilatus()
        self.hide_all()
        if self._gtk_quit_on_close:
            gtk.main_quit()
        self.savestate()
        return True
    def savestate(self, filename='~/.saxsctrlrc'):
        return
        filename = os.path.expanduser(filename)
        cp = ConfigParser.ConfigParser()
        cp.add_section('PilatusControl')
        # cp.set('PilatusControl', 'Host', self.hostnameentry.get_text())
        cp.add_section('Exposure')
        # cp.set('Exposure', 'FSN', self.fsnentry.get_value_as_int())
        # cp.set('Exposure', 'ExpTime', self.exptimeentry.get_value())
        # cp.set('Exposure', 'Title', self.samplenameentry.get_active_text())
        # cp.set('Exposure', 'Owner', self.ownerentry.get_active_text())
        # cp.set('Exposure', 'Project', self.projectentry.get_active_text())
        # cp.set('Exposure', 'Wavelength', self.wavelengthentry.get_value())
        # cp.set('Exposure', 'Dist', self.distentry.get_value())
        # cp.set('Exposure', 'PixelSize', self.pixsizeentry.get_value())
        # cp.set('Exposure', 'BeamPosX', self.beamposxentry.get_value())
        # cp.set('Exposure', 'BeamPosY', self.beamposyentry.get_value())
        # cp.set('Exposure', 'Transmission', self.transmentry.get_value())
        # cp.set('Exposure', 'Filter', self.filterentry.get_active_text())
        # cp.set('Exposure', 'Temperature', self.tempentry.get_value())
        # cp.set('Exposure', 'Thickness', self.thicknessentry.get_value())
        cp.add_section('DetectorSetup')
        # cp.set('DetectorSetup', 'ImgPath', self.imgpathentry.get_text())
        # cp.set('DetectorSetup', 'FilePath', self.filepathentry.get_text())
        # cp.set('DetectorSetup', 'Digits', self.digitsentry.get_value_as_int())
        # cp.set('DetectorSetup', 'FilePrefix', self.filetemplateentry.get_text())
        # cp.set('DetectorSetup', 'Threshold', self.thresholdentry.get_value_as_int())
        # cp.set('DetectorSetup', 'Gain', self.gainselector.get_active_text())
        with open(filename, 'wt') as f:
            cp.write(f)
        logger.info('State saved to file: ' + filename)
    def loadstate(self, filename='~/.saxsctrlrc'):
        return
        filename = os.path.expanduser(filename)
        if not os.path.exists(filename):
            return
        logger.info('Loading state from file: ' + filename)
        cp = ConfigParser.ConfigParser()
        cp.read(filename)
        if cp.has_option('PilatusControl', 'Host'):
            self.hostnameentry.set_text(cp.get('PilatusControl', 'Host'))
        if cp.has_option('DetectorSetup', 'FilePrefix'):
            self.filetemplateentry.set_text(cp.get('DetectorSetup', 'FilePrefix'))
        if cp.has_option('Exposure', 'FSN'):
            self.fsnentry.set_value(cp.getint('Exposure', 'FSN'))
        if cp.has_option('DetectorSetup', 'Digits'):
            self.digitsentry.set_value(cp.getint('DetectorSetup', 'Digits'))
        if cp.has_option('Exposure', 'ExpTime'):
            self.exptimeentry.set_value(cp.getfloat('Exposure', 'ExpTime'))
        if cp.has_option('DetectorSetup', 'ImgPath'):
            self.imgpathentry.set_text(cp.get('DetectorSetup', 'ImgPath'))
        if cp.has_option('DetectorSetup', 'Threshold'):
            self.thresholdentry.set_value(cp.getint('DetectorSetup', 'Threshold'))
        if cp.has_option('DetectorSetup', 'Gain'):
            activetext = cp.get('DetectorSetup', 'Gain')
            # find the number of the gain setting in self.gainselector
            try:
                idx = [i for i in range(len(self.gainselector.get_model())) if self.gainselector.get_model()[i][0] == activetext][0]
            except IndexError:
                pass
            else: 
                self.gainselector.set_active(idx)
        if cp.has_option('DetectorSetup', 'FilePath'):
            self.filepathentry.set_text(cp.get('DetectorSetup', 'FilePath'))
        if cp.has_option('Exposure', 'Title'):
            append_and_select_text_to_combo(self.samplenameentry, cp.get('Exposure', 'Title'))
        if cp.has_option('Exposure', 'Owner'):
            append_and_select_text_to_combo(self.ownerentry, cp.get('Exposure', 'Owner'))
        if cp.has_option('Exposure', 'Project'):
            append_and_select_text_to_combo(self.projectentry, cp.get('Exposure', 'Project'))
        if cp.has_option('Exposure', 'Wavelength'):
            self.wavelengthentry.set_value(cp.getfloat('Exposure', 'Wavelength'))
        if cp.has_option('Exposure', 'Dist'):
            self.distentry.set_value(cp.getfloat('Exposure', 'Dist'))
        if cp.has_option('Exposure', 'PixelSize'):
            self.pixsizeentry.set_value(cp.getfloat('Exposure', 'PixelSize'))
        if cp.has_option('Exposure', 'BeamPosX'):
            self.beamposxentry.set_value(cp.getfloat('Exposure', 'BeamPosX'))
        if cp.has_option('Exposure', 'BeamPosY'):
            self.beamposyentry.set_value(cp.getfloat('Exposure', 'BeamPosY'))
        if cp.has_option('Exposure', 'Transmission'):
            self.transmentry.set_value(cp.getfloat('Exposure', 'Transmission'))
        if cp.has_option('Exposure', 'Filter'):
            append_and_select_text_to_combo(self.filterentry, cp.get('Exposure', 'Filter'))
        if cp.has_option('Exposure', 'Temperature'):
            self.tempentry.set_value(cp.getfloat('Exposure', 'Temperature'))
        if cp.has_option('Exposure', 'Thickness'):
            self.thicknessentry.set_value(cp.getfloat('Exposure', 'Thickness'))
        
if __name__ == '__main__':
    import sys
    win = PilatusControl()
    win.show_all()
    try:
        __IPYTHON__
    except NameError:
        win._gtk_quit_on_close = True
        gtk.main()
