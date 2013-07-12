from gi.repository import Gtk
from .nextfsn_monitor import NextFSNMonitor
from .widgets import ToolDialog

class InstrumentSetup(ToolDialog):
    __gsignals__ = {'response':'override'}
    def __init__(self, credo, title='Instrument parameters'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_REFRESH, Gtk.ResponseType.REJECT))
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)

        vb = self.get_content_area()
        self._tab = self.credo.create_setup_table()
        self._tab.connect('changed', lambda t, parname:self.set_response_sensitive(Gtk.ResponseType.APPLY, True))
        self._tab.connect('apply', lambda t:self.set_response_sensitive(Gtk.ResponseType.APPLY, False))
        self._tab.connect('revert', lambda t:self.set_response_sensitive(Gtk.ResponseType.APPLY, False))

        vb.pack_start(self._tab, False, True, 0)

        f = Gtk.Frame(label='Subsystems')
        vb.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        for i, ssname in enumerate(self.credo.subsystems):
            row = i / 3
            column = i % 3
            b = Gtk.Button(label=ssname)
            b.connect('clicked', lambda b, ssn:self._configure_subsystem(ssn), ssname)
            tab.attach(b, column, column + 1, row, row + 1)
        vb.show_all()
    def _configure_subsystem(self, subsystem):
        dia = self.credo.subsystems[subsystem].create_setup_dialog(parent=self, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL)
        while dia.run() not in (Gtk.ResponseType.OK, Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CANCEL):
            pass
        dia.destroy()
        del dia
    def do_response(self, respid):
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            self._tab.apply_changes()
        if respid in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.REJECT):
            self._tab.revert_changes()
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.REJECT):
            self.stop_emission('response')
        if respid in (Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()
