from gi.repository import Gtk
import sasgui
import os
from .exposureselector import ExposureSelector
from .widgets import ToolDialog

class CenteringDialog(ToolDialog):
    def __init__(self, credo, title='Centering image...') :
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_EXECUTE, 1, Gtk.STOCK_SAVE, Gtk.ResponseType.YES))
        vb = self.get_content_area()
        f = Gtk.Expander(label='Exposure')
        vb.pack_start(f, False, True, 0)
        es = ExposureSelector(credo)
        f.add(es)
        es.connect('open', self._exposure_loaded)
        f.set_expanded(True)
        hb = Gtk.HBox()
        vb.pack_start(hb, True, True, 0)
        vb1 = Gtk.VBox()
        hb.pack_start(vb1, False, True, 0)

        self.plot2d = sasgui.plot2dsasimage.PlotSASImage()
        hb.pack_start(self.plot2d, True, True, 0)
        self.plot2d.set_size_request(300, 300)

        self.nb = Gtk.Notebook()
        vb1.pack_start(self.nb, True, True, 0)

        tab = Gtk.Table()
        self.nb.append_page(tab, Gtk.Label(label='Barycenter'))
        row = 0
        l = Gtk.Label(label='Zoom to the beam area and press "Execute"!')
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, 0)
        row += 1

        tab = Gtk.Table()
        self.nb.append_page(tab, Gtk.Label(label='Radial peak'))
        row = 0

        l = Gtk.Label(label='R min (pixel):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, 0)
        self.minpixel_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 1e5, 1, 10), digits=2)
        tab.attach(self.minpixel_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        row += 1

        l = Gtk.Label(label='R max (pixel):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, 0)
        self.maxpixel_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 1e5, 1, 10), digits=2)
        tab.attach(self.maxpixel_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        row += 1

        l = Gtk.Label(label='Drive by:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, 0)
        self.driveby_combo = Gtk.ComboBoxText()
        tab.attach(self.driveby_combo, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        self.driveby_combo.append_text('amplitude')
        self.driveby_combo.append_text('hwhm')
        self.driveby_combo.set_active(0)
        row += 1

        b = Gtk.Button('Check radial average');
        tab.attach(b, 0, 1, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        b.connect('clicked', self.on_radavg)
        self.radavg_plotmode = Gtk.ComboBoxText()
        tab.attach(self.radavg_plotmode, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        self.radavg_plotmode.append_text('plot')
        self.radavg_plotmode.append_text('semilogx')
        self.radavg_plotmode.append_text('semilogy')
        self.radavg_plotmode.append_text('loglog')
        self.radavg_plotmode.set_active(3)

        tab = Gtk.Table()
        self.nb.append_page(tab, Gtk.Label(label='Manual'))
        row = 0
        l = Gtk.Label(label='Beam position X (vertical):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, 0)
        self.beamposx_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 1e5, 1, 10), digits=2)
        tab.attach(self.beamposx_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        row += 1

        l = Gtk.Label(label='Beam position Y (horizontal):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, 0)
        self.beamposy_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 1e5, 1, 10), digits=2)
        tab.attach(self.beamposy_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        row += 1

        self.autosave_cb = Gtk.CheckButton('Auto-save beam position')
        vb1.pack_start(self.autosave_cb, False, True, 0)
        self.autosave_cb.set_active(True)

        f = Gtk.Frame(label='Current position')
        vb1.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        l = Gtk.Label(label='X (vertical):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.beamposx_label = Gtk.Label(); l.set_alignment(0, 0.5)
        tab.attach(self.beamposx_label, 1, 2, 0, 1, xpadding=10)

        l = Gtk.Label(label='Y (horizontal):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 1, 2, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.beamposy_label = Gtk.Label(); l.set_alignment(0, 0.5)
        tab.attach(self.beamposy_label, 1, 2, 1, 2, xpadding=10)


        self._radavgwin = None
    def _exposure_loaded(self, es, ex):
        self.plot2d.set_exposure(ex)
        self.beamposx_label.set_text('%.2f' % ex['BeamPosX'])
        self.beamposy_label.set_text('%.2f' % ex['BeamPosY'])
    def on_radavg(self, button):
        ex = self.plot2d.get_exposure()
        rad = ex.radial_average(pixel=True)
        if self._radavgwin is not None and not self._radavgwin.get_realized():
            self._radavgwin.destroy()
            del self._radavgwin
            self._radavgwin = None
        if self._radavgwin is None:
            self._radavgwin = sasgui.PlotSASCurveWindow('Radial averages')
            self._radavgwin.show_all()
        func = self._radavgwin.__getattribute__(self.radavg_plotmode.get_active_text())
        func(rad, label=ex['FileName'])
        if self.autosave_cb.get_active():
            self.save_beampos()
    def execute_findbeam(self):
        ex = self.plot2d.get_exposure()
        if self.nb.get_current_page() == 0:  # barycenter
            xmin, xmax, ymin, ymax = self.plot2d.get_zoom()
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
        ex = self.plot2d.get_exposure()
        basename = os.path.basename(ex['FileName']).rsplit('.', 1)[0]
        ex.header.write(os.path.join(self.credo.subsystems['Files'].eval2dpath, basename + '.param'))

    def do_response(self, respid):
        if respid == 1:  # execute
            self.execute_findbeam()
        if respid == Gtk.ResponseType.YES:  # save
            self.save_beampos()
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            beamposx, beamposy = self.plot2d.get_exposure()['BeamPosX'], self.plot2d.get_exposure()['BeamPosY']
            if self.credo.get_property('beamposx') != beamposx:  self.credo.set_property('beamposx', beamposx)
            if self.credo.get_property('beamposy') != beamposy:  self.credo.set_property('beamposy', beamposy)
        if respid in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.OK, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()


