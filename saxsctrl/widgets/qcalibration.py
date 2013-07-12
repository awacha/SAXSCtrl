from gi.repository import Gtk
import sastool
import sasgui
import numpy as np
from .exposureselector import ExposureSelector
from .peakfinder import PeakFinder
from .widgets import ToolDialog

class QCalibrationDialog(sasgui.QCalibrator):
    def __init__(self, credo, title='Q calibration'):
        sasgui.QCalibrator.__init__(self, title, flags=0, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE,))
        self.set_default_response(Gtk.ResponseType.CLOSE)
        self.credo = credo
        self.connect('response', self.on_response)
        self.connect('notify::dist', lambda obj, prop:self.do_changed())
        vb = self.get_content_area()
        row = 0

        f = Gtk.Expander(label='Exposure:')
        vb.pack_start(f, True, True, 0)
        vb.reorder_child(f, 0)
        es = ExposureSelector(credo)
        es.connect('open', self.do_load_exposure)
        f.add(es)
        f.set_expanded(True)
        
        self.wavelength = 1.5418
        self.pixelsize = 0.172
        self.alpha = np.pi / 2
        self.beampos = 0
        for i in ['alpha', 'beampos', 'pixelsize', 'wavelength']:
            self.set_fixed(i)
        self.checkbuttons['alpha'].set_sensitive(False)
        self.entries['alpha'].set_sensitive(False)
        vb.show_all()
        
        aa = self.get_action_area()
        self.findpeakbutton = Gtk.Button('Find peak...')
        aa.pack_start(self.findpeakbutton, True, True, 0)
        self.findpeakbutton.connect('clicked', self.do_find_peak)
        self.findpeakbutton.set_sensitive(False)
        self._rad = None
        self.get_widget_for_response(Gtk.ResponseType.APPLY).set_sensitive(False)
    def do_changed(self):
        self.get_widget_for_response(Gtk.ResponseType.APPLY).set_sensitive(True)
    def do_load_exposure(self, el, ex):
        try:
            self._rad = ex.radial_average(pixel=True)
            del ex
            self.findpeakbutton.set_sensitive(True)
        except sastool.classes.SASExposureException:
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Please load a mask!')
            md.run()
            md.destroy()
            del md
    def do_find_peak(self, button):
        pf = PeakFinder(self._rad)
        res = Gtk.ResponseType.APPLY
        while res not in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            res = pf.run()
            if res == Gtk.ResponseType.APPLY:
                self.calibrationpairs.append((float(pf.lastfoundpeak[1]), float(2 * np.pi * pf.n_entry.get_value_as_int() / pf.d_entry.get_value())))
                self.update_extended_params()
                self.redraw()
        pf.destroy()
    def to_credo(self):
        self.get_widget_for_response(Gtk.ResponseType.APPLY).set_sensitive(False)
        for prop in ['dist', 'pixelsize', 'wavelength']:
            if self.credo.get_property(prop) != self.get_property(prop):
                self.credo.set_property(prop, self.get_property(prop))
    def on_response(self, dialog, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.OK):
            self.destroy()
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            self.to_credo()
        return
