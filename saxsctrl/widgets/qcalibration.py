from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
import numpy as np

from matplotlib.backends.backend_gtk3agg import Figure, FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
import sastool
import sasgui

from .exposureselector import ExposureSelector
from .peakfinder import PeakFinder
from .widgets import ToolDialog, ErrorValueEntry


class DistCalibrationDialog(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_DistCalibrationDialog'

    def __init__(self, credo, title='Sample-to-detector distance calibration'):
        ToolDialog.__init__(self, credo, title=title, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        vb = self.get_content_area()
        f = Gtk.Expander(label='Exposure')
        vb.pack_start(f, False, False, 0)
        es = ExposureSelector(credo)
        es.connect('open', self.do_load_exposure)
        f.add(es)
        f.set_expanded(True)
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, True, True, 0)
        vb1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hb.pack_start(vb1, False, False, 0)
        hb1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb1.pack_start(hb1, True, True, 0)

        self._treemodel = Gtk.ListStore(GObject.TYPE_PYOBJECT,  # ErrorValue of uncalibrated data (pixel/radius)
                                        GObject.TYPE_PYOBJECT,  # ErrorValue of calibrated data (q)
                                        GObject.TYPE_STRING,  # String representation of uncalibrated data
                                        GObject.TYPE_STRING)  # String representation of calibrated data
        self._treeview = Gtk.TreeView(self._treemodel)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        hb1.pack_start(sw, True, True, 0)
        sw.add(self._treeview)
        self._treeview.append_column(Gtk.TreeViewColumn('Pixel', Gtk.CellRendererText(), text=2))
        self._treeview.append_column(Gtk.TreeViewColumn('q', Gtk.CellRendererText(), text=3))
        self._treeview.set_rules_hint(True)
        self._treeview.set_headers_visible(True)
        self._treeview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self._treeview.set_size_request(150, -1)
        tv_buttonbox = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL)
        tv_buttonbox.set_layout(Gtk.ButtonBoxStyle.START)
        hb1.pack_start(tv_buttonbox, False, False, 0)
        b = Gtk.Button(label='Add', image=Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.BUTTON))
        tv_buttonbox.add(b)
        b.connect('clicked', self._treeview_add)
        b = Gtk.Button(label='Remove', image=Gtk.Image.new_from_icon_name('list-remove', Gtk.IconSize.BUTTON))
        tv_buttonbox.add(b)
        b.connect('clicked', self._treeview_remove)
        b = Gtk.Button(label='Clear', image=Gtk.Image.new_from_icon_name('edit-clear', Gtk.IconSize.BUTTON))
        tv_buttonbox.add(b)
        b.connect('clicked', self._treeview_clear)
        b = Gtk.Button(label='Save As', image=Gtk.Image.new_from_icon_name('document-save-as', Gtk.IconSize.BUTTON))
        tv_buttonbox.add(b)
        b.connect('clicked', self._treeview_saveas)
        b = Gtk.Button(label='Open', image=Gtk.Image.new_from_icon_name('document-open', Gtk.IconSize.BUTTON))
        tv_buttonbox.add(b)
        b.connect('clicked', self._treeview_open)
        b = Gtk.Button(label='Refresh', image=Gtk.Image.new_from_icon_name('view-refresh', Gtk.IconSize.BUTTON))
        tv_buttonbox.add(b)
        b.connect('clicked', self._treeview_refresh)
        self._findpeakbutton = Gtk.Button(label='Find peaks',
                                          image=Gtk.Image.new_from_icon_name('edit-find', Gtk.IconSize.BUTTON))
        tv_buttonbox.add(self._findpeakbutton)
        self._findpeakbutton.connect('clicked', self._treeview_findpeak)
        self._findpeakbutton.set_sensitive(False)

        b = Gtk.Button(label='Export to HTML')
        tv_buttonbox.add(b)
        b.connect('clicked', self._treeview_export_html)


        vb2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hb.pack_start(vb2, True, True, 0)
        self._fig = Figure()
        self._canvas = FigureCanvasGTK3Agg(self._fig)
        self._canvas.set_size_request(400, 300)
        vb2.pack_start(self._canvas, True, True, 0)
        self._figtoolbar = NavigationToolbar2GTK3(self._canvas, None)
        vb2.pack_start(self._figtoolbar, False, False, 0)
        grid = Gtk.Grid()
        vb.pack_start(grid, False, False, 0)

        l = Gtk.Label(label='Wavelength:');
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, 0, 1, 1)
        self._wavelength_entry = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0.15418, lower=0, upper=100, step_increment=0.01, page_increment=0.1, page_size=0.1),
            digits=5)
        self._wavelength_entry.set_value(0.15418)
        grid.attach(self._wavelength_entry, 1, 0, 1, 1)

        l = Gtk.Label(label='Pixel size:');
        l.set_alignment(0, 0.5)
        grid.attach(l, 2, 0, 1, 1)
        self._pixelsize_entry = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0.172, lower=0, upper=100, step_increment=0.01, page_increment=0.1),
            digits=3)
        self._pixelsize_entry.set_value(0.172)
        grid.attach(self._pixelsize_entry, 3, 0, 1, 1)

        l = Gtk.Label(label='Coefficient of determination (R2) of the fit:');
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, 1, 1, 1)
        self._r2_label = Gtk.Label(label='N/A')
        grid.attach(self._r2_label, 1, 1, 1, 1)

        l = Gtk.Label(label='Reduced Chi2 of the fit:')
        l.set_alignment(0, 0.5)
        grid.attach(l, 2, 1, 1, 1)
        self._chi2_label = Gtk.Label(label='N/A')
        grid.attach(self._chi2_label, 3, 1, 1, 1)

        l = Gtk.Label(label='Sample-to-detector distance:');
        l.set_alignment(0, 0.5)
        grid.attach(l, 0, 2, 1, 1)
        self._sddist_label = Gtk.Label(label='N/A')
        grid.attach(self._sddist_label, 1, 2, 1, 1)


    def do_response(self, respid):
        if respid in (Gtk.ResponseType.OK, Gtk.ResponseType.APPLY) and hasattr(self, '_dist'):
            self.credo.dist = self._dist.val
            self.credo.dist_error = self._dist.err
        if respid in (Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL):
            ToolDialog.do_response(self, respid)
        return

    def do_load_exposure(self, exposureselector, exposure):
        try:
            self._rad = exposure.radial_average(pixel=True)
            del exposure
            self._findpeakbutton.set_sensitive(True)
        except sastool.classes.SASExposureException:
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                   Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Please load a mask!')
            md.run()
            md.destroy()
            del md

    def _treeview_add(self, button=None):
        self._treemodel.append((sastool.ErrorValue(0, 0), sastool.ErrorValue(0, 0), '0', '0'))

    def _treeview_remove(self, button=None):
        model, selection = self._treeview.get_selection().get_selected_rows()
        for row in reversed(selection):
            model.remove(self._treemodel.get_iter(row))
        self._treeview_refresh()

    def _treeview_clear(self, button=None):
        self._treemodel.clear()

    def _treeview_saveas(self, button=None):
        pass

    def _treeview_open(self, button=None):
        pass

    def _treeview_export_html(self, button=None):
        htmlout = '<table border="1" cellpadding="1" cellspacing="1" style="width:500px">\n'
        htmlout = htmlout + '  <tr>\n'
        htmlout = htmlout + '    <th>Uncalibrated values (pixel)</th>\n'
        htmlout = htmlout + '    <th>Calibrated values (1/nm)</th>\n'
        htmlout = htmlout + '    <th>Determined from (calibration sample, peak nr.)</th>\n'
        htmlout = htmlout + '  </tr>\n'
        for uncal, cal, struncal, strcal in self._treemodel:
            htmlout = htmlout + '  <tr>\n'
            htmlout = htmlout + '    <td>%s</td>\n    <td>%s</td>\n    <td>...</td>\n' % (uncal.tostring(extra_digits=1), cal.tostring(extra_digits=1))
            htmlout = htmlout + '  </tr>\n'
        htmlout = htmlout + '</table>\n'
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(htmlout, -1)

    def _treeview_refresh(self, button=None):
        self._fig.clear()
        axes = self._fig.add_subplot(1, 1, 1)
        x = np.array([r[0].val for r in self._treemodel])
        y = np.array([r[1].val for r in self._treemodel])
        dx = np.array([r[0].err for r in self._treemodel])
        dy = np.array([r[1].err for r in self._treemodel])
        axes.errorbar(x, y, dx, dy, 'bo', label='Calibration points')

        def qfrompix(pix, pixelsize, wavelength, dist):
            return 4 * np.pi * np.sin(0.5 * np.arctan(pixelsize * pix / dist)) / wavelength
        if len(x) > 1:

            dist, stat = sastool.easylsq.nonlinear_leastsquares(x, y, dy, qfrompix,
                                                                [sastool.FixedParameter(self._pixelsize_entry.get_value()),
                                                                 sastool.FixedParameter(self._wavelength_entry.get_value()),
                                                                 100.
                                                                ])[2:]
            pixscale = np.linspace(x.min(), x.max(), 100)
            self._r2_label.set_label(str(stat['R2']))
            self._chi2_label.set_label(str(stat['Chi2_reduced']))
        else:
            q = sastool.ErrorValue(y[0], dy[0])
            pix = sastool.ErrorValue(x[0], dx[0])
            dist = self._pixelsize_entry.get_value() * pix / np.tan(np.arcsin(q * self._wavelength_entry.get_value() / (4 * np.pi)) * 2)
            pixscale = np.linspace(0, float(pix), 100)
            self._r2_label.set_label('N/A')
            self._chi2_label.set_label('N/A')
        self._sddist_label.set_label(dist.tostring(extra_digits=3))
        self._dist = dist
        axes.plot(pixscale, qfrompix(pixscale, self._pixelsize_entry.get_value(), self._wavelength_entry.get_value(), dist), 'r-', label='Calibration curve from LSQ fit')
        axes.set_xlabel('Pixels')
        axes.set_ylabel('q')
        axes.legend(loc='best')
        self._fig.canvas.draw()

    def _treeview_findpeak(self, button=None):
        pf = PeakFinder(self._rad)
        res = Gtk.ResponseType.APPLY
        conn = pf.connect('peak-found', self._on_peak_found)
        try:
            res = pf.run()
        finally:
            pf.disconnect(conn)
        pf.destroy()

    def _on_peak_found(self, peakfinder, a, x0, sigma, y0, stat, cal):
        if not isinstance(cal, sastool.ErrorValue):
            uncal = sastool.ErrorValue(cal)
        self._treemodel.append((x0, cal, unicode(x0), unicode(cal)))
        self._treeview_refresh()


