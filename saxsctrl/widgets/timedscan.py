import gtk
import matplotlib.pyplot as plt
import sasgui
import gobject
import numpy as np
import gc
from ..hardware import sample
from .spec_filechoosers import MaskChooserDialog
import sastool
import scangraph
import os
import logging
import datetime

logger = logging.getLogger('timedscan')
# logger.setLevel(logging.DEBUG)

class VirtualPointDetector(object):
    def __init__(self, name, mask, mode='max'):
        """Define a virtual point detector, which analyzes a portion of a 2D scattering
        pattern and returns a single number.
        
        Inputs:
            mask: sastool.classes.SASMask
                this defines the portion to be analyzed.
            mode: 'max' or 'min' or 'mean' or 'sum' or 'barycenter_x' or 'barycenter_y'
                what to do with the portion selected by the mask.
        """
        self.name = name
        self.mask = mask
        self.mode = mode
    def readout(self, exposure):
        if self.mode == 'max':
            return exposure.max(mask=self.mask)
        elif self.mode == 'min':
            return exposure.min(mask=self.mask)
        elif self.mode == 'mean':
            return exposure.mean(mask=self.mask)
        elif self.mode == 'sum':
            return exposure.sum(mask=self.mask)
        elif self.mode == 'barycenter_x':
            x, y = exposure.barycenter(mask=self.mask)
            return x
        elif self.mode == 'barycenter_y':
            x, y = exposure.barycenter(mask=self.mask)
            return y
            
            

