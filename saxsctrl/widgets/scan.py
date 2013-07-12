from gi.repository import Gtk
from gi.repository import Pango
import matplotlib.pyplot as plt
import sasgui
from gi.repository import GObject
import numpy as np
import gc
from ..hardware import sample, virtualpointdetector, credo
from .spec_filechoosers import MaskChooserDialog
from .widgets import ExposureInterface, ToolDialog
import sastool
import scangraph
import os
import logging
import datetime
import re
import multiprocessing
import sys

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ScanDeviceSelector(Gtk.ComboBoxText):
    def __init__(self, credo):
        Gtk.ComboBoxText.__init__(self)
        self.credo = credo
        self._fromcredo()
    def _fromcredo(self):
        model = self.get_model().clear()
        for i, sd in enumerate(self.credo.subsystems['Scan'].get_supported_devices()):
            self.append_text(sd)
            if self.credo.subsystems['Scan'].devicename == sd:
                self.set_active(i)
    def _tocredo(self):
        self.credo.subsystems['Scan'].devicename = self.get_active_text()
    def get(self):
        return self.get_active_text()
    def set(self, devname):
        self.credo.subsystems['Scan'].devicename = devname
        for i, row in enumerate(self.get_model()):
            if row[0] == devname:
                self.set_active(i)
                return
        raise NotImplementedError('Cannot set active device.')


