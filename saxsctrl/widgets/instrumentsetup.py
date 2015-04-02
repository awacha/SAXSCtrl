from gi.repository import Gtk
from .widgets import ToolDialog
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class InstrumentSetup(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_InstrumentSetup'
    __gsignals__ = {'response': 'override'}

    def __init__(self, credo, title='Instrument parameters'):
        ToolDialog.__init__(
            self, credo, title, buttons=(
                'OK', Gtk.ResponseType.OK, 'Apply',
                Gtk.ResponseType.APPLY, 'Cancel',
                Gtk.ResponseType.CANCEL, 'Refresh',
                Gtk.ResponseType.REJECT))
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)

        vb = self.get_content_area()
        self._tab = self.credo.create_setup_table()
        self._tabconn = [self._tab.connect(
            'changed', lambda t, parname:self.set_response_sensitive(
                   Gtk.ResponseType.APPLY, True)),
            self._tab.connect(
                'apply', lambda t:self.set_response_sensitive(
                    Gtk.ResponseType.APPLY, False)),
            self._tab.connect('revert', lambda t:self.set_response_sensitive(
                Gtk.ResponseType.APPLY, False))]

        vb.pack_start(self._tab, False, True, 0)

        vb.show_all()

    def do_response(self, respid):
        logger.debug('InstrumentSetup.do_response(%s)' % (str(respid)))
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            self._tab.apply_changes()
        if respid in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT,
                      Gtk.ResponseType.REJECT):
            self._tab.revert_changes()
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.REJECT):
            self.stop_emission('response')
        if respid in (Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL,
                      Gtk.ResponseType.DELETE_EVENT):
            self.destroy()

    def do_destroy(self):
        if hasattr(self, '_tabconn'):
            for c in self._tabconn:
                self._tab.disconnect(c)
            del self._tabconn
