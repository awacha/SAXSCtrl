from .widgets import ToolDialog, DateEntry
from gi.repository import Gtk
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3
from matplotlib.figure import Figure
import datetime

class HWLogViewer(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_HWLogViewer'
    def __init__(self, credo, title):
        ToolDialog.__init__(self, credo, title, buttons=('Close', Gtk.ResponseType.CLOSE, 'Refresh', 1))
        hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.get_content_area().pack_start(hpaned, True, True, 0)
        toolvb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hpaned.pack1(toolvb, True, False)
        figvb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hpaned.pack2(figvb, True, False)
        self._fig = Figure()
        self._figcanvas = FigureCanvasGTK3Agg(self._fig)
        self._figtoolbar = NavigationToolbar2GTK3(self._figcanvas, self)
        figvb.pack_start(self._figcanvas, True, True, 0)
        self._figcanvas.set_size_request(640, 480)
        figvb.pack_start(self._figtoolbar, False , False, 0)

        grid = Gtk.Grid()
        toolvb.pack_start(grid, False, False, 0)
        row = 0
        l = Gtk.Label(label='Equipment:')
        l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._equipment_selector = Gtk.ComboBoxText()
        for eq in credo.subsystems['Equipments'].known_equipments():
            self._equipment_selector.append_text(eq)
        self._equipment_selector.set_active(0)
        self._equipment_selector.connect('changed', lambda cbt:self._on_equipment_changed())
        grid.attach(self._equipment_selector, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Parameter:')
        l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._parameter_selector = Gtk.ComboBoxText()
        grid.attach(self._parameter_selector, 1, row, 1, 1)
        self._parameter_selector.connect('changed', lambda cbt:self._on_parameter_changed())
        row += 1

        self._starttimecheck = Gtk.CheckButton(label='Start time:')
        self._starttimecheck.set_halign(Gtk.Align.START)
        grid.attach(self._starttimecheck, 0, row, 1, 1)
        self._starttimeentry = DateEntry(orientation=Gtk.Orientation.VERTICAL)
        self._starttimeentry.set_datetime(datetime.datetime.now())
        grid.attach(self._starttimeentry, 1, row, 1, 1)
        self._starttimecheck.connect('toggled', lambda cb:(self._starttimeentry.set_sensitive(cb.get_active()), self._redraw()))
        self._starttimeentry.set_sensitive(False)
        self._starttimeentry.connect('changed', lambda te:self._redraw())
        self._starttimecheck.set_active(False)
        row += 1

        self._endtimecheck = Gtk.CheckButton(label='End time:')
        self._endtimecheck.set_halign(Gtk.Align.START)
        grid.attach(self._endtimecheck, 0, row, 1, 1)
        self._endtimeentry = DateEntry(orientation=Gtk.Orientation.VERTICAL)
        self._endtimeentry.set_datetime(datetime.datetime.now())
        grid.attach(self._endtimeentry, 1, row, 1, 1)
        self._endtimecheck.connect('toggled', lambda cb:(self._endtimeentry.set_sensitive(cb.get_active()), self._redraw()))
        self._endtimeentry.set_sensitive(False)
        self._endtimeentry.connect('changed', lambda te:self._redraw())
        self._endtimecheck.set_active(False)
        row += 1

        self._logy_checkbutton = Gtk.CheckButton(label='Logarithmic y')
        self._logy_checkbutton.set_halign(Gtk.Align.START)
        grid.attach(self._logy_checkbutton, 0, row, 2, 1)
        self._logy_checkbutton.connect('toggled', lambda cb:self._redraw())
        row += 1

        self._connectpoints_checkbutton = Gtk.CheckButton(label='Plot continuous line')
        self._connectpoints_checkbutton.set_halign(Gtk.Align.START)
        grid.attach(self._connectpoints_checkbutton, 0, row, 2, 1)
        self._connectpoints_checkbutton.connect('toggled', lambda cb:self._redraw())
        row += 1

        self._abscissa_dates_radio = Gtk.RadioButton(label='Dates on abscissa')
        self._abscissa_dates_radio.set_halign(Gtk.Align.START)
        grid.attach(self._abscissa_dates_radio, 0, row, 2, 1)
        self._abscissa_dates_radio.connect('toggled', lambda rb:(rb.get_active() and self._redraw()))
        self._abscissa_dates_radio.set_active(True)
        row += 1

        self._abscissa_linear_radio = Gtk.RadioButton.new_with_label_from_widget(self._abscissa_dates_radio, 'Linear abscissa')
        self._abscissa_linear_radio.set_halign(Gtk.Align.START)
        grid.attach(self._abscissa_linear_radio, 0, row, 2, 1)
        self._abscissa_linear_radio.connect('toggled', lambda rb:(rb.get_active() and self._redraw()))
        row += 1

        self._abscissa_logarithmic_radio = Gtk.RadioButton.new_with_label_from_widget(self._abscissa_dates_radio, 'Logarithmic abscissa')
        self._abscissa_logarithmic_radio.set_halign(Gtk.Align.START)
        grid.attach(self._abscissa_logarithmic_radio, 0, row, 2, 1)
        self._abscissa_logarithmic_radio.connect('toggled', lambda rb:(rb.get_active() and self._redraw()))
        row += 1



        self._on_equipment_changed()
        self.show_all()
    def do_response(self, respid):
        if respid == 1:
            self._on_equipment_changed()
        else:
            return ToolDialog.do_response(self, respid)
    def _on_equipment_changed(self):
        eq = self.credo.subsystems['Equipments'].get(self._equipment_selector.get_active_text())
        self._logdata = eq.load_log()
        self._parameter_selector.get_model().clear()
        for f in self._logdata.dtype.names[1:]:
            self._parameter_selector.append_text(f)
        self._parameter_selector.set_active(0)

    def _on_parameter_changed(self):
        self._redraw()

    def _redraw(self):
        if not hasattr(self, '_logdata'):
            return
        if self._parameter_selector.get_active_text() not in self._logdata.dtype.names:
            return
        ld = self._logdata
        if self._starttimecheck.get_active():
            ld = ld[ld['time'] >= self._starttimeentry.get_epoch()]
        if self._endtimecheck.get_active():
            ld = ld[ld['time'] <= self._endtimeentry.get_epoch()]
        ax = self._fig.gca()
        ax.clear()
        if self._logy_checkbutton.get_active():
            ax.set_yscale('log')
        else:
            ax.set_yscale('linear')
        if self._connectpoints_checkbutton.get_active():
            linestyle = '.-'
        else:
            linestyle = '.'
        if self._abscissa_dates_radio.get_active():
            ax.plot([datetime.datetime.fromtimestamp(t) for t in ld['time']], ld[self._parameter_selector.get_active_text()], linestyle)
            ax.xaxis_date()
            self._fig.autofmt_xdate()
        else:
            ax.plot(ld['time'] - ld['time'][0], ld[self._parameter_selector.get_active_text()], linestyle)
            if self._abscissa_linear_radio.get_active():
                ax.set_xscale('linear')
            else:
                ax.set_xscale('log')
        ax.set_ylabel(self._parameter_selector.get_active_text())

        self._figcanvas.draw()
