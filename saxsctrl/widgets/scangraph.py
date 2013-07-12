from gi.repository import Gtk
from gi.repository import GObject
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
import matplotlib.pyplot as plt
import numpy as np
import sys
from .widgets import ToolDialog

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
            sg.redraw_scan()
            sg.show_all()
        elif respid == self.RESPONSE_INTEGRATE:
            sg = ScanGraph(self.scan.integrate(), title='Integrated ' + self.get_title())
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