class QCalibrationDialog(sasgui.QCalibrator):
    __gsignals__ = {'response': 'override'}
    __gtype_name__ = 'SAXSCtrl_QCalibrationDialog'

    def __init__(self, credo, title='Q calibration'):
        sasgui.QCalibrator.__init__(self, title, flags=0, buttons=(
            Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CLOSE,
            Gtk.ResponseType.CLOSE,))
        self.set_default_response(Gtk.ResponseType.CLOSE)
        self.credo = credo
        self.connect('notify::dist', lambda obj, prop: self.do_changed())
        vb = self.get_content_area()

        f = Gtk.Expander(label='Exposure:')
        vb.pack_start(f, False, False, 0)
        vb.reorder_child(f, 0)
        es = ExposureSelector(credo)
        es.connect('open', self.do_load_exposure)
        f.add(es)
        f.set_expanded(True)

        self.wavelength = 0.15418
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
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                   Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Please load a mask!')
            md.run()
            md.destroy()
            del md

    def do_find_peak(self, button):
        pf = PeakFinder(self._rad)
        res = Gtk.ResponseType.APPLY
        while res not in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            res = pf.run()
            if res == Gtk.ResponseType.APPLY:
                self.calibrationpairs.append((
                    float(pf.lastfoundpeak[1]),
                    float(2 * np.pi * pf.n_entry.get_value_as_int() / pf.d_entry.get_value())))
                self.update_extended_params()
                self.redraw()
        pf.destroy()

    def to_credo(self):
        self.get_widget_for_response(Gtk.ResponseType.APPLY).set_sensitive(False)
        for prop in ['dist', 'pixelsize', 'wavelength']:
            if self.credo.get_property(prop) != self.get_property(prop):
                self.credo.set_property(prop, self.get_property(prop))

    def do_response(self, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.OK):
            self.destroy()
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            self.to_credo()
        return
