from gi.repository import Gtk
from gi.repository import Pango
import matplotlib.pyplot as plt
import sasgui
from gi.repository import GObject
import numpy as np
import gc
from ..hardware import sample, virtualpointdetector, credo
from .spec_filechoosers import MaskChooserDialog
from .widgets import ToolDialog
import sastool
import scangraph
import os
import logging
import datetime
import re
import multiprocessing
import sys
from .scan import ScanDeviceSelector

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ImagingDeviceSelector(Gtk.ComboBoxText):
    def __init__(self, credo, number=1):
        Gtk.ComboBoxText.__init__(self)
        self.credo = credo
        self.number = number
        self._fromcredo()
    def _fromcredo(self):
        model = self.get_model().clear()
        for i, sd in enumerate(self.credo.subsystems['Imaging'].get_supported_devices()):
            self.append_text(sd)
            if self.credo.subsystems['Imaging'].get_property('devicename%d' % self.number) == sd:
                self.set_active(i)
    def _tocredo(self):
        self.credo.subsystems['Imaging'].set_property('devicename%d' % self.number, self.get_active_text())
    def get(self):
        return self.get_active_text()
    def set(self, devname):
        self.credo.subsystems['Imaging'].set_property('devicename%d' % self.number, devname)
        for i, row in enumerate(self.get_model()):
            if row[0] == devname:
                self.set_active(i)
                return
        raise NotImplementedError('Cannot set active device.')


