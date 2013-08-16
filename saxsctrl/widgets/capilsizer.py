from gi.repository import Gtk
from .widgets import ToolDialog
from .samplesetup import SampleSelector
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
import numpy as np
import sastool


class CapilSizer(ToolDialog):
    def __init__(self, credo, title='Find position and thickness of capillaries'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self._poi = {}
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.get_content_area().pack_start(paned, True, True, 0)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        paned.pack1(vbox, True, False)
        
        self.fig = Figure()
        self.figcanvas = FigureCanvasGTK3Agg(self.fig)
        self.figtoolbar = NavigationToolbar2GTK3(self.figcanvas, self)
        figvbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        paned.pack2(figvbox, True, True)
        figvbox.pack_start(self.figcanvas, True, True, 0)
        figvbox.pack_start(self.figtoolbar, False, False, 0)
        self.figcanvas.set_size_request(640, 480)
        
        tab = Gtk.Table()
        vbox.pack_start(tab, False, False, 0)
        row = 0
        
        l = Gtk.Label('Sample name:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._sampleselector = SampleSelector(self.credo, False, shortnames=True)
        tab.attach(self._sampleselector, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label('Peak function:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._peakfunction_combo = Gtk.ComboBoxText()
        tab.attach(self._peakfunction_combo, 1, 2, row, row + 1)
        self._peakfunction_combo.append_text('Lorentz')
        self._peakfunction_combo.append_text('Gauss')
        self._peakfunction_combo.set_active(0)
        row += 1
        
        l = Gtk.Label('Scan number:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._scannumber_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 0, 1e6, 1, 10), digits=0)
        tab.attach(self._scannumber_entry, 1, 2, row, row + 1)
        self._scannumber_entry.connect('value-changed', self._on_scannumber_changed)
        row += 1
        
        l = Gtk.Label('Signal name:')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._signalname_combo = Gtk.ComboBoxText()
        tab.attach(self._signalname_combo, 1, 2, row, row + 1)
        self._signalname_combo.connect('changed', self._on_signalname_changed)
        row += 1
        
        self._plotnormal_radio = Gtk.RadioButton(label='Plot signal')
        tab.attach(self._plotnormal_radio, 0, 2, row, row + 1)
        row += 1
        self._plotderivative_radio = Gtk.RadioButton.new_with_label_from_widget(self._plotnormal_radio, 'Plot derivative')
        tab.attach(self._plotderivative_radio, 0, 2, row, row + 1)
        row += 1
        self._plotnormal_radio.set_active(True)
        
        self._plotnormal_radio.connect('toggled', lambda rb: self._on_signalname_changed(self._signalname_combo))
        
        hs = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        hs.set_size_request(-1, 20)
        vbox.pack_start(hs, False, False, 0)
        
        tab = Gtk.Table()
        vbox.pack_start(tab, False, False, 0)
        row = 0

        l = Gtk.Label('Left inflexion point')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._leftpoi_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e6, 1e6, 1, 10), digits=4)
        tab.attach(self._leftpoi_entry, 1, 2, row, row + 1)
        self._leftpoi_entry.connect('value-changed', lambda sb:self.recalculate())
        b = Gtk.Button(label='Fit')
        tab.attach(b, 2, 3, row, row + 1)
        b.connect('clicked', lambda button, targetentry, name: self._fitpeak(targetentry, name), self._leftpoi_entry, 'left')
        row += 1
        
        l = Gtk.Label('Right inflexion point')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._rightpoi_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e6, 1e6, 1, 10), digits=4)
        tab.attach(self._rightpoi_entry, 1, 2, row, row + 1)
        self._rightpoi_entry.connect('value-changed', lambda sb:self.recalculate())
        b = Gtk.Button(label='Fit')
        tab.attach(b, 2, 3, row, row + 1)
        b.connect('clicked', lambda button, targetentry, name: self._fitpeak(targetentry, name), self._rightpoi_entry, 'right')
        row += 1

        l = Gtk.Label('Thickness (cm):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._thickness_label = Gtk.Label('--')
        tab.attach(self._thickness_label, 1, 2, row, row + 1)
        row += 1
        l = Gtk.Label('Position (mm):')
        l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._position_label = Gtk.Label('--')
        tab.attach(self._position_label, 1, 2, row, row + 1)
        row += 1
        b = Gtk.Button(stock=Gtk.STOCK_SAVE)
        tab.attach(b, 2, 3, row - 2, row, Gtk.AttachOptions.FILL)
        b.connect('clicked', lambda button: self.save())
        
    def _on_scannumber_changed(self, spinbutton):
        try:
            self._scan = self.credo.subsystems['Files'].scanfile.get_scan(spinbutton.get_value_as_int())
        except ValueError as exc:
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'No such scan: %d' % spinbutton.get_value_as_int())
            md.format_secondary_text(exc.message)
            md.run()
            md.destroy()
            del md
            return
        prevsel = self._signalname_combo.get_active_text()
        self._signalname_combo.get_model().clear()
        for i, col in enumerate(self._scan.columns()[1:]):
            self._signalname_combo.append_text(col)
            if col == prevsel:
                self._signalname_combo.set_active(i)
        if prevsel is None:
            self._signalname_combo.set_active(0)
        self._on_signalname_changed(self._signalname_combo)
        return True
    
    def _on_signalname_changed(self, combobox):
        try:
            x = self._scan[0]
            y = self._scan[self._signalname_combo.get_active_text()]
        except (KeyError, AttributeError, TypeError) as exc:
            print exc.message
            return
        self.fig.clf()
        ax = self.fig.gca()
        if self._plotnormal_radio.get_active():
            self._x = x
            self._y = y
            ax.set_ylabel(self._signalname_combo.get_active_text())
        else:
            self._x = 0.5 * (x[1:] + x[:-1])
            self._y = np.diff(y)
            ax.set_ylabel('Derivative of ' + self._signalname_combo.get_active_text())
        ax.plot(self._x, self._y, '.-')
        ax.set_xlabel(self._scan.columns()[0])
        self.figcanvas.draw()
        return True
    def recalculate(self):
        if not (('left' in self._poi) and ('right' in self._poi)):
            return True
        self._thickness_label.set_label(str(0.1 * np.abs(self._poi['right'] - self._poi['left'])))
        self._position_label.set_label(str(0.5 * (self._poi['left'] + self._poi['right'])))
        return True
    def save(self):
        self._sampleselector.get_sample().thickness = 0.1 * np.abs(self._poi['right'] - self._poi['left'])
        if self._scan.columns()[0] == self.credo.subsystems['Samples'].motor_samplex:
            x_or_y = True
        elif self._scan.columns()[0] == self.credo.subsystems['Samples'].motor_sampley:
            x_or_y = False
        else:
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                   Gtk.MessageType.QUESTION, Gtk.ButtonsType.NONE,
                                   'Cannot determine automatically if this is the X or Y position.')
            md.format_secondary_text('Which sample position did we determine just now?')
            md.add_button('X', 1)
            md.add_button('Y', 2)
            md.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
            res = md.run()
            if res == 1: x_or_y = True
            elif res == 2: x_or_y = False
            else: x_or_y = None
            md.destroy()
            del md
        if x_or_y is None:
            mesg = ''
        elif x_or_y:
            self._sampleselector.get_sample().positionx = 0.5 * (self._poi['left'] + self._poi['right'])
            mesg = 'and X position'
        else:
            self._sampleselector.get_sample().positiony = 0.5 * (self._poi['left'] + self._poi['right'])
            mesg = 'and Y position'
        self.credo.subsystems['Samples'].save()
        md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                               Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                               'Thickness ' + mesg + ' updated in sample ' + str(self._sampleselector.get_sample()) + '.')
        if not self.credo.offline:
            md.format_secondary_text('Sample information was also saved to %s' % self.credo.subsystems['Samples'].configfile)
        else:
            md.format_secondary_markup('However, this information <b>WAS NOT SAVED</b> to %s, since we are in offline mode.' % self.credo.subsystems['Samples'].configfile)
        md.run()
        md.destroy()
        del md
            
    def _fitpeak(self, targetentry, name):
        limits = self.fig.gca().axis()
        idx = (self._x >= limits[0]) & (self._x <= limits[1]) & (self._y >= limits[2]) & (self._y <= limits[3])
        self._poi[name], hwhm, baseline, amplitude = sastool.findpeak_single(self._x[idx], self._y[idx], curve=self._peakfunction_combo.get_active_text())
        targetentry.set_value(self._poi[name])
        if self._peakfunction_combo.get_active_text().upper().startswith('GAUSS'):
            yfit = amplitude * np.exp(0.5 * (self._x[idx] - self._poi[name]) ** 2 / hwhm ** 2) + baseline
        else:
            yfit = amplitude * hwhm ** 2 / (hwhm ** 2 + (self._poi[name] - self._x[idx]) ** 2) + baseline
        self.fig.gca().plot(self._x[idx], yfit)
        self.fig.gca().text(float(self._poi[name]), float(amplitude + baseline), 'Peak at ' + str(self._poi[name]), ha='left', va='bottom')
        self.figcanvas.draw()
        self.recalculate()
