from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GdkPixbuf
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
import numpy as np
from .widgets import ToolDialog
from ..hardware.subsystems import SubSystemError
from ..hardware.instruments.tmcl_motor import MotorError
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
import sastool
import os
import pkg_resources
import matplotlib
import itertools
import sasgui
import traceback

itheme = Gtk.IconTheme.get_default()
itheme.append_search_path(pkg_resources.resource_filename('saxsctrl', 'resource'))


class ScanGraph(ToolDialog):
    RESPONSE_DERIVATIVE = 1
    RESPONSE_INTEGRATE = 2
    is_recording = GObject.property(type=bool, default=False, blurb='Scan running')
    __gsignals__ = {'notify':'override'}
    def __init__(self, scan, credo, title='Scan results'):
        self._lines = []
        self._cursors = {}
        self._cursor_at = None
        ToolDialog.__init__(self, credo, title, buttons=('Close', Gtk.ResponseType.CLOSE, 'Derivative', self.RESPONSE_DERIVATIVE, 'Integrate', self.RESPONSE_INTEGRATE))
        vb = self.get_content_area()
        self.fig = Figure()
        self.figcanvas = FigureCanvasGTK3Agg(self.fig)
        hb = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, True, True, 0)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hb.pack1(vb, True, False)
        self._hb_cursor = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(self._hb_cursor, False, False, 0)
        self._hb_cursor.set_no_show_all(True)
        self._hb_motor = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(self._hb_motor, False, False, 0)
        self._hb_motor.set_no_show_all(True)

        vb.pack_start(self.figcanvas, True, True, 0)
        self.figtoolbar = NavigationToolbar2GTK3(self.figcanvas, self)
        vb.pack_start(self.figtoolbar, False, True, 0)
