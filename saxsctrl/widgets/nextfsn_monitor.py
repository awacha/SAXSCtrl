from gi.repository import Gtk

class NextFSNMonitor(Gtk.Frame):
    def __init__(self, credo, label=''):
        Gtk.Frame.__init__(self, label=label)
        self.credo = credo
        tab = Gtk.Table()
        self.add(tab)
        l = Gtk.Label(label='File format:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.fileformat_label = Gtk.Label(); self.fileformat_label.set_alignment(0, 0.5)
        tab.attach(self.fileformat_label, 1, 2, 0, 1, xpadding=10)
        l = Gtk.Label(label='First FSN:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 1, 2, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.firstfsn_label = Gtk.Label(); self.firstfsn_label.set_alignment(0, 0.5)
        tab.attach(self.firstfsn_label, 1, 2, 1, 2, xpadding=10)
        l = Gtk.Label(label='Next FSN:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 2, 3, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.nextfsn_label = Gtk.Label(); self.nextfsn_label.set_alignment(0, 0.5)
        tab.attach(self.nextfsn_label, 1, 2, 2, 3, xpadding=10)
        self.show_all()
        self._credo_conns = []
        self._credo_conns.append(self.credo.subsystems['Files'].connect('changed', self.update_labels))
        self._credo_conns.append(self.credo.subsystems['Files'].connect('new-nextfsn', self.update_labels))
        self._credo_conns.append(self.credo.subsystems['Files'].connect('new-firstfsn', self.update_labels))
        self.update_labels()
        self.connect('destroy', self.on_destroy)
    def update_labels(self, *args):
        self.fileformat_label.set_text(self.credo.subsystems['Files'].get_fileformat())
        self.nextfsn_label.set_text(str(self.credo.subsystems['Files'].get_next_fsn()))
        self.firstfsn_label.set_text(str(self.credo.subsystems['Files'].get_first_fsn()))
    def on_destroy(self, *args):
        for cb in self._credo_conns:
            self.credo.subsystems['Files'].disconnect(cb)
        del self._credo_conns
        return False
