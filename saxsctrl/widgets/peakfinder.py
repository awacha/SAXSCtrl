from gi.repository import Gtk
from gi.repository import GObject
import sastool
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg 
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3


class PeakFinder(Gtk.Dialog):
    __gsignals__ = {'peak-found':(GObject.SignalFlags.RUN_FIRST, None, (object, object, object, object , object))}
    lastfoundpeak = None
    def __init__(self, curve, title='Find peak by fitting...', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, Gtk.STOCK_ADD, Gtk.ResponseType.APPLY)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.CLOSE)
        self.curve = curve
        vb = self.get_content_area()
        hbox = Gtk.HBox()
        vb.pack_start(hbox, True, True, 0)
        vb1 = Gtk.VBox()
        hbox.pack_start(vb1, False, True, 0)
        
        vbox_fig = Gtk.VBox()
        hbox.pack_start(vbox_fig, True, True, 0)
        self.fig = Figure(figsize=(0.2, 0.2), dpi=72)
        self.canvas = FigureCanvasGTK3Agg(self.fig)
        self.canvas.set_size_request(640, 480)
        vbox_fig.pack_start(self.canvas, True, True, 0)
        tb = NavigationToolbar2GTK3(self.canvas, vbox_fig)
        vbox_fig.pack_start(tb, False, True, 0)
    
        f = Gtk.Frame(label='Plotting')
        vb1.pack_start(f, False, True, 0)
        hb = Gtk.HBox()
        f.add(hb)
        l = Gtk.Label(label='Plot type:'); l.set_alignment(0, 0.5)
        hb.pack_start(l, False, True, 0)
        self.plottype_combo = Gtk.ComboBoxText()
        hb.pack_start(self.plottype_combo, True, True, 0)
        self.plottype_combo.append_text('plot')
        self.plottype_combo.append_text('semilogx')
        self.plottype_combo.append_text('semilogy')
        self.plottype_combo.append_text('loglog')
        self.plottype_combo.set_active(3)
        self.plottype_combo.connect('changed', self.do_replot)
        
        f = Gtk.Frame(label='Control')
        vb1.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        l = Gtk.Label(label='Peak type:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.peaktype_combo = Gtk.ComboBoxText()
        tab.attach(self.peaktype_combo, 1, 2, row, row + 1)
        self.peaktype_combo.append_text('Gaussian')
        self.peaktype_combo.append_text('Lorentzian')
        self.peaktype_combo.set_active(0)
        row += 1
        
        self.ampl_cb = Gtk.CheckButton('Amplitude:'); self.ampl_cb.set_alignment(0, 0.5)
        tab.attach(self.ampl_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.ampl_entry = Gtk.Entry()
        tab.attach(self.ampl_entry, 1, 2, row, row + 1)
        self.ampl_cb.connect('toggled', self.on_checkbutton_entry_toggled, self.ampl_entry)
        self.on_checkbutton_entry_toggled(self.ampl_cb, self.ampl_entry)
        row += 1

        self.position_cb = Gtk.CheckButton('Position:'); self.position_cb.set_alignment(0, 0.5)
        tab.attach(self.position_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.position_entry = Gtk.Entry()
        tab.attach(self.position_entry, 1, 2, row, row + 1)
        self.position_cb.connect('toggled', self.on_checkbutton_entry_toggled, self.position_entry)
        self.on_checkbutton_entry_toggled(self.position_cb, self.position_entry)
        row += 1
        
        self.sigma_cb = Gtk.CheckButton('Sigma:'); self.sigma_cb.set_alignment(0, 0.5)
        tab.attach(self.sigma_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.sigma_entry = Gtk.Entry()
        tab.attach(self.sigma_entry, 1, 2, row, row + 1)
        self.sigma_cb.connect('toggled', self.on_checkbutton_entry_toggled, self.sigma_entry)
        self.on_checkbutton_entry_toggled(self.sigma_cb, self.sigma_entry)
        row += 1

        self.offset_cb = Gtk.CheckButton('Vert. offset:'); self.offset_cb.set_alignment(0, 0.5)
        tab.attach(self.offset_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.offset_entry = Gtk.Entry()
        tab.attach(self.offset_entry, 1, 2, row, row + 1)
        self.offset_cb.connect('toggled', self.on_checkbutton_entry_toggled, self.offset_entry)
        self.on_checkbutton_entry_toggled(self.offset_cb, self.offset_entry)
        row += 1
        
        b = Gtk.Button(stock=Gtk.STOCK_EXECUTE)
        tab.attach(b, 0, 2, row, row + 1)
        b.connect('clicked', self.do_findpeak)
        
        f = Gtk.Frame(label='Peak:')
        vb1.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        l = Gtk.Label(label='Periodicity:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, 0)
        self.d_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(58.402, 0, 1e5, 0.1, 1), digits=4)
        tab.attach(self.d_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        row += 1
        
        l = Gtk.Label(label='Order:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, 0)
        self.n_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 0, 100, 1, 10), digits=0)
        tab.attach(self.n_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND, 0)
        row += 1
        
        
        f = Gtk.Frame(label='Results:')
        vb1.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        l = Gtk.Label(label='Value'); l.set_alignment(0, 0.5)
        tab.attach(l, 1, 2, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='Error'); l.set_alignment(0, 0.5)
        tab.attach(l, 2, 3, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='Amplitude:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 1, 2, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='Position:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 2, 3, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='Sigma:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 3, 4, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label(label='Vert. offset:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 4, 5, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)

        self.ampl_val_label = Gtk.Label(); self.ampl_val_label.set_alignment(0, 0.5)
        tab.attach(self.ampl_val_label, 1, 2, 1, 2)
        self.ampl_err_label = Gtk.Label(); self.ampl_err_label.set_alignment(0, 0.5)
        tab.attach(self.ampl_err_label, 2, 3, 1, 2)

        self.pos_val_label = Gtk.Label(); self.pos_val_label.set_alignment(0, 0.5)
        tab.attach(self.pos_val_label, 1, 2, 2, 3)
        self.pos_err_label = Gtk.Label(); self.pos_err_label.set_alignment(0, 0.5)
        tab.attach(self.pos_err_label, 2, 3, 2, 3)
        
        self.sigma_val_label = Gtk.Label(); self.sigma_val_label.set_alignment(0, 0.5)
        tab.attach(self.sigma_val_label, 1, 2, 3, 4)
        self.sigma_err_label = Gtk.Label(); self.sigma_err_label.set_alignment(0, 0.5)
        tab.attach(self.sigma_err_label, 2, 3, 3, 4)

        self.offset_val_label = Gtk.Label(); self.offset_val_label.set_alignment(0, 0.5)
        tab.attach(self.offset_val_label, 1, 2, 4, 5)
        self.offset_err_label = Gtk.Label(); self.offset_err_label.set_alignment(0, 0.5)
        tab.attach(self.offset_err_label, 2, 3, 4, 5)

        self.do_replot()
        vb.show_all()
    def on_checkbutton_entry_toggled(self, cb, entry):
        entry.set_sensitive(cb.get_active())
        return True
    def do_replot(self, *args):
        self.fig.gca().cla()
        func = self.curve.__getattribute__(self.plottype_combo.get_active_text())
        func(axes=self.fig.gca())
        self.fig.gca().set_xlabel(u'q (\xc5$^{-1}$)')
        self.fig.gca().set_ylabel('Intensity (arb. units)')
        self.canvas.draw()
    def do_findpeak(self, button):
        if self.peaktype_combo.get_active_text() == 'Gaussian':
            fitfunc = sastool.fitting.fitfunctions.Gaussian
        elif self.peaktype_combo.get_active_text() == 'Lorentzian':
            fitfunc = sastool.fitting.fitfunctions.Lorentzian
        else:
            raise NotImplementedError

        c = self.curve.trimzoomed()
        x = c.x
        y = c.y
        if not self.position_cb.get_active():
            self.position_entry.set_text(str(c.x[c.y == c.y.max()][0]))
        if not self.sigma_cb.get_active():
            self.sigma_entry.set_text(str(0.5 * (c.x.max() - c.x.min())))
        if not self.offset_cb.get_active():
            self.offset_entry.set_text(str(c.y.min()))
        if not self.ampl_cb.get_active():
            self.ampl_entry.set_text(str(c.y.max() - float(self.offset_entry.get_text())))
        a, x0, sigma, y0, stat, fittedcurve = self.curve.trimzoomed().fit(fitfunc, [float(x.get_text()) for x in (self.ampl_entry, self.position_entry, self.sigma_entry, self.offset_entry)])
        self.ampl_entry.set_text(str(float(a)))
        self.sigma_entry.set_text(str(float(sigma)))
        self.offset_entry.set_text(str(float(y0)))
        self.position_entry.set_text(str(float(x0)))

        self.ampl_val_label.set_text(str(float(a)))
        if isinstance(a, sastool.ErrorValue):
            self.ampl_err_label.set_text(str(a.err))
        else:
            self.ampl_err_label.set_text('--')
                                 
        self.sigma_val_label.set_text(str(float(sigma)))
        if isinstance(sigma, sastool.ErrorValue):
            self.sigma_err_label.set_text(str(sigma.err))
        else:
            self.sigma_err_label.set_text('--')

        self.pos_val_label.set_text(str(float(x0)))
        if isinstance(x0, sastool.ErrorValue):
            self.pos_err_label.set_text(str(x0.err))
        else:
            self.pos_err_label.set_text('--')
        
        self.offset_val_label.set_text(str(float(y0)))
        if isinstance(y0, sastool.ErrorValue):
            self.offset_err_label.set_text(str(y0.err))
        else:
            self.offset_err_label.set_text('--')

        fittedcurve.plot('r-', axes=self.fig.gca())
        self.lastfoundpeak = (a, x0, sigma, y0, stat)
        self.emit('peak-found', a, x0, sigma, y0, stat)