class Scan(ToolDialog):
    __gsignals__ = {'response':'override'}
    def __init__(self, credo, title='Scan'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self.set_default_response(Gtk.ResponseType.OK)
        vb = self.get_content_area()
        self.entrytable = Gtk.Table()
        vb.pack_start(self.entrytable, False, True, 0)
        self.set_resizable(False)
        row = 0
        
        l = Gtk.Label(label='Scan device:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self.scandevice_selector = ScanDeviceSelector(self.credo)
        self.entrytable.attach(self.scandevice_selector, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Comment:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.samplename_entry = Gtk.Entry()
        self.samplename_entry.set_text(self.credo.subsystems['Scan'].comment)
        self.entrytable.attach(self.samplename_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Counting time (s):'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Scan'].countingtime, 0, 100, 0.1, 1), digits=4)
        self.entrytable.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Start:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.start_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Scan'].value_begin, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.start_entry, 1, 2, row, row + 1)
        self.start_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        row += 1

        l = Gtk.Label(label='Number of steps:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.step_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Scan'].nstep, 0, 1e9, 1, 10), digits=0)
        self.entrytable.attach(self.step_entry, 1, 2, row, row + 1)
        self.step_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        row += 1

        l = Gtk.Label(label='End:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.end_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Scan'].value_end, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.end_entry, 1, 2, row, row + 1)
        self.end_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        row += 1

        l = Gtk.Label(label='Step size:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.stepsize_label = Gtk.Label('--'); self.stepsize_label.set_alignment(0, 0.5)
        self.entrytable.attach(self.stepsize_label, 1, 2, row, row + 1, xpadding=3)
        row += 1

        l = Gtk.Label(label='Delay between exposures (s):'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.dwelltime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Scan'].waittime, 0.003, 10000, 1, 10), digits=4)
        self.entrytable.attach(self.dwelltime_entry, 1, 2, row, row + 1)
        row += 1
        
        self.shutter_checkbutton = Gtk.CheckButton('Open/close shutter on each exposure (SLOW!)')
        self.shutter_checkbutton.set_alignment(0, 0.5)
        self.entrytable.attach(self.shutter_checkbutton, 0, 2, row, row + 1)
        self.shutter_checkbutton.set_active(self.credo.subsystems['Scan'].operate_shutter)
        row += 1
        
        self.autoreturn_checkbutton = Gtk.CheckButton('Auto-return to start at end')
        self.autoreturn_checkbutton.set_alignment(0, 0.5)
        self.entrytable.attach(self.autoreturn_checkbutton, 0, 2, row, row + 1)
        self.autoreturn_checkbutton.set_active(self.credo.subsystems['Scan'].autoreturn)
        row += 1
        
        l = Gtk.Label(label='Iterations:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self.repetitions_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 1, 100000, 1, 10), digits=0)
        self.entrytable.attach(self.repetitions_entry, 1, 2, row, row + 1)
        row += 1
        
        self.lazystop_button = Gtk.ToggleButton(label="Stop after current run")
        self.lazystop_button.connect('toggled', self.on_lazystop)
        self.lazystop_button.set_sensitive(False)
        self.get_action_area().pack_start(self.lazystop_button, False, False, 0)
        
        self._recalculate_stepsize()
        vb.show_all()
    def _recalculate_stepsize(self):
        self.stepsize_label.set_label(str((self.end_entry.get_value() - self.start_entry.get_value()) / (self.step_entry.get_value_as_int() - 1)))
    def on_lazystop(self, button):
        if self.lazystop_button.get_active():
            self.lazystop_button.set_label('Will stop...')
        else:
            self.lazystop_button.set_label('Stop after current run')
    
    def start_scan(self):
        if self.repetitions_entry.get_value_as_int() == 0:
            return
        self.credo.subsystems['Samples'].set(None)
        self.credo.subsystems['Scan'].countingtime = self.exptime_entry.get_value()
        self.credo.subsystems['Scan'].waittime = self.dwelltime_entry.get_value()
        self.credo.subsystems['Scan'].value_begin = self.start_entry.get_value()
        self.credo.subsystems['Scan'].value_end = self.end_entry.get_value()
        self.credo.subsystems['Scan'].nstep = self.step_entry.get_value_as_int()
        self.credo.subsystems['Scan'].devicename = self.scandevice_selector.get()
        self.credo.subsystems['Scan'].comment = self.samplename_entry.get_text()
        self._scanconnections = [self.credo.subsystems['Scan'].connect('scan-end', self._scan_end),
                                 self.credo.subsystems['Scan'].connect('scan-report', self._scan_report),
                                 self.credo.subsystems['Scan'].connect('scan-fail', self._scan_fail)]
        self.credo.subsystems['Scan'].prepare()
        self._scangraph = scangraph.ScanGraph(self.credo.subsystems['Scan'].currentscan, 'Scan #%d' % (self.credo.subsystems['Scan'].currentscan.fsn))
        self._scangraph.figtext(1, 0, self.credo.username + '@' + 'CREDO  ' + str(datetime.datetime.now()), ha='right', va='bottom')
        self._scangraph.show_all()
        self._scangraph.set_scalers([(vd.name, vd.visible, vd.scaler) for vd in self.credo.subsystems['VirtualDetectors']])
        self.credo.subsystems['Scan'].start()
        self.entrytable.set_sensitive(False)
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_STOP)
        
        self.lazystop_button.set_sensitive(True)
        
    def do_response(self, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()
            return
        if respid == Gtk.ResponseType.OK:
            if self.get_widget_for_response(respid).get_label() == Gtk.STOCK_STOP:
                self.set_response_sensitive(respid, False)
                self.credo.subsystems['Scan'].kill()
            elif self.get_widget_for_response(respid).get_label() == Gtk.STOCK_EXECUTE:
                self.start_scan()
            else:
                raise NotImplementedError
    def _scan_end(self, subsys, state):
        logger.debug('last scan point received.')
        for c in self._scanconnections:
            subsys.disconnect(c)
        del self._scanconnections
        if self.lazystop_button.get_active():
            state = False
        if not state:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, 'User break!')
            md.run()
            md.destroy()
            del md
        if state and (self.repetitions_entry.get_value_as_int() > 1):  # should do one more run
            self.repetitions_entry.set_value(self.repetitions_entry.get_value_as_int() - 1)
            logger.info('Re-starting scan: %d repetitions left' % (self.repetitions_entry.get_value_as_int()))
            GObject.idle_add(lambda: self.start_scan() and False)
        else:
            logger.info('Scan ended, no repetitions requested.')
            self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_EXECUTE)
            self.set_response_sensitive(Gtk.ResponseType.OK, True)
            self.lazystop_button.set_sensitive(False)
            self.entrytable.set_sensitive(True)
        return True
    def _scan_report(self, subsys, scan):
        self._scangraph.redraw_scan()
    def _scan_fail(self, subsys, mesg):
        md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Scan failure')
        md.format_secondary_text(mesg)
        md.run()
        md.destroy()
        del md

