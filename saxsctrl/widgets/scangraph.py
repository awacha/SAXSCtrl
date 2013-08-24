from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GdkPixbuf
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
import matplotlib.pyplot as plt
import numpy as np
import sys
from .widgets import ToolDialog
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
import sastool
import os

iconfactory = Gtk.IconFactory()
for f, n in [('fitpeak.png', 'Fit peak')]:
    basename = os.path.splitext(f)[0]
    iconset = Gtk.IconSet(GdkPixbuf.Pixbuf.new_from_file(os.path.join(os.path.dirname(__file__), f)))
    iconfactory.add('saxsctrl_%s' % basename, iconset)
iconfactory.add_default()

class ScanGraph(ToolDialog):
    RESPONSE_DERIVATIVE = 1
    RESPONSE_INTEGRATE = 2
    def __init__(self, scan, title='Scan results'):
        ToolDialog.__init__(self, None, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, 'Derivative', self.RESPONSE_DERIVATIVE, 'Integrate', self.RESPONSE_INTEGRATE))
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
        
        b = Gtk.ToolButton(stock_id='saxsctrl_fitpeak')
        b.set_tooltip_text('Fit a Lorentzian peak to the zoomed portion of the currently selected signal')
        self.figtoolbar.insert(b, self.figtoolbar.get_n_items() - 2)
        b.connect('clicked', self.on_fitpeak)
        self.scan = scan
        self.datacols = [c for c in self.scan.columns() if c != self.scan.get_dataname('x')]
        self.xname = self.scan.get_dataname('x')
        self.xlabel(self.xname)
        
        ls = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_BOOLEAN, GObject.TYPE_FLOAT)
        self.scalertreeview = Gtk.TreeView(ls)
        cr = Gtk.CellRendererText()
        self.scalertreeview.append_column(Gtk.TreeViewColumn('Name', cr, text=0))
        cr = Gtk.CellRendererToggle()
        cr.set_activatable(True)
        cr.connect('toggled', self.on_cell_toggled)
        self.scalertreeview.append_column(Gtk.TreeViewColumn('Visible', cr, active=1))
        cr = Gtk.CellRendererSpin()
        cr.set_property('adjustment', Gtk.Adjustment(0, -1e9, 1e9, 1, 10, 0))
        cr.set_property('digits', 1)
        cr.set_property('editable', True)
        cr.connect('edited', self.on_cell_edited)
        tvc = Gtk.TreeViewColumn('Scaling', cr, text=2)
        tvc.set_min_width(30)
        tvc.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)     
        self.scalertreeview.append_column(tvc)
        self.scalertreeview.set_size_request(150, -1)
        vb = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        hb.pack2(vb, False, False)
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
            self.currvallabels[col] = Gtk.Label('--')
            f.add(self.currvallabels[col])
        self.set_scalers(None)
    def do_response(self, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()
        elif respid == self.RESPONSE_DERIVATIVE:
            sg = ScanGraph(self.scan.diff(), title='Derivative of ' + self.get_title())
            sg.set_scalers([(x[0], x[1], x[2]) for x in self.scalertreeview.get_model()])
            sg.redraw_scan()
            sg.show_all()
        elif respid == self.RESPONSE_INTEGRATE:
            sg = ScanGraph(self.scan.integrate(), title='Integrated ' + self.get_title())
            sg.set_scalers([(x[0], x[1], x[2]) for x in self.scalertreeview.get_model()])
            sg.redraw_scan()
            sg.show_all()
        return
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
        mod = self.scalertreeview.get_model()
        x = self.scan[self.xname]
        if not self.gca().lines:
            full = True
        if full:
            self.gca().cla()
            for col in self.datacols:
                try:
                    scale = [m[2] for m in mod if m[0] == col][0]
                    visible = [m[1] for m in mod if m[0] == col][0]
                except IndexError:
                    scale = None
                    visible = False
                if not visible: continue
                self.gca().plot(x, self.scan[col] * scale, '.-', label=col)
        else:
            miny = np.inf
            maxy = -np.inf
            for l in self.gca().lines:
                l.set_xdata(x)
                try:
                    scale = [m[2] for m in mod if m[0] == l.get_label()][0]
                    visible = [m[1] for m in mod if m[0] == l.get_label()][0]
                except IndexError:
                    scale = None
                    visible = False
                if not visible: continue
                
                y = self.scan[l.get_label()] * scale 
                l.set_ydata(y)
                if y.max() > maxy: maxy = y.max()
                if y.min() < miny: miny = y.min()
            dx = max(abs(x.max() - x.min()) * 0.05, 0.5)
            self.fig.gca().set_xlim(x.min() - dx, x.max() + dx)
            dy = max(abs(maxy - miny) * 0.05, 0.5)
            self.fig.gca().set_ylim(miny - dy, maxy + dy)
        self.legend(loc='best')
        self.fig.canvas.draw()
        for c in self.currvallabels:
            self.currvallabels[c].set_label('%f' % self.scan[c][-1])
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
        curve = sastool.GeneralCurve(self.scan[self.xname], self.scan[signalname])
        curve = curve.trim(*(self.gca().axis()))
        if not len(curve):
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Fitting error')
            md.set_title('Please make sure you selected the correct signal for fitting.')
            md.run()
            md.destroy()
            del md
            
        pos, hwhm, baseline, amplitude = sastool.misc.findpeak_single(curve.x, curve.y, curve='Lorentz')
        xfitted = np.linspace(curve.x.min(), curve.x.max(), 5 * len(curve.x))
        fitted = sastool.GeneralCurve(xfitted, amplitude * hwhm ** 2 / (hwhm ** 2 + (pos - xfitted) ** 2) + baseline)
        fitted.plot('r-', axes=self.gca(), label='Peak of %s at: ' % signalname + str(pos))
        self.text(float(pos), curve.interpolate(float(pos)), 'Peak at: ' + str(pos), ha='left', va='top')
        self.fig.canvas.draw()
        
class ImagingGraph(ToolDialog):
    def __init__(self, scan, title='Imaging results', extent=None):
        self._axes = []
        self._extent = extent
        ToolDialog.__init__(self, None, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
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
        l = Gtk.Label('Number of columns:'); l.set_alignment(0, 0.5)
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
            self.currvallabels[col] = Gtk.Label('--')
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
