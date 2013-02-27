import gtk

class NextFSNMonitor(gtk.Frame):
    def __init__(self, credo, label=''):
        gtk.Frame.__init__(self, label)
        self.credo = credo
        tab = gtk.Table()
        self.add(tab)
        l = gtk.Label('File format:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 0, 1, gtk.FILL, gtk.FILL)
        self.fileformat_label = gtk.Label(); self.fileformat_label.set_alignment(0, 0.5)
        tab.attach(self.fileformat_label, 1, 2, 0, 1, xpadding=10)
        l = gtk.Label('Next FSN:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 1, 2, gtk.FILL, gtk.FILL)
        self.nextfsn_label = gtk.Label(); self.nextfsn_label.set_alignment(0, 0.5)
        tab.attach(self.nextfsn_label, 1, 2, 1, 2, xpadding=10)
        self.show_all()
        self._credo_conns = []
        self._credo_conns.append(self.credo.connect_callback('files-changed', self.update_labels))
        self._credo_conns.append(self.credo.connect_callback('setup-changed', self.update_labels))
        self.update_labels()
        self.connect('destroy', self.on_destroy)
    def update_labels(self, *args):
        self.fileformat_label.set_text(self.credo.fileformat)
        self.nextfsn_label.set_text(str(self.credo.get_next_fsn()))
    def on_destroy(self, *args):
        for c in self._credo_conns:
            self.credo.disconnect_callback(c)
        del self._credo_conns
        return False
