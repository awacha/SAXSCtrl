import gtk
import sastool
import sasgui
import numpy as np
from .spec_filechoosers import ExposureLoader
from .peakfinder import PeakFinder

class QCalibrationDialog(sasgui.QCalibrator):
    def __init__(self, credo, title='Q calibration', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK)):
        sasgui.QCalibrator.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_CLOSE)
        self.credo = credo
        vb = self.get_content_area()
        row = 0

        f = gtk.Frame('Exposure:')
        vb.pack_start(f)
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
        self.findpeakbutton = gtk.Button('Find peak...')
        aa.pack_start(self.findpeakbutton)
        self.findpeakbutton.connect('clicked', self.do_find_peak)
        self.findpeakbutton.set_sensitive(False)
        self._rad = None
    def do_load_exposure(self, el, ex):
        try:
            self._rad = ex.radial_average(pixel=True)
            del ex
            self.findpeakbutton.set_sensitive(True)
        except sastool.classes.SASExposureException:
            md = gtk.MessageDialog(self.get_toplevel(), gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, 'Please load a mask!')
            md.run()
            md.destroy()
            el.forget_exposure()
            del md
    def do_find_peak(self, button):
        pf = PeakFinder(self._rad)
        res = gtk.RESPONSE_APPLY
        while res not in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_DELETE_EVENT):
            res = pf.run()
            if res == gtk.RESPONSE_APPLY:
                self.calibrationpairs.append((pf.lastfoundpeak[1], 2 * np.pi * pf.n_entry.get_value_as_int() / pf.d_entry.get_value()))
                self.update_extended_params()
                self.redraw()
        pf.destroy()
