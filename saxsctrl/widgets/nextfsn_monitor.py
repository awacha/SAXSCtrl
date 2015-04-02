from gi.repository import Gtk
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class NextFSNMonitor(Gtk.Frame):
    __gsignals__ = {'destroy':'override'}
    def __init__(self, credo, label=''):
        Gtk.Frame.__init__(self, label=label)
        self.credo = credo
        tab = Gtk.Table()
        self.add(tab)
        l = Gtk.Label(label='File format:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        tab.attach(l, 0, 1, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.fileformat_label = Gtk.Label(); self.fileformat_label.set_halign(Gtk.Align.START); self.fileformat_label.set_valign(Gtk.Align.CENTER)
        tab.attach(self.fileformat_label, 1, 2, 0, 1, xpadding=10)
        l = Gtk.Label(label='First FSN:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        tab.attach(l, 0, 1, 1, 2, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.firstfsn_label = Gtk.Label(); self.firstfsn_label.set_halign(Gtk.Align.START); self.firstfsn_label.set_valign(Gtk.Align.CENTER)
        tab.attach(self.firstfsn_label, 1, 2, 1, 2, xpadding=10)
        l = Gtk.Label(label='Next FSN:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        tab.attach(l, 0, 1, 2, 3, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.nextfsn_label = Gtk.Label(); self.nextfsn_label.set_halign(Gtk.Align.START); self.nextfsn_label.set_valign(Gtk.Align.CENTER)
        tab.attach(self.nextfsn_label, 1, 2, 2, 3, xpadding=10)
        self._credo_conns = []
        self._credo_conns.append(self.credo.subsystems['Files'].connect('changed', self.update_labels))
        self._credo_conns.append(self.credo.subsystems['Files'].connect('new-nextfsn', self.update_labels))
        self._credo_conns.append(self.credo.subsystems['Files'].connect('new-firstfsn', self.update_labels))
        self.update_labels()
        self.show_all()
    def update_labels(self, *args):
        self.fileformat_label.set_text(self.credo.subsystems['Files'].get_fileformat())
        self.nextfsn_label.set_text(str(self.credo.subsystems['Files'].get_next_fsn()))
        self.firstfsn_label.set_text(str(self.credo.subsystems['Files'].get_first_fsn()))
    def do_destroy(self):
        logger.debug('Destroying a NextFSNMonitor instance.')
        if not hasattr(self, '_credo_conns'):
            logger.debug('No _credo_conns in NextFSNMonitor.')
            return False
        for cb in self._credo_conns:
            self.credo.subsystems['Files'].disconnect(cb)
        self._credo_conns = []
        logger.debug('Returning from NextFSNMonitor.do_destroy()')
        return True
