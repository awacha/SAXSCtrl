import gtk
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtkagg import NavigationToolbar2GTKAgg, FigureCanvasGTKAgg
import matplotlib.pyplot as plt
import numpy as np

class ScanGraph(gtk.Dialog):
    def __init__(self, title='Scan results', parent=None, flags=0, buttons=()):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        vb = self.get_content_area()
        self.fig = Figure()
        self.figcanvas = FigureCanvasGTKAgg(self.fig)
        vb.pack_start(self.figcanvas)
        self.figtoolbar = NavigationToolbar2GTKAgg(self.figcanvas, self)
        vb.pack_start(self.figtoolbar, False)
        tab = gtk.Table()
        vb.pack_start(tab, False)
        self.figcanvas.set_size_request(640, 480)
        row = 0
    def xlabel(self, *args, **kwargs):
        self.fig.gca().set_xlabel(*args, **kwargs)
    def ylabel(self, *args, **kwargs):
        self.fig.gca().set_ylabel(*args, **kwargs)
    def title(self, *args, **kwargs):
        self.fig.gca().set_title(*args, **kwargs)
    def legend(self, *args, **kwargs):
        self.fig.gca().legend(*args, **kwargs)
    def text(self, *args, **kwargs):
        self.fig.gca().text(*args, **kwargs)
    def figtext(self, *args, **kwargs):
        self.fig.text(*args, **kwargs)
    def add_datapoint(self, x, y):
        if not self.fig.gca().lines:
            self.set_data([x], [y])
        else:
            x = np.concatenate((self.fig.gca().lines[0].get_xdata(), np.array([x])))
            y = np.concatenate((self.fig.gca().lines[0].get_ydata(), np.array([y])))
            self.set_data(x, y)
            self.fig.gca().lines[0].set_xdata(x)
            self.fig.gca().lines[0].set_ydata(y)
            self.fig.gca().set_xlim(x.min(), x.max())
            self.fig.gca().set_ylim(y.min(), y.max())
            self.fig.canvas.draw()
    def set_data(self, x, y):
        if not self.fig.gca().lines:
            self.fig.gca().plot(x, y, 'bo-')
        else:
            self.fig.gca().lines[0].set_xdata(x)
            self.fig.gca().lines[0].set_ydata(y)
            self.fig.gca().set_xlim(x.min(), x.max())
            self.fig.gca().set_ylim(y.min(), y.max())
            self.fig.canvas.draw()
                             
