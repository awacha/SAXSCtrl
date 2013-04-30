# coding: utf-8
from gi.repository import Gtk
import sastool
import numpy as np
from .spec_filechoosers import MaskChooserDialog
from .samplesetup import SampleSelector
from gi.repository import GObject
from .widgets import ExposureInterface

class TransmissionMeasurement(Gtk.Dialog, ExposureInterface):
    _sample_I = None
    _empty_I = None
    _transm = None
    _dtransm = None
    _buttons = None
    _filechooserdialogs = None
    def __init__(self, credo, title='Transmission measurement', parent=None, flags=0, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        self.credo = credo
        vb = self.get_content_area()
        tab = Gtk.Table()
        self.entrytab = tab
        vb.pack_start(tab, False, True, 0)
        self.set_resizable(False)
        row = 0
    
        l = Gtk.Label(label='Sample:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.sample_combo = SampleSelector(self.credo)
        self.entrytab.attach(self.sample_combo, 1, 2, row, row + 1)
        self.sample_combo.connect('sample-changed', lambda combo, sample:self.clear_data())
        row += 1
        
        l = Gtk.Label(label='Exposure time:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0.1, 0.0001, 1e10, 1, 10), digits=4)
        self.entrytab.attach(self.exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Number of exposures:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.nimages_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(10, 0.0001, 1e10, 1, 10), digits=4)
        self.entrytab.attach(self.nimages_entry, 1, 2, row, row + 1)
        row += 1
    
        l = Gtk.Label(label='Mask for beam area:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.mask_entry = Gtk.Entry()
        hb = Gtk.HBox()
        self.entrytab.attach(hb, 1, 2, row, row + 1)
        hb.pack_start(self.mask_entry, True, True, 0)
        b = Gtk.Button(stock=Gtk.STOCK_OPEN)
        hb.pack_start(b, False, True, 0)
        b.connect('clicked', self.on_loadmaskbutton, self.mask_entry, Gtk.FileChooserAction.OPEN)
        row += 1

        l = Gtk.Label(label='Method for intensity determination:'); l.set_alignment(0, 0.5)
        self.entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.method_combo = Gtk.ComboBoxText()
        self.entrytab.attach(self.method_combo, 1, 2, row, row + 1)
        self.method_combo.append_text('max')
        self.method_combo.append_text('sum')
        self.method_combo.set_active(0)
        row += 1
        
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        
        l = Gtk.Label(label='Sample:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 1, 2, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='Empty beam:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 2, 3, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='# of exposures'); l.set_alignment(0, 0.5)
        tab.attach(l, 1, 2, 0, 1, xpadding=10)
        l = Gtk.Label(label='Mean cps'); l.set_alignment(0, 0.5)
        tab.attach(l, 2, 3, 0, 1, xpadding=10)
        l = Gtk.Label(label='RMS cps'); l.set_alignment(0, 0.5)
        tab.attach(l, 3, 4, 0, 1, xpadding=10)
        
        self._buttons = []
        self.sampleN_label = Gtk.Label(label='0')
        tab.attach(self.sampleN_label, 1, 2, 1, 2, xpadding=10)
        self.emptyN_label = Gtk.Label(label='0')
        tab.attach(self.emptyN_label, 1, 2, 2, 3, xpadding=10)
        self.samplemean_label = Gtk.Label()
        tab.attach(self.samplemean_label, 2, 3, 1, 2, xpadding=10)
        self.emptymean_label = Gtk.Label()
        tab.attach(self.emptymean_label, 2, 3, 2, 3, xpadding=10)
        self.samplestd_label = Gtk.Label()
        tab.attach(self.samplestd_label, 3, 4, 1, 2, xpadding=10)
        self.emptystd_label = Gtk.Label()
        tab.attach(self.emptystd_label, 3, 4, 2, 3, xpadding=10)
        b = Gtk.Button(stock=Gtk.STOCK_EXECUTE)
        tab.attach(b, 4, 5, 1, 2, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', self.start_measurement, 'Sample')
        self._buttons.append(b)
        b = Gtk.Button(stock=Gtk.STOCK_EXECUTE)
        tab.attach(b, 4, 5, 2, 3, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', self.start_measurement, 'Empty')
        self._buttons.append(b)
        b = Gtk.Button(stock=Gtk.STOCK_CLEAR)
        tab.attach(b, 5, 6, 1, 2, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', self.clear_data, 'Sample')
        self._buttons.append(b)
        b = Gtk.Button(stock=Gtk.STOCK_CLEAR)
        tab.attach(b, 5, 6, 2, 3, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', self.clear_data, 'Empty')
        self._buttons.append(b)
        
        f = Gtk.Frame(label='Measured transmission')
        vb.pack_start(f, True, True, 0)
        hb = Gtk.HBox()
        f.add(hb)
        self.transm_label = Gtk.Label(label='--')
        self.transm_label.set_alignment(0, 0.5)
        hb.pack_start(self.transm_label, False, True, 0)

        l = Gtk.Label(label='+/-'); l.set_alignment(0, 0.5)
        hb.pack_start(l, False, True, 10)

        self.transmstd_label = Gtk.Label(label='--')
        self.transmstd_label.set_alignment(0, 0.5)
        hb.pack_start(self.transmstd_label, False, True, 0)
        
        self.connect('response', self.on_response)
        self._sample_I = []
        self._empty_I = []
        self.do_refresh_labels()
    def on_exposure_end(self, credo, state):
        ExposureInterface.on_exposure_end(self, credo, state)
        self._expbutton.set_label(Gtk.STOCK_EXECUTE)
    def on_exposure_done(self, credo, exposure):
        if self.method_combo.get_active_text() == 'sum':
            self._explis.append(exposure.sum(mask=self._mask) / exposure['MeasTime'])
        elif self.method_combo.get_active_text() == 'max':
            self._explis.append(exposure.max(mask=self._mask) / exposure['MeasTime'])
        else:
            raise NotImplementedError(self.method_combo.get_active_text())
        GObject.idle_add(lambda dummy:self.do_refresh_labels() and dummy, False)
    def start_measurement(self, button, type_):
        if button.get_label() == Gtk.STOCK_STOP:
            self.credo.killexposure()
        else:
            try:
                self._mask = sastool.classes.SASMask(self.mask_entry.get_text())
            except (NotImplementedError, IOError):
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, "Please select a valid mask!")
                md.run()
                md.destroy()
                del md
                return
            self._expbutton = button
            self.credo.set_sample(self.sample_combo.get_sample())
            self.credo.set_fileformat('transm', 5)
            if type_ == 'Sample':
                self._explis = self._sample_I
            elif type_ == 'Empty':
                self._explis = self._empty_I
            _expbutton.set_label(Gtk.STOCK_STOP)
            self._exptype = type_
            self._explis = lis
            self.start_exposure(self.exptime_entry.get_value(), self.nimages_entry.get_value_as_int(),
                                insensitive=[self.entrytab] + self._buttons + [self.get_widget_for_response(x) for x in [Gtk.ResponseType.CANCEL, Gtk.ResponseType.OK, Gtk.ResponseType.APPLY]])
            self._expbutton.set_sensitive(True)
    def clear_data(self, button=None, type_=None):
        if type_ == 'Sample' or type_ is None:
            self._sample_I = []
        elif type_ == 'Empty' or type_ is None:
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
        
    def on_response(self, dlg, respid):
        if (respid == Gtk.ResponseType.APPLY or respid == Gtk.ResponseType.OK) and self._transm is not None:
            sam = self.credo.get_samples()[self.sample_combo.get_active()]
            sam.transmission = sastool.classes.ErrorValue(self._transm, self._dtransm)
            self.credo.save_samples()
        if (respid != Gtk.ResponseType.APPLY):
            self.hide()
        return True
            
