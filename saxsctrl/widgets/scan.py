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


class AddDetectorDialog(Gtk.Dialog):
    _filechooserdialogs = None
    def __init__(self, title='Add detector', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        vb = self.get_content_area()
        self.set_default_response(Gtk.ResponseType.OK)
        if isinstance(parent, Scan):
            self.credo = parent.credo
        else:
            self.credo = None
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        self.set_resizable(False)
        row = 0
        
        l = Gtk.Label(label='Detector name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_text('-- please fill --')
        tab.attach(self.name_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Detector type:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.type_entry = Gtk.ComboBoxText()
        self.type_entry.append_text('Exposure manipulation')
        self.type_entry.append_text('Epoch time')
        self.type_entry.append_text('GeniX recorder')
        self.type_entry.set_active(0)
        self.type_entry.connect('changed', lambda combo: self.on_type_entry_change())
        tab.attach(self.type_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Mask file:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.maskfile_entry = Gtk.Entry()
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab.attach(hb, 1, 2, row, row + 1)
        hb.pack_start(self.maskfile_entry, True, True, 0)
        self.maskfile_button = Gtk.Button(stock=Gtk.STOCK_OPEN)
        hb.pack_start(self.maskfile_button, False, False, 0)
        self.maskfile_button.connect('clicked', self.on_loadmaskbutton, self.maskfile_entry, Gtk.FileChooserAction.OPEN)
        row += 1

        l = Gtk.Label(label='Mode of operation:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.mode_entry = Gtk.ComboBoxText()
        self.mode_entry.append_text('max')
        self.mode_entry.append_text('min')
        self.mode_entry.append_text('sum')
        self.mode_entry.append_text('mean')
        self.mode_entry.append_text('barycenter_x')
        self.mode_entry.append_text('barycenter_y')
        self.mode_entry.append_text('sigma_x')
        self.mode_entry.append_text('sigma_y')
        self.mode_entry.append_text('sigma_tot')
        self.mode_entry.set_active(0)
        tab.attach(self.mode_entry, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='GeniX parameter:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self.genixpar_entry = Gtk.ComboBoxText()
        self.genixpar_entry.append_text('HT')
        self.genixpar_entry.append_text('Current')
        self.genixpar_entry.append_text('Status')
        self.genixpar_entry.append_text('Tubetime')
        self.genixpar_entry.set_active(0)
        tab.attach(self.genixpar_entry, 1, 2, row, row + 1)
        row += 1
        
        cb = Gtk.CheckButton(label='Scaling/visibility:'); cb.set_alignment(0, 0.5)
        tab.attach(cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self.scalerentry = Gtk.SpinButton()
        self.scalerentry.set_digits(2)
        self.scalerentry.set_increments(1, 10)
        self.scalerentry.set_value(1)
        self.scalerentry.set_range(-sys.float_info.max, sys.float_info.max)
        self.scalerentry.set_width_chars(40)
        tab.attach(self.scalerentry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL)
        cb.connect('toggled', self.on_scalercheckbutton)
        self.on_scalercheckbutton(cb)
        row += 1
        
        self.on_type_entry_change()
        vb.show_all()
    def on_scalercheckbutton(self, cb):
        if cb.get_active():
            cb.set_label('Scaling:')
            self.scalerentry.set_sensitive(True)
            self.scalerentry.set_value(1)
        else:
            cb.set_label('Invisible:')
            self.scalerentry.set_sensitive(False)
            self.scalerentry.set_text('Graph will not be drawn')
    def on_type_entry_change(self):
        if self.type_entry.get_active_text() == 'Exposure manipulation':
            self.maskfile_entry.set_sensitive(True)
            self.maskfile_button.set_sensitive(True)
            self.mode_entry.set_sensitive(True)
            self.genixpar_entry.set_sensitive(False)
        elif self.type_entry.get_active_text() == 'Epoch time':
            self.maskfile_entry.set_sensitive(False)
            self.maskfile_button.set_sensitive(False)
            self.mode_entry.set_sensitive(False)
            self.genixpar_entry.set_sensitive(False)
        elif self.type_entry.get_active_text() == 'GeniX recorder':
            self.maskfile_entry.set_sensitive(False)
            self.maskfile_button.set_sensitive(False)
            self.mode_entry.set_sensitive(False)
            self.genixpar_entry.set_sensitive(True)
    def on_loadmaskbutton(self, button, entry, action):
        if self._filechooserdialogs is None:
            self._filechooserdialogs = {}
        if entry not in self._filechooserdialogs:
            
            self._filechooserdialogs[entry] = MaskChooserDialog('Select mask file...', None, action, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
            if self.credo is not None:
                self._filechooserdialogs[entry].set_current_folder(self.credo.maskpath)
        if entry.get_text():
            self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == Gtk.ResponseType.OK:
            entry.set_text(self._filechooserdialogs[entry].get_filename())
        self._filechooserdialogs[entry].hide()
        return True
    def get_detector(self):
        if self.scalerentry.get_sensitive():
            scaler = self.scalerentry.get_value()
        else:
            scaler = None
        if self.type_entry.get_active_text() == 'Exposure manipulation':
            return virtualpointdetector.VirtualPointDetectorExposure(self.name_entry.get_text(), scaler, sastool.classes.SASMask(self.maskfile_entry.get_text()), self.mode_entry.get_active_text())
        elif self.type_entry.get_active_text() == 'Epoch time':
            return virtualpointdetector.VirtualPointDetectorEpoch(self.name_entry.get_text(), scaler)
        elif self.type_entry.get_active_text() == 'GeniX recorder':
            return virtualpointdetector.VirtualPointDetectorGenix(self.name_entry.get_text(), scaler, self.genixpar_entry.get_active_text())
        else:
            raise NotImplementedError

class ScanSetup(ToolDialog):
    _dlg = None
    def __init__(self, credo, title, parent=None, flags=0, buttons=(Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        ToolDialog.__init__(self, credo, title, parent, flags, buttons)
        vb = self.get_content_area()
        self.connect('response', self.on_response)
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        row = 0
        l = Gtk.Label('Scan device:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self.scandevice = Gtk.ComboBoxText()
        tab.attach(self.scandevice, 1, 2, row, row + 1)
        self.scandevice.connect('changed', lambda combo:self.set_response_sensitive(Gtk.ResponseType.APPLY, True))
        self.credo.connect('notify::scandevice', lambda crd, prop:self.refresh_scandevices())
        self.credo.connect('equipment-connection', lambda crd, name, state, obj:self.refresh_scandevices())
        row += 1
        self.refresh_scandevices()
        self.detectorsframe = Gtk.Frame(label='Detectors')
        vb.pack_start(self.detectorsframe, False, True, 0)
        hb = Gtk.HBox()
        self.detectorsframe.add(hb)
        self.detectors_liststore = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_PYOBJECT)
        
        self.detectors_treeview = Gtk.TreeView(self.detectors_liststore)
        self.detectors_treeview.set_headers_visible(True)
        self.detectors_treeview.set_rules_hint(True)
        self.detectors_treeview.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
        cellrenderer = Gtk.CellRendererText()
        self.detectors_treeview.append_column(Gtk.TreeViewColumn('Name', cellrenderer, text=0))
        cellrenderer = Gtk.CellRendererText()
        self.detectors_treeview.append_column(Gtk.TreeViewColumn('Scaling', cellrenderer, text=1))
        cellrenderer = Gtk.CellRendererText()
        self.detectors_treeview.append_column(Gtk.TreeViewColumn('Arguments', cellrenderer, text=2))
        self.detectors_treeview.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
        sw = Gtk.ScrolledWindow()
        hb.pack_start(sw, True, True, 0)
        sw.add(self.detectors_treeview)
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        vbb = Gtk.VButtonBox()
        hb.pack_start(vbb, False, True, 0)
        b = Gtk.Button(stock=Gtk.STOCK_ADD)
        b.connect('clicked', self.on_add_detector)
        vbb.add(b)
        b = Gtk.Button(stock=Gtk.STOCK_REMOVE)
        b.connect('clicked', self.on_remove_detector)
        vbb.add(b)
        b = Gtk.Button(stock=Gtk.STOCK_CLEAR)
        b.connect('clicked', self.on_clear_detectors)
        vbb.add(b)
        b = Gtk.Button(stock=Gtk.STOCK_SAVE)
        b.connect('clicked', self.on_save_detectors)
        vbb.add(b)
        b = Gtk.Button(stock=Gtk.STOCK_OPEN)
        b.connect('clicked', self.on_load_detectors)
        vbb.add(b)
        self.reload_vpds()
        vb.show_all()
        
    def on_add_detector(self, *args):
        if self._dlg is None:
            self._dlg = AddDetectorDialog(parent=self)
        ret = self._dlg.run()
        if ret == Gtk.ResponseType.OK:
            self.add_detector(self._dlg.get_detector())
        self._dlg.hide()
        return True
    def on_remove_detector(self, *args):
        model, iter = self.detectors_treeview.get_selection().get_selected()
        model.remove(iter)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, True)
        return True
    def on_clear_detectors(self, *args):
        self.detectors_liststore.clear()
        self.set_response_sensitive(Gtk.ResponseType.APPLY, True)
        return True
    def on_save_detectors(self, *args):
        fsd = Gtk.FileChooserDialog('Save detector list to...', self, Gtk.FileChooserAction.SAVE, (Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        fsd.set_do_overwrite_confirmation(True)
        filt = Gtk.FileFilter()
        filt.set_name('All files')
        filt.add_pattern('*')
        fsd.add_filter(filt)
        filt = Gtk.FileFilter()
        filt.set_name('Virtual Detector Lists')
        filt.add_pattern('*.vpdl')
        fsd.add_filter(filt)
        fsd.set_filter(filt)
        fsd.set_current_folder(self.credo.configpath)
        fsd.set_current_name('untitled.vpdl')
        if self.credo.virtdetcfgfile:
            fsd.set_filename(self.credo.virtdetcfgfile)
        self.to_credo()
        if fsd.run() == Gtk.ResponseType.OK:
            self.credo.save_virtdetcfg(fsd.get_filename())
        fsd.destroy()
        del fsd
        return True
    def on_load_detectors(self, *args):
        fsd = Gtk.FileChooserDialog('Load detector list from...', self, Gtk.FileChooserAction.OPEN, (Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        filt = Gtk.FileFilter()
        filt.set_name('All files')
        filt.add_pattern('*')
        fsd.add_filter(filt)
        filt = Gtk.FileFilter()
        filt.set_name('Virtual Detector Lists')
        filt.add_pattern('*.vpdl')
        fsd.add_filter(filt)
        fsd.set_filter(filt)
        fsd.set_current_folder(self.credo.configpath)
        if fsd.run() == Gtk.ResponseType.OK:
            self.credo.load_virtdetcfg(fsd.get_filename(), clear=True)
            self.reload_vpds()
        fsd.destroy()
        del fsd
        return True
    def reload_vpds(self):
        self.detectors_liststore.clear()
        for vpd in self.credo.virtualpointdetectors:
            self.add_detector(vpd)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
    def add_detector(self, det):
        if det.scaler is None:
            scaling = 'no graph'
        else:
            scaling = str(det.scaler)
        if isinstance(det, virtualpointdetector.VirtualPointDetectorExposure):
            self.detectors_liststore.append((det.name, scaling, 'type: Exposure; mask: ' + det.mask.maskid + '; mode: ' + det.mode, det))
        elif isinstance(det, virtualpointdetector.VirtualPointDetectorEpoch):
            self.detectors_liststore.append((det.name, scaling, 'type: Epoch time', det))
        elif isinstance(det, virtualpointdetector.VirtualPointDetectorGenix):
            self.detectors_liststore.append((det.name, scaling, 'type: GeniX recorder; parameter: ' + det.genixparam, det))
        else:
            raise NotImplementedError
        self.set_response_sensitive(Gtk.ResponseType.APPLY, True)
    def refresh_scandevices(self):
        self.scandevice.get_model().clear()
        for i, mot in enumerate(self.credo.get_scandevices()):
            self.scandevice.append_text(str(mot))
            if str(self.credo.scandevice) == str(mot):
                idx = i
        self.scandevice.set_active(idx)
    def to_credo(self):
        if self.credo.virtualpointdetectors != [row[-1] for row in self.detectors_liststore]:
            self.credo.virtualpointdetectors = [row[-1] for row in self.detectors_liststore]
            self.credo.emit('virtualpointdetectors-changed')
        if self.credo.scandevice != self.scandevice.get_active_text():
            self.credo.scandevice = self.scandevice.get_active_text()
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
    def on_response(self, dlg, respid):
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            self.to_credo()
        if respid not in (Gtk.ResponseType.APPLY,):
            self.hide()
        return False
    
class Scan(Gtk.Dialog, ExposureInterface):
    def __init__(self, credo, title='Scan', parent=None, flags=0, buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        self.credo = credo
        vb = self.get_content_area()
        self.entrytable = Gtk.Table()
        vb.pack_start(self.entrytable, False, True, 0)
        self.set_resizable(False)
        row = 0
        
        l = Gtk.Label(label='Scan device:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self.scandevice_label = Gtk.Label(label=self.credo.scandevice); self.scandevice_label.set_alignment(0, 0.5)
        self.entrytable.attach(self.scandevice_label, 1, 2, row, row + 1)
        self.credo.connect('notify::scandevice', lambda crd, prop: self.update_scandevice())
        row += 1
        
        l = Gtk.Label(label='Sample name:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.samplename_entry = Gtk.Entry()
        self.samplename_entry.set_text('-- please fill --')
        self.entrytable.attach(self.samplename_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Counting time (s):'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 0, 100, 0.1, 1), digits=4)
        self.entrytable.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Number of exposures:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.nimages_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(10, 1, 10000, 1, 10), digits=0)
        self.entrytable.attach(self.nimages_entry, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Start:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.start_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.start_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Step:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.step_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.step_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='End:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.end_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e9, 1e9, 1, 10), digits=4)
        self.entrytable.attach(self.end_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Delay between exposures (s):'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.dwelltime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(2, 0.003, 10000, 1, 10), digits=4)
        self.entrytable.attach(self.dwelltime_entry, 1, 2, row, row + 1)
        row += 1
        
        self.shutter_checkbutton = Gtk.CheckButton('Open/close shutter on each exposure (SLOW!)')
        self.shutter_checkbutton.set_alignment(0, 0.5)
        self.entrytable.attach(self.shutter_checkbutton, 0, 2, row, row + 1)
        self.shutter_checkbutton.set_active(False)
        row += 1
        
        self.autoreturn_checkbutton = Gtk.CheckButton('Auto-return to start at end')
        self.autoreturn_checkbutton.set_alignment(0, 0.5)
        self.entrytable.attach(self.autoreturn_checkbutton, 0, 2, row, row + 1)
        self.autoreturn_checkbutton.set_active(True)
        row += 1
        
        l = Gtk.Label(label='Repetitions:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self.repetitions_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 0, 100000, 1, 10), digits=0)
        self.entrytable.attach(self.repetitions_entry, 1, 2, row, row + 1)
        row += 1
        
        self.update_scandevice()
        self.connect('response', self.on_response)
        
        self.lazystop_button = Gtk.Button(label="Stop after current run")
        self.lazystop_button.connect('clicked', self.on_lazystop)
        self.lazystop_button.set_sensitive(False)
        self.get_action_area().pack_start(self.lazystop_button, False, False, 0)
        
        vb.show_all()
    def on_lazystop(self, button):
        self.lazystop_button.set_sensitive(False)
    
    def update_scandevice(self):
        self.scandevice_label.set_label(self.credo.scandevice)
        if self.credo.scandevice == 'Time':
            self.nimages_entry.set_sensitive(True)
            self.start_entry.set_sensitive(False)
            self.end_entry.set_sensitive(False)
            self.step_entry.set_sensitive(False)
        else:
            self.nimages_entry.set_sensitive(False)
            self.start_entry.set_sensitive(True)
            self.end_entry.set_sensitive(True)
            self.step_entry.set_sensitive(True)
    def start_scan(self):
        if self.repetitions_entry.get_value_as_int() == 0:
            return
        self.credo.set_sample(sample.SAXSSample(self.samplename_entry.get_text()))
        fsn = self.credo.get_next_fsn(re.compile('scan_(\d+)'))
        self.credo.set_fileformat('scan')
        logger.debug('initializing scan graphs.')
        self.entrytable.set_sensitive(False)
        self._scanconnections = [self.credo.connect('scan-end', self.on_scan_end),
                                 self.credo.connect('scan-dataread', self.on_scan_dataread)]
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_STOP)
        try:
            if self.credo.scandevice == 'Time':
                scn = self.credo.scan(None, None, self.nimages_entry.get_value_as_int(),
                                      self.exptime_entry.get_value(),
                                      self.dwelltime_entry.get_value(),
                                      shutter=self.shutter_checkbutton.get_active(),
                                      autoreturn=self.autoreturn_checkbutton.get_active())
            else:
                scn = self.credo.scan(self.start_entry.get_value(),
                                      self.end_entry.get_value(),
                                      self.step_entry.get_value(),
                                      self.exptime_entry.get_value(),
                                      self.dwelltime_entry.get_value(),
                                      shutter=self.shutter_checkbutton.get_active(),
                                      autoreturn=self.autoreturn_checkbutton.get_active())
        except (credo.CredoError, ValueError) as ce:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, ce.message)
            md.run()
            md.destroy()
            del md
            self.on_scan_end(self.credo, None, False)
            return True
        self._scangraph = scangraph.ScanGraph(scn, 'Scan #%d' % (scn.fsn))
        self._scangraph.figtext(1, 0, self.credo.username + '@' + 'CREDO  ' + str(datetime.datetime.now()), ha='right', va='bottom')
        self._scangraph.show_all()
        self._scangraph.set_scalers([(vd.name, vd.scaler) for vd in self.credo.virtualpointdetectors])
        self.lazystop_button.set_sensitive(True)
        
    def on_response(self, dialog, respid):
        if respid != Gtk.ResponseType.OK:
            if self.entrytable.get_sensitive():
                self.credo.killscan()
            self.hide()
            return True
        if self.entrytable.get_sensitive():
            self.start_scan()
        else:
            self.credo.killscan()
        return True
    def on_scan_end(self, credo, scan, state):
        logger.debug('last scan point received.')
        self.entrytable.set_sensitive(True)
        for c in self._scanconnections:
            credo.disconnect(c)
        del self._scanconnections
        if not self.lazystop_button.get_sensitive():
            state = False
        if not state and scan is not None:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, 'User break!')
            md.run()
            md.destroy()
            del md
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_EXECUTE)
        self.lazystop_button.set_sensitive(False)
        if self.repetitions_entry.get_value_as_int() > 0:
            self.repetitions_entry.set_value(self.repetitions_entry.get_value_as_int() - 1)
            self.start_scan()
        return True
    def on_scan_dataread(self, credo, scan):
        self._scangraph.redraw_scan()
    

