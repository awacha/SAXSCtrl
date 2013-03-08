from gi.repository import Gtk
import sastool
import sasgui
import numpy as np
from .spec_filechoosers import ExposureLoader
from .peakfinder import PeakFinder

class QCalibrationDialog(sasgui.QCalibrator):
    def __init__(self, credo, title='Q calibration', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)):
        sasgui.QCalibrator.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.CLOSE)
        self.credo = credo
        vb = self.get_content_area()
        row = 0

        f = Gtk.Frame(label='Exposure:')
        vb.pack_start(f, True, True, 0)
        vb.reorder_child(f, 0)
        self.exposureloader = ExposureLoader(credo)
        self.exposureloader.connect('exposure-loaded', self.do_load_exposure)
        f.add(self.exposureloader)
        
        self.wavelength_checkbutton.set_active(True)
        self.wavelength_entry.set_text('1.5418')
        self.pixelsize_checkbutton.set_active(True)
        self.pixelsize_entry.set_text('0.172')
        self.beampos_checkbutton.set_active(True)
        self.beampos_entry.set_text('0')
        self.alpha_checkbutton.set_active(True)
        self.alpha_entry.set_text('90')
        
        vb.show_all()
        
        aa = self.get_action_area()
        self.findpeakbutton = Gtk.Button('Find peak...')
        aa.pack_start(self.findpeakbutton, True, True, 0)
        self.findpeakbutton.connect('clicked', self.do_find_peak)
        self.findpeakbutton.set_sensitive(False)
        self._rad = None
    def do_load_exposure(self, el, ex):
        try:
            self._rad = ex.radial_average(pixel=True)
            del ex
            self.findpeakbutton.set_sensitive(True)
        except sastool.classes.SASExposureException:
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Please load a mask!')
            md.run()
            md.destroy()
            el.forget_exposure()
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