#        tab = Gtk.Table()
#        vb.pack_start(tab, False, True, 0)
        self.figcanvas.set_size_request(640, 480)

        b = Gtk.ToolButton(icon_name='fitpeak')
        b.set_tooltip_text('Fit a Lorentzian peak to the zoomed portion of the currently selected signal')
        self.figtoolbar.insert(b, self.figtoolbar.get_n_items() - 2)
        b.connect('clicked', self.on_fitpeak)

        self.scan = scan
        self.datacols = [c for c in self.scan.columns() if c != self.scan.get_dataname('x')]
        self.xname = self.scan.get_dataname('x')
        self.xlabel(self.xname)


        l = Gtk.Label(label='Move cursor')
        self._hb_cursor.pack_start(l, False, False, 0)
        l.show()
        self._cursor_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=Gtk.Adjustment(value=0, lower=0, upper=1, step_increment=0, page_increment=1))
        self._hb_cursor.pack_start(self._cursor_scale, True, True, 0)
        self._cursor_scale.show()
        self._cursor_scale.set_draw_value(False)
        self._cursor_scale.connect('value-changed', lambda scale:self.move_cursor(scale.get_value()))
        self._cursor_label = Gtk.Label(label='')
        self._hb_cursor.pack_start(self._cursor_label, False, False, 0)
        self._cursor_label.show()
        b = Gtk.Button('Go to min')
        self._hb_cursor.pack_start(b, False, False, 0)
        b.show()
        b.connect('clicked', lambda b: self._on_goto_min())
        b = Gtk.Button('Go to max')
        self._hb_cursor.pack_start(b, False, False, 0)
        b.show()
        b.connect('clicked', lambda b: self._on_goto_max())
        if not self.credo.offline:
            try:
                self.motor = self.credo.subsystems['Motors'].get(self.xname)
            except SubSystemError:
                pass
            else:
                b1 = Gtk.Button('Motor to cursor')
                self._hb_cursor.pack_start(b1, False, False, 0)
                b1.show()
                b2 = Gtk.Button('Motor to peak')
                self._hb_cursor.pack_start(b2, False, False, 0)
                b2.show()
                b1.connect('clicked', self._on_motor_to_cursor, b2)
                b2.connect('clicked', self._on_motor_to_peak, b1)

        ls = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_BOOLEAN, GObject.TYPE_FLOAT)
        self.scalertreeview = Gtk.TreeView(ls)
        cr = Gtk.CellRendererText()
        self.scalertreeview.append_column(Gtk.TreeViewColumn('Name', cr, text=0))
        cr = Gtk.CellRendererToggle()
        cr.set_activatable(True)
        cr.connect('toggled', self.on_cell_toggled)
        self.scalertreeview.append_column(Gtk.TreeViewColumn('Visible', cr, active=1))
        cr = Gtk.CellRendererSpin()
        cr.set_property('adjustment', Gtk.Adjustment(value=0, lower=-1e9, upper=1e9, step_increment=1, page_increment=10))
        cr.set_property('digits', 1)
        cr.set_property('editable', True)
        cr.connect('edited', self.on_cell_edited)
        tvc = Gtk.TreeViewColumn('Scaling', cr, text=2)
        tvc.set_min_width(30)
        tvc.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        self.scalertreeview.append_column(tvc)
        self.scalertreeview.set_size_request(150, -1)
        vb0 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._logy_check = Gtk.CheckButton(label='Logarithmic y')
        self._logy_check.connect('toggled', lambda cb:self.redraw_scan())
        vb0.pack_start(self._logy_check, False, False, 0)
        self._show2d_check = Gtk.CheckButton(label='Show 2D image')
        self._show2d_check.connect('toggled', lambda cb:self.redraw_scan())
        vb0.pack_start(self._show2d_check, False, False, 0)

        vb = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        hb.pack2(vb0, False, False)
        vb0.pack_start(vb, True, True, 0)
        vb.set_size_request(100, -1)
        hb.set_size_request(740, -1)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        vb.pack1(sw, True, True)
        sw.add(self.scalertreeview)
        sw = Gtk.ScrolledWindow()
        vb.pack2(sw, True, True)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.currvallabels = {}
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sw.add_with_viewport(vb)
        for col in self.scan.columns():
            f = Gtk.Frame(label=col)
            vb.pack_start(f, False, False, 0)
            self.currvallabels[col] = Gtk.Label(label='--')
            f.add(self.currvallabels[col])
        self._initialize_cursors()
        self.set_scalers(None)
        self.is_recording = False

    def _on_motor_to_cursor(self, *buttons):
        try:
            self._movement_connection = self.motor.connect('idle', self._on_motor_idle, *buttons)
            self.motor.moveto(self.scan[self.xname][self._cursor_at])
            for b in buttons:
                b.set_sensitive(False)
        except MotorError as me:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot move to cursor')
            md.set_title('Reason: ' + str(me))
            md.run()
            md.destroy()
            del md
            return
    def _on_motor_idle(self, mot, *buttons):
        for b in buttons:
            b.set_sensitive(True)
        mot.disconnect(self._movement_connection)
    def _on_motor_to_peak(self, *buttons):
        if not hasattr(self, '_lastpeakpos'):
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot move to peak')
            md.set_title('Please do a peak fit before trying to move the motor to the peak position!')
            md.run()
            md.destroy()
            del md
            return
        try:
            self._movement_connection = self.motor.connect('idle', self._on_motor_idle, *buttons)
            self.motor.moveto(float(self._lastpeakpos))
            for b in buttons:
                b.set_sensitive(False)
        except MotorError as me:
            md = Gtk.MessageDialog(transient_for=self, destroy_with_parent=True,
                                   modal=True, type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK,
                                   message_format='Cannot move to peak')
            md.format_secondary_text('Reason: ' + traceback.format_exc(me))
            md.run()
            md.destroy()
            del md
            return
        pass
    def _on_goto_min(self):
        model, iter_ = self.scalertreeview.get_selection().get_selected()
        if iter_ is None:
            return
        signalname = model[iter_][0]
        self.move_cursor(self.scan[self.xname][self.scan[signalname].argmin()])
    def _on_goto_max(self):
        model, iter_ = self.scalertreeview.get_selection().get_selected()
        if iter_ is None:
            return
        signalname = model[iter_][0]
        self.move_cursor(self.scan[self.xname][self.scan[signalname].argmax()])
    def _initialize_cursors(self):
        for col, color in itertools.izip(self.datacols, itertools.cycle(matplotlib.rcParams['axes.color_cycle'])):
            self._cursors[col] = self.gca().plot(np.nan, np.nan, 'o', markersize=10, mew=2, mfc='none', mec=color)[0]

    def do_notify(self, prop):
        if prop.name == 'is-recording':
            if not self.is_recording:
                self._hb_cursor.show_now()
                x = self.scan[self.xname]
                if not len(x):
                    return
                self._cursor_scale.set_range(x.min(), x.max())
                xwid = x.max() - x.min()
                self._cursor_scale.set_increments(xwid / (len(x) - 1.), 10 * xwid / (len(x) - 1.))
                self._cursor_scale.set_digits(3)
                self.move_cursor(x[len(x) / 2])
            else:
                self._hb_cursor.hide()

    def do_response(self, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()
        elif respid == self.RESPONSE_DERIVATIVE:
            sg = ScanGraph(self.scan.diff(), self.credo, title='Derivative of ' + self.get_title())
            sg.set_scalers([(x[0], x[1], x[2]) for x in self.scalertreeview.get_model()])
            sg.redraw_scan()
            sg.show_all()
        elif respid == self.RESPONSE_INTEGRATE:
            sg = ScanGraph(self.scan.integrate(), self.credo, title='Integrated ' + self.get_title())
            sg.set_scalers([(x[0], x[1], x[2]) for x in self.scalertreeview.get_model()])
            sg.redraw_scan()
            sg.show_all()
        return

    def move_cursor(self, to):
        """Move the cursor to the given position (update the scale and its label as well)

        to: value with respect to the x scale. Snap to the nearest point."""
        if hasattr(self, '_movecursor_noreentry'):
            return
        try:
            self._movecursor_noreentry = True
            x = self.scan[self.xname]
            desired_index = np.interp(to, x, np.arange(len(self.scan)), 0, len(self.scan) - 1)
            self._cursor_at = int(round(desired_index))
            if self._cursor_scale.get_value() != to:
                self._cursor_scale.set_value(to)
                self._cursor_label.set_label(unicode(to))
            self.redraw_scan()
        finally:
            del self._movecursor_noreentry


    def xlabel(self, *args, **kwargs):
        self.gca().set_xlabel(*args, **kwargs)
    def ylabel(self, *args, **kwargs):
        self.gca().set_ylabel(*args, **kwargs)
    def title(self, *args, **kwargs):
        self.gca().set_title(*args, **kwargs)
    def legend(self, *args, **kwargs):
        self.gca().legend(*args, **kwargs)
    def text(self, *args, **kwargs):
        self.gca().text(*args, **kwargs)
    def figtext(self, *args, **kwargs):
        self.fig.text(*args, **kwargs)
    def gca(self):
        return self.fig.gca()
    def redraw_scan(self, full=False):
        if self.scan is None:
            return
        if not len(self.scan):
            return
        mod = self.scalertreeview.get_model()
        x = self.scan[self.xname]
        if self.is_recording:
            self._cursor_at = len(x) - 1
        elif self._cursor_at is None:
            self._cursor_at = 0
        if not self._lines:
            full = True
        if full:
            self.gca().cla()
            self._initialize_cursors()
            for col, color in itertools.izip(self.datacols, itertools.cycle(matplotlib.rcParams['axes.color_cycle'])):
                try:
                    scale = [m[2] for m in mod if m[0] == col][0]
                    visible = [m[1] for m in mod if m[0] == col][0]
                except (IndexError, TypeError):
                    scale = None
                    visible = False
                if not visible:
                    self._cursors[col].set_visible(False)
                    continue
                self._cursors[col].set_visible(True)
                self._lines.extend(self.gca().plot(x, self.scan[col] * scale, '.-', color=color, label=col))
                self._cursors[col].set_xdata(x[self._cursor_at])
                self._cursors[col].set_ydata(self.scan[col][self._cursor_at] * scale)
            self.xlabel(self.xname)
#            self.fig.gca().axis('tight')
            self.fig.gca().relim()
            self.fig.gca().autoscale(True, tight=True)
        else:
            miny = np.inf
            maxy = -np.inf
            for l in self._lines:
                l.set_xdata(x)
                try:
                    scale = [m[2] for m in mod if m[0] == l.get_label()][0]
                    visible = [m[1] for m in mod if m[0] == l.get_label()][0]
                except (IndexError, TypeError):
                    scale = None
                    visible = False
                self._cursors[l.get_label()].set_visible(visible)
                if not visible: continue

                y = self.scan[l.get_label()] * scale
                l.set_ydata(y)
                if y.max() > maxy: maxy = y.max()
                if y.min() < miny: miny = y.min()
                self._cursors[l.get_label()].set_xdata(x[self._cursor_at])
                self._cursors[l.get_label()].set_ydata(y[self._cursor_at])
            dx = abs(x.max() - x.min()) * 0.01
            if dx == 0:
                dx = 0.5
            # self.fig.gca().set_xlim(x.min() - dx, x.max() + dx)
            dy = abs(maxy - miny)
            if dy == 0:
                dy = 0.5
            # self.fig.gca().axis('tight')
            self.fig.gca().relim()
            self.fig.gca().autoscale(True, tight=True)
        if self._show2d_check.get_active() and ('FSN' in self.scan.columns()):
            ssf = self.credo.subsystems['Files']
            exposure = sastool.classes.SASExposure(ssf.get_exposureformat('scn') % self.scan['FSN'][self._cursor_at], dirs=[ssf.scanpath, ssf.imagespath, ssf.parampath] + sastool.misc.find_subdirs(ssf.maskpath))
            pltwin = sasgui.PlotSASImageWindow.get_current_plot()
            pltwin.set_exposure(exposure)
            if not pltwin.is_visible():
                pltwin.show_all()

        self.legend(loc='best')
        if self._logy_check.get_active():
            self.fig.gca().set_yscale('log')
        else:
            self.fig.gca().set_yscale('linear')
        self.fig.canvas.draw()
        for c in self.currvallabels:
            self.currvallabels[c].set_label('%f' % self.scan[c][self._cursor_at])
    def set_scalers(self, scalerlist=None):
        mod = self.scalertreeview.get_model()
        mod.clear()
        if scalerlist is None:
            for name in self.scan.columns()[1:]:
                mod.append((name, True, 1.0))
        else:
            for name, visible, scaling in scalerlist:
                mod.append((name, visible, float(scaling)))
    def on_cell_edited(self, renderer, path, new_text):
        try:
            self.scalertreeview.get_model()[path][2] = float(new_text)
        except ValueError:
            pass
        else:
            self.redraw_scan()
        return True
    def on_cell_toggled(self, renderer, path):
        self.scalertreeview.get_model()[path][1] ^= True
        self.redraw_scan(full=True)
    def on_fitpeak(self, button):
        model, iter_ = self.scalertreeview.get_selection().get_selected()
        if iter_ is None:
            return
        signalname = model[iter_][0]
        scale = [m[2] for m in self.scalertreeview.get_model() if m[0] == signalname][0]
        curve = sastool.GeneralCurve(self.scan[self.xname], self.scan[signalname] * scale)
        curve = curve.trim(*(self.gca().axis()))
        try:
            if not len(curve):
                raise TypeError()
            pos, hwhm, baseline, amplitude = sastool.misc.findpeak_single(curve.x, curve.y, curve='Lorentz')
        except TypeError:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Fitting error')
            md.set_title('Please make sure you selected the correct signal for fitting.')
            md.run()
            md.destroy()
            del md
            return
        xfitted = np.linspace(curve.x.min(), curve.x.max(), 5 * len(curve.x))
        fitted = sastool.GeneralCurve(xfitted, amplitude * hwhm ** 2 / (hwhm ** 2 + (pos - xfitted) ** 2) + baseline)
        if hasattr(self, '_fittedline'):
            self._fittedline.set_xdata(fitted.x)
            self._fittedline.set_ydata(fitted.y)
        else:
            self._fittedline = fitted.plot('r-', axes=self.gca(), label='Peak of %s at: ' % signalname + str(pos))[0]
        if hasattr(self, '_peakpostext') and self._peakpostext is not None:
            self._peakpostext.set_text('Peak at: ' + str(pos))
        else:
            self._peakpostext = self.text(float(pos), curve.interpolate(float(pos)), 'Peak at: ' + str(pos), ha='left', va='top')
        self._lastpeakpos = pos
        self.fig.canvas.draw()

class ImagingGraph(ToolDialog):
    def __init__(self, scan, title='Imaging results', extent=None):
        self._axes = []
        self._extent = extent
        ToolDialog.__init__(self, None, title)
        vb = self.get_content_area()
        self.fig = Figure()
        self.figcanvas = FigureCanvasGTK3Agg(self.fig)
        hb = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, True, True, 0)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hb.pack1(vb, True, False)
        vb.pack_start(self.figcanvas, True, True, 0)
        self.figtoolbar = NavigationToolbar2GTK3(self.figcanvas, self)
        vb.pack_start(self.figtoolbar, False, True, 0)
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        self.figcanvas.set_size_request(640, 480)

        self.scan = scan
        self.datacols = self.scan.columns()[2:]
        self.x1name = self.scan.columns()[0]
        self.x2name = self.scan.columns()[1]
        self.x1label(self.x1name)
        self.x2label(self.x2name)

        ls = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_BOOLEAN, GObject.TYPE_STRING, GObject.TYPE_FLOAT)
        self.scalertreeview = Gtk.TreeView(ls)
        cr = Gtk.CellRendererText()
        self.scalertreeview.append_column(Gtk.TreeViewColumn('Name', cr, text=0))
        cr = Gtk.CellRendererToggle()
        cr.set_activatable(True)
        cr.connect('toggled', self.on_cell_toggled)
        self.scalertreeview.append_column(Gtk.TreeViewColumn('Visible', cr, active=1))
        cr = Gtk.CellRendererCombo()
        cr.connect('changed', self.on_cell_combo_selected)
        cr.set_property('has-entry', False)
        cr.set_property('editable', True)
        scalingmodel = Gtk.ListStore(GObject.TYPE_STRING)
        scalingmodel.append(('Linear',))
        scalingmodel.append(('Log',))
        scalingmodel.append(('Sqrt',))
        cr.set_property('model', scalingmodel)
        cr.set_property('text-column', 0)
        tvc = Gtk.TreeViewColumn('Scaling', cr, text=2)
        self.scalertreeview.append_column(tvc)
        cr = Gtk.CellRendererSpin()
        cr.set_property('adjustment', Gtk.Adjustment(0, -1e9, 1e9, 1, 10, 0))
        cr.set_property('digits', 1)
        cr.set_property('editable', True)
        cr.connect('edited', self.on_cell_edited)
        tvc = Gtk.TreeViewColumn('Factor', cr, text=3)
        tvc.set_min_width(60)
        tvc.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        self.scalertreeview.append_column(tvc)
        self.scalertreeview.set_size_request(150, -1)
        vb = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        hb.pack2(vb, False, False)
        vb.set_size_request(100, -1)
        hb.set_size_request(740, -1)
        vb1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vb.pack1(vb1, True, True)
        hb1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb1.pack_start(hb1, False, False, 0)
        l = Gtk.Label(label='Number of columns:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        hb1.pack_start(l, False, False, 0)
        self._ncol_sb = Gtk.SpinButton(adjustment=Gtk.Adjustment(4, 1, 100, 1, 10), digits=0)
        self._ncol_sb.set_value(2)
        self._ncol_sb.connect('value-changed', lambda sb:self.redraw_scan(True))
        hb1.pack_start(self._ncol_sb, True, True, 3)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        vb1.pack_start(sw, True, True, 0)
        sw.add(self.scalertreeview)
        sw = Gtk.ScrolledWindow()
        vb.pack2(sw, True, True)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.currvallabels = {}
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sw.add_with_viewport(vb)
        for col in self.scan.columns():
            f = Gtk.Frame(label=col)
            vb.pack_start(f, False, False, 0)
            self.currvallabels[col] = Gtk.Label(label='--')
            f.add(self.currvallabels[col])
        self.set_scalers(None)
    def do_response(self, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()
        return
    def x1label(self, *args, **kwargs):
        for ax in self._axes:
            ax.set_xlabel(*args, **kwargs)
    def x2label(self, *args, **kwargs):
        for ax in self._axes:
            ax.set_ylabel(*args, **kwargs)
    def title(self, *args, **kwargs):
        self.gcf().set_title(*args, **kwargs)
    def figtext(self, *args, **kwargs):
        self.fig.text(*args, **kwargs)
    def gcf(self):
        return self.fig
    def redraw_scan(self, full=False):
        if self.scan is None:
            return
        mod = self.scalertreeview.get_model()
        x1 = self.scan[0]
        x2 = self.scan[1]
        if not self._axes:
            full = True
        if full:
            self._axes = []
            self.gcf().clf()
            valid_cols = [c for c in self.datacols if [m for m in mod if m[0] == c]]
            self._visible_cols = [ col for col in valid_cols if [m[1] for m in mod if m[0] == col][0]]
            Nsubplotrows = len(self._visible_cols) / self._ncol_sb.get_value_as_int() + 1
            if not (len(self._visible_cols) % self._ncol_sb.get_value_as_int()):
                Nsubplotrows -= 1
            Nsubplotcols = self._ncol_sb.get_value_as_int()
            if len(self._visible_cols) < Nsubplotcols:
                Nsubplotcols = len(self._visible_cols)
            for i, col in enumerate(self._visible_cols):
                scale = [m[2] for m in mod if m[0] == col][0]
                factor = [m[3] for m in mod if m[0] == col][0]
                self._axes.append(self.gcf().add_subplot(Nsubplotrows, Nsubplotcols, i + 1))
                img = self.scan.get_image(col) * factor
                logger.debug('ImagingGraph.redraw_scan(True): column %s, image dimensions: (%d, %d). NaNs: %d' % (col, img.shape[0], img.shape[1], (-np.isfinite(img)).sum()))
                if scale.upper() == 'LOG':
                    img = np.log10(img)
                elif scale.upper() == 'SQRT':
                    img = np.sqrt(img)
                if self._extent is None:
                    extent = (x1[0], x1[-1], x2[0], x2[-1])
                else:
                    extent = self._extent
                self._axes[-1].imshow(img, interpolation='nearest', origin='lower', aspect='equal', extent=extent)
                self._axes[-1].set_title(col)
        else:
            for col, ax in zip(self._visible_cols, self._axes):
                scale = [m[2] for m in mod if m[0] == col][0]
                factor = [m[3] for m in mod if m[0] == col][0]
                img = self.scan.get_image(col) * factor
                if scale.upper() == 'LOG':
                    img = np.log10(img)
                elif scale.upper() == 'SQRT':
                    img = np.sqrt(img)
                logger.debug('ImagingGraph.redraw_scan(Fals): column %s, image dimensions: (%d, %d). NaNs: %d' % (col, img.shape[0], img.shape[1], (-np.isfinite(img)).sum()))
                ax.images[0].set_data(img)
        self.fig.canvas.draw()
        for c in self.currvallabels:
            self.currvallabels[c].set_label('%f' % self.scan[c][-1])
    def set_scalers(self, scalerlist=None):
        mod = self.scalertreeview.get_model()
        mod.clear()
        if scalerlist is None:
            for name in self.scan.columns()[2:]:
                mod.append((name, True, 'Linear', 1.0))
        else:
            for name, visible, scaling, factor in scalerlist:
                if scaling.upper().startswith('LIN'):
                    scaling = 'Linear'
                elif scaling.upper().startswith('LOG'):
                    scaling = 'Log'
                elif scaling.upper() == 'SQRT':
                    scaling = 'Sqrt'
                else:
                    raise ValueError('Invalid scaling type for column %s: %s' % (name, scaling))
                mod.append((name, visible, scaling, float(factor)))
    def on_cell_edited(self, renderer, path, new_text):
        try:
            self.scalertreeview.get_model()[path][3] = float(new_text)
        except ValueError:
            pass
        else:
            self.redraw_scan()
        return True
    def on_cell_toggled(self, renderer, path):
        self.scalertreeview.get_model()[path][1] ^= True
        self.redraw_scan(full=True)
    def on_cell_combo_selected(self, combo, path, new_iter):
        name = combo.get_property('model')[new_iter][0]
        self.scalertreeview.get_model()[path][2] = name
        self.redraw_scan(full=True)
