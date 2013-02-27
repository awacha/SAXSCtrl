import gtk
import sastool
import sasgui
import os
from .spec_filechoosers import ExposureLoader

class CenteringDialog(gtk.Dialog):
    def __init__(self, credo, title='Centering image...', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE, gtk.STOCK_EXECUTE, gtk.RESPONSE_APPLY, gtk.STOCK_SAVE, gtk.RESPONSE_YES)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_CLOSE)
        self.credo = credo
        vb = self.get_content_area()
        f = gtk.Frame()
        vb.pack_start(f, False)
        hb = gtk.HBox()
        f.add(hb)
        l = gtk.Label('Exposure:'); l.set_alignment(0, 0.5)
        hb.pack_start(l, False)
        el = ExposureLoader(credo)
        hb.pack_start(el, True)
        el.connect('exposure-loaded', self.on_exposure_loaded)
        
        hb = gtk.HBox()
        vb.pack_start(hb)
        vb1 = gtk.VBox()
        hb.pack_start(vb1, False)
        
        self.plot2d = sasgui.plot2dsasimage.PlotSASImage()
        hb.pack_start(self.plot2d, True)
        
        self.nb = gtk.Notebook()
        vb1.pack_start(self.nb, True)
        
        tab = gtk.Table()
        self.nb.append_page(tab, gtk.Label('Barycenter'))
        row = 0
        l = gtk.Label('Zoom to the beam area and press "Execute"!')
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, 0)
        row += 1
        
        tab = gtk.Table()
        self.nb.append_page(tab, gtk.Label('Radial peak'))
        row = 0
        
        l = gtk.Label('R min (pixel):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, 0)
        self.minpixel_entry = gtk.SpinButton(gtk.Adjustment(0, 0, 1e5, 1, 10), digits=2)
        tab.attach(self.minpixel_entry, 1, 2, row, row + 1, gtk.FILL | gtk.EXPAND, 0)
        row += 1
        
        l = gtk.Label('R max (pixel):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, 0)
        self.maxpixel_entry = gtk.SpinButton(gtk.Adjustment(0, 0, 1e5, 1, 10), digits=2)
        tab.attach(self.maxpixel_entry, 1, 2, row, row + 1, gtk.FILL | gtk.EXPAND, 0)
        row += 1
        
        l = gtk.Label('Drive by:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, 0)
        self.driveby_combo = gtk.combo_box_new_text()
        tab.attach(self.driveby_combo, 1, 2, row, row + 1, gtk.FILL | gtk.EXPAND, 0)
        self.driveby_combo.append_text('amplitude')
        self.driveby_combo.append_text('hwhm')
        self.driveby_combo.set_active(0)
        row += 1

        b = gtk.Button('Check radial average');
        tab.attach(b, 0, 1, row, row + 1, gtk.FILL | gtk.EXPAND, 0)        
        b.connect('clicked', self.on_radavg)
        self.radavg_plotmode = gtk.combo_box_new_text()
        tab.attach(self.radavg_plotmode, 1, 2, row, row + 1, gtk.FILL | gtk.EXPAND, 0)
        self.radavg_plotmode.append_text('plot')
        self.radavg_plotmode.append_text('semilogx')
        self.radavg_plotmode.append_text('semilogy')
        self.radavg_plotmode.append_text('loglog')
        self.radavg_plotmode.set_active(2)
        
        tab = gtk.Table()
        self.nb.append_page(tab, gtk.Label('Manual'))
        row = 0
        l = gtk.Label('Beam position X (vertical):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, 0)
        self.beamposx_entry = gtk.SpinButton(gtk.Adjustment(0, 0, 1e5, 1, 10), digits=2)
        tab.attach(self.beamposx_entry, 1, 2, row, row + 1, gtk.FILL | gtk.EXPAND, 0)
        row += 1
        
        l = gtk.Label('Beam position Y (horizontal):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, 0)
        self.beamposy_entry = gtk.SpinButton(gtk.Adjustment(0, 0, 1e5, 1, 10), digits=2)
        tab.attach(self.beamposy_entry, 1, 2, row, row + 1, gtk.FILL | gtk.EXPAND, 0)
        row += 1
        
        self.autosave_cb = gtk.CheckButton('Auto-save beam position')
        vb1.pack_start(self.autosave_cb, False)
        self.autosave_cb.set_active(True)
        
        f = gtk.Frame('Current position')
        vb1.pack_start(f, False)
        tab = gtk.Table()
        f.add(tab)
        l = gtk.Label('X (vertical):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 0, 1, gtk.FILL, gtk.FILL)
        self.beamposx_label = gtk.Label(); l.set_alignment(0, 0.5)
        tab.attach(self.beamposx_label, 1, 2, 0, 1, xpadding=10)

        l = gtk.Label('Y (horizontal):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 1, 2, gtk.FILL, gtk.FILL)
        self.beamposy_label = gtk.Label(); l.set_alignment(0, 0.5)
        tab.attach(self.beamposy_label, 1, 2, 1, 2, xpadding=10)
        
        
        self.connect('response', self.on_response)
        self._radavgwin = None
    def on_exposure_loaded(self, el, ex):
        self.plot2d.set_exposure(ex)
        self.beamposx_label.set_text('%.2f' % ex['BeamPosX'])
        self.beamposy_label.set_text('%.2f' % ex['BeamPosY'])
    def on_radavg(self, button):
        ex = self.plot2d.exposure
        rad = ex.radial_average(pixel=True)
        if self._radavgwin is not None and not self._radavgwin.get_realized():
            self._radavgwin.destroy()
            del self._radavgwin
            self._radavgwin = None
        if self._radavgwin is None:
            self._radavgwin = sasgui.PlotSASCurveWindow('Radial averages', self.get_toplevel())
            self._radavgwin.show_all()
        func = self._radavgwin.__getattribute__(self.radavg_plotmode.get_active_text())
        func(rad, label=ex['FileName'])
        if self.autosave_cb.get_active():
            self.save_beampos()
    def execute_findbeam(self):
        ex = self.plot2d.exposure
        if self.nb.get_current_page() == 0:  # barycenter
            xmin, xmax, ymin, ymax = self.plot2d.get_axes().axis()
            beampos = ex.find_beam_semitransparent((ymin, ymax, xmin, xmax), threshold=None, update=True)
        elif self.nb.get_current_page() == 1:  # radial peak
            beampos = ex.find_beam_radialpeak(self.minpixel_entry.get_value(), self.maxpixel_entry.get_value(), self.driveby_combo.get_active_text(), update=True)
        elif self.nb.get_current_page() == 2:  # manual
            beampos = (self.beamposx_entry.get_value(), self.beamposy_entry.get_value())
            ex['BeamPosX'], ex['BeamPosY'] = beampos
        else:
            raise NotImplementedError
        self.plot2d.set_exposure(ex)
        self.beamposx_entry.set_value(beampos[0])
        self.beamposy_entry.set_value(beampos[1])
        self.beamposx_label.set_text('%.2f' % beampos[0])
        self.beamposy_label.set_text('%.2f' % beampos[1])
    def save_beampos(self):
        ex = self.plot2d.exposure
        basename = os.path.basename(ex['FileName']).rsplit('.', 1)[0]
        ex.header.write(os.path.join(self.credo.eval2dpath, basename + '.param'))
        
    def on_response(self, dialog, respid):
        if respid == gtk.RESPONSE_APPLY:  # execute
            self.execute_findbeam()
        if respid == gtk.RESPONSE_YES:  # save
            self.save_beampos()
            