class Imaging(ToolDialog):
    __gsignals__ = {'response':'override'}
    def __init__(self, credo, title='Imaging'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self.set_default_response(Gtk.ResponseType.OK)
        vb = self.get_content_area()
        self.entrytable = Gtk.Table()
        vb.pack_start(self.entrytable, False, True, 0)
        self.set_resizable(False)
        row = 0
        
        l = Gtk.Label(label='Scan device #1:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 1, 2, row, row + 1, Gtk.AttachOptions.FILL)
        self.scandevice1_selector = ImagingDeviceSelector(self.credo, 1)
        self.entrytable.attach(self.scandevice1_selector, 1, 2, row + 1, row + 2)
        l = Gtk.Label(label='Scan device #2:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 2, 3, row, row + 1, Gtk.AttachOptions.FILL)
        self.scandevice2_selector = ImagingDeviceSelector(self.credo, 2)
        self.entrytable.attach(self.scandevice2_selector, 2, 3, row + 1, row + 2)
        row += 2

        l = Gtk.Label(label='Start:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.start1_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Imaging'].value_begin1, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.start1_entry, 1, 2, row, row + 1)
        self.start1_entry.set_value(self.credo.subsystems['Imaging'].value_begin1)
        self.start1_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        self.start2_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Imaging'].value_begin2, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.start2_entry, 2, 3, row, row + 1)
        self.start2_entry.set_value(self.credo.subsystems['Imaging'].value_begin2)
        self.start2_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        row += 1

        l = Gtk.Label(label='End:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.end1_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Imaging'].value_end1, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.end1_entry, 1, 2, row, row + 1)
        self.end1_entry.set_value(self.credo.subsystems['Imaging'].value_end1)
        self.end1_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        self.end2_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Imaging'].value_end2, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.end2_entry, 2, 3, row, row + 1)
        self.end2_entry.set_value(self.credo.subsystems['Imaging'].value_end2)
        self.end2_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        row += 1

        l = Gtk.Label(label='Number of steps:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.step1_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Imaging'].nstep1, 2, 1e9, 1, 10), digits=0)
        self.entrytable.attach(self.step1_entry, 1, 2, row, row + 1)
        self.step1_entry.set_value(self.credo.subsystems['Imaging'].nstep1)
        self.step1_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        self.step2_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Imaging'].nstep2, 2, 1e9, 1, 10), digits=0)
        self.entrytable.attach(self.step2_entry, 2, 3, row, row + 1)
        self.step2_entry.set_value(self.credo.subsystems['Imaging'].nstep2)
        self.step2_entry.connect('value-changed', lambda sb: self._recalculate_stepsize())
        row += 1


        l = Gtk.Label(label='Step size:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.stepsize1_label = Gtk.Label('--'); self.stepsize1_label.set_alignment(0, 0.5)
        self.entrytable.attach(self.stepsize1_label, 1, 2, row, row + 1, xpadding=3)
        self.stepsize2_label = Gtk.Label('--'); self.stepsize2_label.set_alignment(0, 0.5)
        self.entrytable.attach(self.stepsize2_label, 2, 3, row, row + 1, xpadding=3)
        row += 1
        
        l = Gtk.Label(label='Comment:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.samplename_entry = Gtk.Entry()
        self.samplename_entry.set_text(self.credo.subsystems['Imaging'].comment)
        self.entrytable.attach(self.samplename_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Counting time (s):'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Imaging'].countingtime, 0, 100, 0.1, 1), digits=4)
        self.exptime_entry.set_value(self.credo.subsystems['Imaging'].countingtime)
        self.entrytable.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1


        l = Gtk.Label(label='Delay between exposures (s):'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.dwelltime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.credo.subsystems['Imaging'].waittime, 0.003, 10000, 1, 10), digits=4)
        self.dwelltime_entry.set_value(self.credo.subsystems['Imaging'].waittime)
        self.entrytable.attach(self.dwelltime_entry, 1, 2, row, row + 1)
        row += 1
        
        self.shutter_checkbutton = Gtk.CheckButton('Open/close shutter on each exposure (SLOW!)')
        self.shutter_checkbutton.set_alignment(0, 0.5)
        self.entrytable.attach(self.shutter_checkbutton, 0, 2, row, row + 1)
        self.shutter_checkbutton.set_active(self.credo.subsystems['Imaging'].operate_shutter)
        row += 1
        
        self.autoreturn_checkbutton = Gtk.CheckButton('Auto-return to start at end')
        self.autoreturn_checkbutton.set_alignment(0, 0.5)
        self.entrytable.attach(self.autoreturn_checkbutton, 0, 2, row, row + 1)
        self.autoreturn_checkbutton.set_active(self.credo.subsystems['Imaging'].autoreturn)
        row += 1
        
        l = Gtk.Label(label='Iterations:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self.repetitions_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 1, 100000, 1, 10), digits=0)
        self.repetitions_entry.set_value(1)
        self.entrytable.attach(self.repetitions_entry, 1, 2, row, row + 1)
        row += 1
        
        self.lazystop_button = Gtk.ToggleButton(label="Stop after current run")
        self.lazystop_button.connect('toggled', self.on_lazystop)
        self.lazystop_button.set_sensitive(False)
        self.get_action_area().pack_start(self.lazystop_button, False, False, 0)
        
        self._recalculate_stepsize()
        vb.show_all()
    def _recalculate_stepsize(self):
        self.stepsize1_label.set_label(str((self.end1_entry.get_value() - self.start1_entry.get_value()) / (self.step1_entry.get_value_as_int() - 1)))
        self.stepsize2_label.set_label(str((self.end2_entry.get_value() - self.start2_entry.get_value()) / (self.step2_entry.get_value_as_int() - 1)))
        
    def on_lazystop(self, button):
        if self.lazystop_button.get_active():
            self.lazystop_button.set_label('Will stop...')
        else:
            self.lazystop_button.set_label('Stop after current run')
    
    def start_imaging(self):
        if self.repetitions_entry.get_value_as_int() == 0:
            return
        self.credo.subsystems['Samples'].set(None)
        self.credo.subsystems['Imaging'].countingtime = self.exptime_entry.get_value()
        self.credo.subsystems['Imaging'].waittime = self.dwelltime_entry.get_value()
        self.credo.subsystems['Imaging'].value_begin1 = self.start1_entry.get_value()
        self.credo.subsystems['Imaging'].value_begin2 = self.start2_entry.get_value()
        self.credo.subsystems['Imaging'].value_end1 = self.end1_entry.get_value()
        self.credo.subsystems['Imaging'].value_end2 = self.end2_entry.get_value()
        self.credo.subsystems['Imaging'].nstep1 = self.step1_entry.get_value_as_int()
        self.credo.subsystems['Imaging'].nstep2 = self.step2_entry.get_value_as_int()
        self.credo.subsystems['Imaging'].devicename1 = self.scandevice1_selector.get()
        self.credo.subsystems['Imaging'].devicename2 = self.scandevice2_selector.get()
        self.credo.subsystems['Imaging'].comment = self.samplename_entry.get_text()
        self.credo.subsystems['Imaging'].autoreturn = self.autoreturn_checkbutton.get_active()
        self._scanconnections = [self.credo.subsystems['Imaging'].connect('imaging-end', self._imaging_end),
                                 self.credo.subsystems['Imaging'].connect('imaging-report', self._imaging_report),
                                 self.credo.subsystems['Imaging'].connect('imaging-fail', self._imaging_fail)]
        self.credo.subsystems['Imaging'].prepare()
        self._scangraph = scangraph.ImagingGraph(self.credo.subsystems['Imaging'].currentscan, 'Imaging #%d' % (self.credo.subsystems['Imaging'].currentscan.fsn),
                                                 extent=[self.start1_entry.get_value(), self.end1_entry.get_value(), self.start2_entry.get_value(), self.end2_entry.get_value()])
        self._scangraph.figtext(1, 0, self.credo.username + '@' + 'CREDO  ' + str(datetime.datetime.now()), ha='right', va='bottom')
        self._scangraph.show_all()
        self._scangraph.set_scalers([(vd.name, vd.visible, 'Linear', vd.scaler) for vd in self.credo.subsystems['VirtualDetectors']])
        self.credo.subsystems['Imaging'].start()
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
                self.credo.subsystems['Imaging'].kill()
            elif self.get_widget_for_response(respid).get_label() == Gtk.STOCK_EXECUTE:
                self.start_imaging()
            else:
                raise NotImplementedError
    def _imaging_end(self, subsys, state):
        logger.debug('last imaging point received.')
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
            logger.info('Re-starting imaging: %d repetitions left' % (self.repetitions_entry.get_value_as_int()))
            GObject.idle_add(lambda: self.start_imaging() and False)
        else:
            logger.info('Imaging ended, no repetitions requested.')
            self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_EXECUTE)
            self.set_response_sensitive(Gtk.ResponseType.OK, True)
            self.lazystop_button.set_sensitive(False)
            self.entrytable.set_sensitive(True)
        return True
    def _imaging_report(self, subsys, scan):
        self._scangraph.redraw_scan()
    def _imaging_fail(self, subsys, mesg):
        md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Imaging failure')
        md.format_secondary_text(mesg)
        md.run()
        md.destroy()
        del md

