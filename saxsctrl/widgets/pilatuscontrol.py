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
        tab = gtk.Table()
        tab_colnum = 6
        sw.add_with_viewport(tab)
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
        sw.set_size_request(700, -1)        
        self.statuslabels = collections.OrderedDict()
        self.statuslabels['t0'] = StatusLabel('P.board temp.')
        self.statuslabels['h0'] = StatusLabel('P.board hum.')
        self.statuslabels['t1'] = StatusLabel('Baseplate temp.')
        self.statuslabels['h1'] = StatusLabel('Baseplate hum.')
        self.statuslabels['t2'] = StatusLabel('Det.head temp.')
        self.statuslabels['h2'] = StatusLabel('Det.head hum.')
        self.statuslabels['camstate'] = StatusLabel('State', {'exposing':'exposing',
                                                              'idle':'idle',
                                                              'error':'error',
                                                              'UNKNOWN':'offline',
                                                              'reading':'reading',
                                                              'preparing':'preparing',
                                                              'waiting':'waiting'},
                                         {'exposing':gtk.gdk.color_parse('turquoise'),
                                          'idle':gtk.gdk.color_parse('green'),
                                          'error':gtk.gdk.color_parse('red'),
                                          'UNKNOWN':gtk.gdk.color_parse('lightgray'),
                                          'reading':gtk.gdk.color_parse('pink'),
                                          'preparing':gtk.gdk.color_parse('magenta'),
                                          'waiting':gtk.gdk.color_parse('yellow')}, 'UNKNOWN')
        self.statuslabels['Timeleft'] = StatusLabel('Time left', {'OK':'OK', 'UNKNOWN':'UNKNOWN'}, {'OK':gtk.gdk.color_parse('white'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')}, 'UNKNOWN')
        self.statuslabels['Done'] = StatusLabel('Done %', {'OK':'OK', 'UNKNOWN':'UNKNOWN'}, {'OK':gtk.gdk.color_parse('white'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')}, 'UNKNOWN')
        self.statuslabels['Threshold'] = StatusLabel('Threshold', {'OK':'OK', 'UNKNOWN':'UNKNOWN'}, {'OK':gtk.gdk.color_parse('white'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')}, 'UNKNOWN')
        self.statuslabels['Gain'] = StatusLabel('Gain', {'OK':'OK', 'UNKNOWN':'UNKNOWN'}, {'OK':gtk.gdk.color_parse('white'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')}, 'UNKNOWN')
        self.statuslabels['Tau'] = StatusLabel('Tau', {'OK':'N/A', 'UNKNOWN':'UNKNOWN'}, {'OK':gtk.gdk.color_parse('white'), 'UNKNOWN':gtk.gdk.color_parse('lightgray')})
        for i, l in enumerate(self.statuslabels.itervalues()):
            tab.attach(l, i % tab_colnum, i % tab_colnum + 1, i / tab_colnum, i / tab_colnum + 1, gtk.FILL | gtk.EXPAND, gtk.FILL | gtk.EXPAND, 2, 3)

        self.show_all()
        for l in self.statuslabels.values():
            l.connect('status-changed', self.on_status_changed_logger)
    def on_status_changed_logger(self, statlabel, status, statstr, color):
        if status.upper() == 'ERROR' and statlabel.labelname not in ['Shutter', 'Remote', 'X-rays', 'Status']:
            logger.error(statlabel.labelname + '; message: ' + statstr)
        elif status.upper() == 'WARNING':
            logger.warning(statlabel.labelname + '; message: ' + statstr)
        else:
            logger.debug('Status changed: ' + statlabel.labelname + ', new status: ' + status + ', message: ' + statstr)
        return False
    def updatemonitor_slow(self, pc=None):
        if pc is None or not pc.connected():
            for l in self.statuslabels:
                if l != 'mem':
                    self[l] = 'UNKNOWN'
            return True
        try:
            taudata = pc.tau
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
            self['Tau'].set_status('OK', '%.1f ns' % (taudata['tau'] * 1e9))
        try:
            thresholddata = pc.getthreshold()
        except pilatus.PilatusError:
            for widgetname in ('Threshold', 'Gain'):
                self.__getitem__(widgetname).set_status('UNKNOWN')
        else:
            self['Threshold'].set_status('OK', '%d eV' % thresholddata['threshold'])
            self['Gain'].set_status('OK', '%s (vcmp=%.3f V)' % (thresholddata['gain'], thresholddata['vcmp']))
        return True
    def updatemonitor(self, pc=None):
        # u = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss + resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        # self['mem'].set_status('OK', '%.2f MB' % (u / 1024))
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
    def __init__(self, credo, title='Control the Pilatus detector', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE, gtk.STOCK_REFRESH, gtk.RESPONSE_APPLY)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        vbox = self.get_content_area()
        self.statusmonitor = PilatusStatus(self)
        vbox.pack_start(self.statusmonitor, False)
        self.credo = credo
        
        tab = gtk.Table()
        vbox.pack_start(tab, False)

        row = 0
        l = gtk.Label('Threshold (eV):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.thresholdentry = gtk.SpinButton(gtk.Adjustment(4024, 4000, 18000, 100, 1000), digits=0)
        tab.attach(self.thresholdentry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Gain:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.gainselector = gtk.combo_box_new_text()
        self.gainselector.append_text('lowG')
        self.gainselector.append_text('midG')
        self.gainselector.append_text('highG')
        self.gainselector.set_active(0)
        tab.attach(self.gainselector, 1, 2, row, row + 1)
        row += 1

        b = gtk.Button('Trim\ndetector')
        tab.attach(b, 2, 3, 0, row, gtk.FILL, gtk.FILL)
        b.connect('clicked', self.on_trim)
        
        l = gtk.Label('Tau:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.tau_entry = gtk.SpinButton(gtk.Adjustment(0, 0, 1000, 1, 10), digits=2)
        tab.attach(self.tau_entry, 1, 2, row, row + 1)
        b = gtk.Button('Set')
        tab.attach(b, 2, 3, row, row + 1, gtk.FILL, gtk.FILL)
        b.connect('clicked', self.on_set_tau)
        row += 1
        
        bb = gtk.HButtonBox()
        tab.attach(bb, 0, 3, row, row + 1, gtk.FILL, gtk.FILL)
        b = gtk.Button('Calibrate')
        b.connect('clicked', self.on_calibrate)
        bb.add(b)
        b = gtk.Button('Read back detector')
        b.connect('clicked', self.on_rbd)
        bb.add(b)
        
        # --------------------------------------------------------------------------
        
#        def _handler(arg, arg1):
#            gobject.idle_add(self.on_disconnect_from_camserver, arg)
#        self.credo.pilatus.register_event_handler('disconnect_from_camserver', _handler)
        
        self.connect('response', self.on_response)
        self.connect('focus-in-event', self.restartmonitor)
        self.startmonitor()
        self.credo.pilatus.getthreshold()
        self.show_all()
    def on_set_tau(self, *args):
        self.credo.pilatus.tau = self.tau_entry.get_value() * 1e-9
        self.statusmonitor.updatemonitor_slow(self.credo.pilatus)
    def on_response(self, dialog, respid):
        if respid in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            self.stopmonitor()
            self.hide()
        elif respid in (gtk.RESPONSE_APPLY,):
            self.statusmonitor.updatemonitor(self.credo.pilatus)
            self.statusmonitor.updatemonitor_slow(self.credo.pilatus)
        return True
    def get_camstate(self):
        if self.credo.is_pilatus_connected():
            return self.credo.pilatus.camstate
        else:
            return 'disconnected'
    def get_exptime(self):
        if self.credo.is_pilatus_connected():
            return self.credo.pilatus.exptime
        else:
            return None
    def get_timeleft(self):
        if self.credo.is_pilatus_connected():
            return self.credo.pilatus.timeleft
        else:
            return None
    def get_percentdone(self):
        if self.credo.is_pilatus_connected():
            return self.credo.pilatus.percentdone
        else:
            return None
    def on_calibrate(self, button):
        logger.info('Starting calibration')
        self.credo.pilatus.calibrate()
    def on_rbd(self, button):
        logger.info('Starting read-back-detector')
        self.credo.pilatus.rbd()
    def on_trim(self, button):
        threshold = self.thresholdentry.get_value_as_int()
        gain = self.gainselector.get_active_text()
        logger.info('Trimming detector: threshold is %.0f, gain is %s.' % (threshold, gain))
        self.credo.pilatus.setthreshold(threshold, gain)
        self.statusmonitor.updatemonitor_slow(self.credo.pilatus)
    def restartmonitor(self, *args):
        self.statusmonitor.restart(self.credo.pilatus)
    def startmonitor(self):
        self.statusmonitor.start(self.credo.pilatus)
    def stopmonitor(self):
        self.statusmonitor.stop()
        
