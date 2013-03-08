# coding: utf-8
import gtk
import sastool
import numpy as np
from .spec_filechoosers import MaskChooserDialog
import gobject

class TransmissionMeasurement(gtk.Dialog):
    _sample_I = None
    _empty_I = None
    _exps_expected = 0
    _transm = None
    _dtransm = None
    _buttons = None
    _filechooserdialogs = None
    def __init__(self, credo, title='Transmission measurement', parent=None, flags=0, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_APPLY, gtk.RESPONSE_APPLY, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.credo = credo
        vb = self.get_content_area()
        tab = gtk.Table()
        self.entrytab = tab
        vb.pack_start(tab, False)
        self.set_resizable(False)
        row = 0
    
        l = gtk.Label('Sample:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.sample_combo = gtk.combo_box_new_text()
        self.entrytab.attach(self.sample_combo, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Exposure time:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.exptime_entry = gtk.SpinButton(gtk.Adjustment(0.1, 0.0001, 1e10, 1, 10), digits=4)
        self.entrytab.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Number of exposures:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.nimages_entry = gtk.SpinButton(gtk.Adjustment(10, 0.0001, 1e10, 1, 10), digits=4)
        self.entrytab.attach(self.nimages_entry, 1, 2, row, row + 1)
        row += 1
    
        l = gtk.Label('Mask for beam area:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.mask_entry = gtk.Entry()
        hb = gtk.HBox()
        self.entrytab.attach(hb, 1, 2, row, row + 1)
        hb.pack_start(self.mask_entry)
        b = gtk.Button(stock=gtk.STOCK_OPEN)
        hb.pack_start(b, False)
        b.connect('clicked', self.on_loadmaskbutton, self.mask_entry, gtk.FILE_CHOOSER_ACTION_OPEN)
        row += 1

        l = gtk.Label('Method for intensity determination:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.method_combo = gtk.combo_box_new_text()
        self.entrytab.attach(self.method_combo, 1, 2, row, row + 1)
        self.method_combo.append_text('max')
        self.method_combo.append_text('sum')
        self.method_combo.set_active(0)
        row += 1
        
        tab = gtk.Table()
        vb.pack_start(tab, False)
        
        l = gtk.Label('Sample:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 1, 2, gtk.FILL, gtk.FILL)
        l = gtk.Label('Empty beam:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 2, 3, gtk.FILL, gtk.FILL)
        l = gtk.Label('# of exposures'); l.set_alignment(0, 0.5)
        tab.attach(l, 1, 2, 0, 1, xpadding=10)
        l = gtk.Label('Mean'); l.set_alignment(0, 0.5)
        tab.attach(l, 2, 3, 0, 1, xpadding=10)
        l = gtk.Label('Stddev'); l.set_alignment(0, 0.5)
        tab.attach(l, 3, 4, 0, 1, xpadding=10)
        
        self._buttons = []
        self.sampleN_label = gtk.Label('0')
        tab.attach(self.sampleN_label, 1, 2, 1, 2, xpadding=10)
        self.emptyN_label = gtk.Label('0')
        tab.attach(self.emptyN_label, 1, 2, 2, 3, xpadding=10)
        self.samplemean_label = gtk.Label()
        tab.attach(self.samplemean_label, 2, 3, 1, 2, xpadding=10)
        self.emptymean_label = gtk.Label()
        tab.attach(self.emptymean_label, 2, 3, 2, 3, xpadding=10)
        self.samplestd_label = gtk.Label()
        tab.attach(self.samplestd_label, 3, 4, 1, 2, xpadding=10)
        self.emptystd_label = gtk.Label()
        tab.attach(self.emptystd_label, 3, 4, 2, 3, xpadding=10)
        b = gtk.Button(stock=gtk.STOCK_EXECUTE)
        tab.attach(b, 4, 5, 1, 2, gtk.FILL, gtk.FILL)
        b.connect('clicked', self.do_exposure, 'Sample')
        self._buttons.append(b)
        b = gtk.Button(stock=gtk.STOCK_EXECUTE)
        tab.attach(b, 4, 5, 2, 3, gtk.FILL, gtk.FILL)
        b.connect('clicked', self.do_exposure, 'Empty')
        self._buttons.append(b)
        b = gtk.Button(stock=gtk.STOCK_CLEAR)
        tab.attach(b, 5, 6, 1, 2, gtk.FILL, gtk.FILL)
        b.connect('clicked', self.do_clear, 'Sample')
        self._buttons.append(b)
        b = gtk.Button(stock=gtk.STOCK_CLEAR)
        tab.attach(b, 5, 6, 2, 3, gtk.FILL, gtk.FILL)
        b.connect('clicked', self.do_clear, 'Empty')
        self._buttons.append(b)
        
        f = gtk.Frame('Measured transmission')
        vb.pack_start(f)
        hb = gtk.HBox()
        f.add(hb)
        self.transm_label = gtk.Label('--')
        self.transm_label.set_alignment(0, 0.5)
        hb.pack_start(self.transm_label, False)

        l = gtk.Label('+/-'); l.set_alignment(0, 0.5)
        hb.pack_start(l, False, True, 10)

        self.transmstd_label = gtk.Label('--')
        self.transmstd_label.set_alignment(0, 0.5)
        hb.pack_start(self.transmstd_label, False)
        
        
        self.credo.connect_callback('samples-changed', self.reload_samples)
        self.reload_samples()
        self.connect('response', self.on_response)
        self._sample_I = []
        self._empty_I = []
        self.do_refresh_labels()
    def do_exposure(self, button, type_):
        try:
            self._mask = sastool.classes.SASMask(self.mask_entry.get_text())
        except (NotImplementedError, IOError):
            md = gtk.MessageDialog(self, gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, "Please select a valid mask!")
            md.run()
            md.destroy()
            del md
            return
        sam = self.credo.get_samples()[self.sample_combo.get_active()]
        self.credo.set_sample(sam)
        self.credo.set_fileformat('transm', 5)
        if type_ == 'Sample':
            lis = self._sample_I
        elif type_ == 'Empty':
            lis = self._empty_I
        def _handler(imgdata):
            gobject.idle_add(self.on_imagereceived, imgdata, lis, button)
            return False
        self.entrytab.set_sensitive(False)
        for b in self._buttons:
            b.set_sensitive(False)
        button.set_sensitive(True)
        button.set_label(gtk.STOCK_STOP)
        self.get_widget_for_response(gtk.RESPONSE_CANCEL).set_sensitive(False)
        self.get_widget_for_response(gtk.RESPONSE_OK).set_sensitive(False)
        self.get_widget_for_response(gtk.RESPONSE_APPLY).set_sensitive(False)
        self._exps_expected = self.nimages_entry.get_value_as_int()
        self._exptype = type_
        self.credo.expose(self.exptime_entry.get_value(), self._exps_expected, blocking=False, callback=_handler)
    def on_imagereceived(self, exposure, lis, button):
        if exposure is not None:
            if self.method_combo.get_active_text() == 'sum':
                lis.append(exposure.sum(mask=self._mask))
            elif self.method_combo.get_active_text() == 'max':
                lis.append(exposure.max(mask=self._mask))
            else:
                raise NotImplementedError(self.method_combo.get_active_text())
            self.do_refresh_labels()
            self._exps_expected -= 1
            if self._exps_expected > 0:
                return False
        self.get_widget_for_response(gtk.RESPONSE_CANCEL).set_sensitive(True)
        self.get_widget_for_response(gtk.RESPONSE_OK).set_sensitive(True)
        self.get_widget_for_response(gtk.RESPONSE_APPLY).set_sensitive(True)
        self.entrytab.set_sensitive(True)
        for b in self._buttons:
            b.set_sensitive(True)
        button.set_label(gtk.STOCK_EXECUTE)
        return False
    def do_clear(self, button, type_):
        if type_ == 'Sample':
            self._sample_I = []
        elif type_ == 'Empty':
            self._empty_I = []
        self.do_refresh_labels()
    def do_refresh_labels(self):
        self.sampleN_label.set_text(str(len(self._sample_I)))
        self.emptyN_label.set_text(str(len(self._empty_I)))
        if self._sample_I:
            self.samplemean_label.set_text(str(np.mean(self._sample_I)))
            self.samplestd_label.set_text(str(np.std(self._sample_I)))
        else:
            self.samplemean_label.set_text('--')
            self.samplestd_label.set_text('--')
        if self._empty_I:
            self.emptymean_label.set_text(str(np.mean(self._empty_I)))
            self.emptystd_label.set_text(str(np.std(self._empty_I)))
        else:
            self.emptymean_label.set_text('--')
            self.emptystd_label.set_text('--')
        if self._sample_I and self._empty_I:
            S = np.mean(self._sample_I)
            dS = np.std(self._sample_I)
            E = np.mean(self._empty_I)
            dE = np.std(self._empty_I)
            self._transm = S / E
            self._dtransm = (dS ** 2 / E ** 2 + S ** 2 / E ** 4 * dE ** 2) ** 0.5
            self.transm_label.set_text(str(self._transm))
            self.transmstd_label.set_text(str(self._dtransm))
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
        
    def reload_samples(self, *args):
        self.sample_combo.get_model().clear()
        idx = 0
        for i, sam in enumerate(self.credo.get_samples()):
            if sam == self.credo.sample:
                idx = i
            self.sample_combo.append_text(u'%s (%.2f°C @%.2f)' % (sam.title, sam.temperature, sam.position))
        self.sample_combo.set_active(idx)
    def on_response(self, dlg, respid):
        if (respid == gtk.RESPONSE_APPLY or respid == gtk.RESPONSE_OK) and self._transm is not None:
            sam = self.credo.get_samples()[self.sample_combo.get_active()]
            sam.transmission = sastool.classes.ErrorValue(self._transm, self._dtransm)
            self.credo.save_samples()
        if (respid != gtk.RESPONSE_APPLY):
            self.hide()
        return True
            