class AddDetectorDialog(gtk.Dialog):
    _filechooserdialogs = None
    def __init__(self, title='Add detector', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        vb = self.get_content_area()
        self.set_default_response(gtk.RESPONSE_OK)
        if isinstance(parent, TimedScan):
            self.credo = parent.credo
        else:
            self.credo = None
        tab = gtk.Table()
        vb.pack_start(tab, False)
        self.set_resizable(False)
        row = 0
        
        l = gtk.Label('Detector name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.name_entry = gtk.Entry()
        self.name_entry.set_text('-- please fill --')
        tab.attach(self.name_entry, 1, 3, row, row + 1)
        row += 1

        l = gtk.Label('Mask file:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.maskfile_entry = gtk.Entry()
        tab.attach(self.maskfile_entry, 1, 2, row, row + 1)
        b = gtk.Button(stock=gtk.STOCK_OPEN)
        tab.attach(b, 2, 3, row, row + 1)
        b.connect('clicked', self.on_loadmaskbutton, self.maskfile_entry, gtk.FILE_CHOOSER_ACTION_OPEN)
        row += 1

        l = gtk.Label('Mode of operation:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.mode_entry = gtk.combo_box_new_text()
        self.mode_entry.append_text('max')
        self.mode_entry.append_text('min')
        self.mode_entry.append_text('sum')
        self.mode_entry.append_text('mean')
        self.mode_entry.append_text('barycenter_x')
        self.mode_entry.append_text('barycenter_y')
        self.mode_entry.set_active(0)
        tab.attach(self.mode_entry, 1, 3, row, row + 1)
        row += 1
        vb.show_all()
    def on_loadmaskbutton(self, button, entry, action):
        if self._filechooserdialogs is None:
            self._filechooserdialogs = {}
        if entry not in self._filechooserdialogs:
            
            self._filechooserdialogs[entry] = MaskChooserDialog('Select mask file...', None, action, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
            if self.credo is not None:
                self._filechooserdialogs[entry].set_current_folder(self.credo.maskpath)
        if entry.get_text():
            self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == gtk.RESPONSE_OK:
            entry.set_text(self._filechooserdialogs[entry].get_filename())
        self._filechooserdialogs[entry].hide()
        return True
    def get_detector(self):
        return VirtualPointDetector(self.name_entry.get_text(), sastool.classes.SASMask(self.maskfile_entry.get_text()), self.mode_entry.get_active_text())
        
class TimedScan(gtk.Dialog):
    _scanresults = []
    _dlg = None
    def __init__(self, credo, title='Timed scan', parent=None, flags=0, buttons=(gtk.STOCK_EXECUTE, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.credo = credo
        vb = self.get_content_area()
        tab = gtk.Table()
        self.entrytable = tab
        vb.pack_start(tab, False)
        self.set_resizable(False)
        row = 0
        
        l = gtk.Label('Sample name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.samplename_entry = gtk.Entry()
        self.samplename_entry.set_text('-- please fill --')
        tab.attach(self.samplename_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Exposure time (s):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.exptime_entry = gtk.SpinButton(gtk.Adjustment(0.1, 0, 100, 0.1, 1), digits=4)
        tab.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Number of exposures:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.nimages_entry = gtk.SpinButton(gtk.Adjustment(1, 1, 10000, 1, 10), digits=0)
        tab.attach(self.nimages_entry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Delay between exposures (s):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.dwelltime_entry = gtk.SpinButton(gtk.Adjustment(0.003, 0.003, 10000, 1, 10), digits=4)
        tab.attach(self.dwelltime_entry, 1, 2, row, row + 1)
        row += 1
        
        self.byhand_checkbutton = gtk.CheckButton('Expose one-by-one')
        self.byhand_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.byhand_checkbutton, 0, 2, row, row + 1)
        self.byhand_checkbutton.set_active(False)
        self.byhand_checkbutton.connect('toggled', self.on_byhand_checkbutton)
        row += 1

        self.recordgenix_checkbutton = gtk.CheckButton('Record GeniX parameters')
        self.recordgenix_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.recordgenix_checkbutton, 0, 2, row, row + 1)
        self.recordgenix_checkbutton.set_active(False)
        row += 1


        self.byhand_button = gtk.Button('Expose now!')
        self.get_action_area().pack_start(self.byhand_button)
        self.byhand_button.connect('clicked', self.on_byhand_button)
        self.byhand_button.set_sensitive(False)
        
        self.detectorsframe = gtk.Frame('Detectors')
        vb.pack_start(self.detectorsframe, False)
        hb = gtk.HBox()
        self.detectorsframe.add(hb)
        self.detectors_liststore = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)
        self.detectors_treeview = gtk.TreeView(self.detectors_liststore)
        self.detectors_treeview.set_headers_visible(True)
        self.detectors_treeview.set_rules_hint(True)
        self.detectors_treeview.get_selection().set_mode(gtk.SELECTION_BROWSE)
        cellrenderer = gtk.CellRendererText()
        self.detectors_treeview.append_column(gtk.TreeViewColumn('Name', cellrenderer, text=0))
        cellrenderer = gtk.CellRendererText()
        self.detectors_treeview.append_column(gtk.TreeViewColumn('Mask file', cellrenderer, text=1))
        cellrenderer = gtk.CellRendererText()
        self.detectors_treeview.append_column(gtk.TreeViewColumn('Mode', cellrenderer, text=2))
        self.detectors_treeview.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)
        hb.pack_start(self.detectors_treeview, True)
        vbb = gtk.VButtonBox()
        hb.pack_start(vbb, False)
        b = gtk.Button(stock=gtk.STOCK_ADD)
        b.connect('clicked', self.on_add_detector)
        vbb.add(b)
        b = gtk.Button(stock=gtk.STOCK_REMOVE)
        b.connect('clicked', self.on_remove_detector)
        vbb.add(b)
        b = gtk.Button(stock=gtk.STOCK_CLEAR)
        b.connect('clicked', self.on_clear_detectors)
        vbb.add(b)
        self.connect('response', self.on_response)
        self.connect('delete-event', self.hide_on_delete)
        
        vb.show_all()
        
    def on_byhand_checkbutton(self, *args):
        self.dwelltime_entry.set_sensitive(not self.byhand_checkbutton.get_active())
        self.nimages_entry.set_sensitive(not self.byhand_checkbutton.get_active())
    
    def on_add_detector(self, *args):
        if self._dlg is None:
            self._dlg = AddDetectorDialog(parent=self)
        ret = self._dlg.run()
        if ret == gtk.RESPONSE_OK:
            det = self._dlg.get_detector()
            self.detectors_liststore.append((det.name, det.mask.maskid, det.mode, det))
        self._dlg.hide()
        return True
    def on_remove_detector(self, *args):
        model, iter = self.detectors_treeview.get_selection().get_selected()
        model.remove(iter)
        return True
    def on_clear_detectors(self, *args):
        self.detectors_liststore.clear()
        return True
    def on_response(self, dialog, respid):
        if respid == gtk.RESPONSE_OK:
            if self.detectorsframe.get_sensitive():
                self.detectorsframe.set_sensitive(False)
                self.entrytable.set_sensitive(False)
                self.get_widget_for_response(gtk.RESPONSE_CANCEL).set_sensitive(False)
                self.byhand_button.set_sensitive(self.byhand_checkbutton.get_active())
                
                self.credo.set_sample(sample.SAXSSample(self.samplename_entry.get_text()))
                self.credo.set_fileformat('timedscan', 5)
                fsn = self.credo.get_next_fsn()
                self.credo.set_fileformat('timedscan_%05d' % fsn)
                self._scanfsn = fsn
                self._scanresults = []
                def _handler(imgdata):
                    gobject.idle_add(self.on_imagereceived, imgdata)
                    return False
                self._timeoffirstpoint = datetime.datetime.now()
                if not self.byhand_checkbutton.get_active():
                    self.credo.expose(self.exptime_entry.get_value(),
                                      self.nimages_entry.get_value_as_int(),
                                      self.dwelltime_entry.get_value(), blocking=False, callback=_handler)
                self.get_widget_for_response(gtk.RESPONSE_OK).set_label(gtk.STOCK_STOP)
            else:
                self.credo.killexposure()
                self.on_imagereceived(None)
        else:
            self.hide()
        return True
    def on_byhand_button(self, *args):
        def _handler(imgdata):
            gobject.idle_add(self.on_imagereceived, imgdata)
            return False
        self.credo.expose(self.exptime_entry.get_value(), blocking=False, callback=_handler)
    def readout_all(self, exposure):
        return [row[-1].readout(exposure) for row in self.detectors_liststore]
    def on_imagereceived(self, exposure):
        if not self._scanresults:
            logger.debug('initializing scan graphs.')
            self._scangraphs = [scangraph.ScanGraph('Scan results: ' + row[-1].name) for row in self.detectors_liststore]
            for sg, row in zip(self._scangraphs, self.detectors_liststore):
                sg.xlabel('Time (sec)')
                sg.ylabel(row[-1].name)
                sg.title(('Scan #%d' % self._scanfsn) + ' mask: ' + row[-1].mask.maskid + ' method: ' + row[-1].mode)
                sg.figtext(1, 0, self.credo.username + '@' + 'CREDO  ' + str(datetime.datetime.now()), ha='right', va='bottom')
                sg.show_all()
            with open(os.path.join(self.credo.scanpath, 'timedscan_%05d.txt' % self._scanfsn), 'wt') as f:
                f.write('# Timed scan #' + str(self._scanfsn) + '\n')
                f.write('# Sample: %s\n' % self.samplename_entry.get_text())
                f.write('# Exposure time: %f\n' % self.exptime_entry.get_value())
                f.write('# Dwell time: %f\n' % self.dwelltime_entry.get_value())
                f.write('# Start time: ' + str(self._timeoffirstpoint) + '\n')
                f.write('# Owner: ' + self.credo.username + '\n')
                f.write('# Project: ' + self.credo.projectname + '\n')
                f.write('# Reason for stopping: RUNNING\n')
                f.write('# Scan data follows.\n')
                f.write('# Time')
                for row in self.detectors_liststore:
                    f.write('\t' + row[-1].name)
                if self.recordgenix_checkbutton.get_active():
                    f.write('\tGeniX record time\tGeniX HT\tGeniX current\tGeniX status')
                f.write('\n')
                
        if exposure is None:  # exposure failed
            logger.debug('exposure broken.')
            broken = True
        else:
            logger.debug('image received.')
            data = [(exposure.header['CBF_Date'] - self._timeoffirstpoint).total_seconds()] + self.readout_all(exposure)
            del exposure
            for sg, d in zip(self._scangraphs, data[1:]):
                sg.add_datapoint(data[0], d)
            if self.recordgenix_checkbutton.get_active():
                data.extend([(datetime.datetime.now() - self._timeoffirstpoint).total_seconds(), self.credo.genix.get_ht(), self.credo.genix.get_current(), self.credo.genix.get_status_int()])
            self._scanresults.append(data)
            with open(os.path.join(self.credo.scanpath, 'timedscan_%05d.txt' % self._scanfsn), 'at') as f:
                f.write((('%16.16g\t' * (len(self.detectors_liststore) + 1))) % tuple(data[:len(self.detectors_liststore) + 1]))
                if self.recordgenix_checkbutton.get_active():
                    f.write('%16.16g\t%.2f\t%.2f\t%s' % tuple(data[-4:]))
                f.write('\n')
                
            gc.collect()
            if self.byhand_checkbutton.get_active() or (len(self._scanresults) < self.nimages_entry.get_value_as_int()):
                return False
            broken = False
        logger.debug('last scan point received, saving log file.')
        self.detectorsframe.set_sensitive(True)
        self.entrytable.set_sensitive(True)
        self.get_widget_for_response(gtk.RESPONSE_CANCEL).set_sensitive(True)
        self.get_widget_for_response(gtk.RESPONSE_OK).set_label(gtk.STOCK_EXECUTE)
        with open(os.path.join(self.credo.scanpath, 'timedscan_%05d.txt' % self._scanfsn), 'wt') as f:
            f.write('# Timed scan #' + str(self._scanfsn) + '\n')
            f.write('# Sample: %s\n' % self.samplename_entry.get_text())
            f.write('# Exposure time: %f\n' % self.exptime_entry.get_value())
            f.write('# Dwell time: %f\n' % self.dwelltime_entry.get_value())
            f.write('# Start time: ' + str(self._timeoffirstpoint) + '\n')
            f.write('# Owner: ' + self.credo.username + '\n')
            f.write('# Project: ' + self.credo.projectname + '\n')
            f.write('# Reason for stopping: ')
            if broken:
                f.write('BREAK\n')
            else:
                f.write('END\n')
            f.write('# Scan data follows.\n')
            f.write('# Time')
            for row in self.detectors_liststore:
                f.write('\t' + row[-1].name)
            if self.recordgenix_checkbutton.get_active():
                f.write('\tGeniX record time\tGeniX HT\tGeniX current\tGeniX status')
            f.write('\n')
            for d in self._scanresults:
                f.write((('%16.16g\t' * (len(self.detectors_liststore) + 1))) % tuple(d[:len(self.detectors_liststore) + 1]))
                if self.recordgenix_checkbutton.get_active():
                    f.write('%16.16g\t%.2f\t%.2f\t%s' % tuple(d[-4:]))
                f.write('\n')
        return False
    
