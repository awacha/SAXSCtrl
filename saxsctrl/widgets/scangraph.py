from gi.repository import Gtk
from gi.repository import GObject
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
import matplotlib.pyplot as plt
import numpy as np
import sys

class ScanGraph(Gtk.Dialog):
    def __init__(self, scan, title='Scan results', parent=None, flags=0, buttons=()):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        vb = self.get_content_area()
        self.fig = Figure()
        self.figcanvas = FigureCanvasGTK3Agg(self.fig)
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vb.pack_start(hb, True, True, 0)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hb.pack_start(vb, True, True, 0)
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
        
        ls = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_FLOAT)
        self.scalertreeview = Gtk.TreeView(ls)
        cr = Gtk.CellRendererText()
        self.scalertreeview.append_column(Gtk.TreeViewColumn('Name', cr, text=0))
        cr = Gtk.CellRendererSpin()
        cr.set_property('adjustment', Gtk.Adjustment(0, -1e9, 1e9, 1, 10, 0))
        cr.set_property('digits', 1)
        cr.set_property('editable', True)
        cr.connect('edited', self.on_cell_edited)
        tvc = Gtk.TreeViewColumn('Scaling', cr, text=1)
        tvc.set_min_width(30)
        tvc.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)     
        self.scalertreeview.append_column(tvc)
        self.scalertreeview.set_size_request(150, -1)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hb.pack_start(vb, False, False, 0)
        vb.pack_start(self.scalertreeview, True, True, 0)
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
    def redraw_scan(self):
        if self.scan is None:
            return
        mod = self.scalertreeview.get_model()
        x = self.scan[self.xname]
        if not self.gca().lines:
            for col in self.datacols:
                try:
                    scale = [m[1] for m in mod if m[0] == col][0]
                except IndexError:
                    scale = None
                if scale is None: continue
                self.gca().plot(x, self.scan[col] * scale, '.-', label=col)
        else:
            miny = np.inf
            maxy = -np.inf
            for l in self.gca().lines:
                l.set_xdata(x)
                try:
                    scale = [m[1] for m in mod if m[0] == l.get_label()][0]
                except IndexError:
                    scale = None
                if scale is None: continue
                
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
    def set_scalers(self, scalerlist):
        mod = self.scalertreeview.get_model()
        mod.clear()
        for name, scaling in scalerlist:
            if scaling is not None:
                mod.append((name, float(scaling)))
    def on_cell_edited(self, renderer, path, new_text):
        self.scalertreeview.get_model()[path][1] = float(new_text)
        self.redraw_scan()
        return True
