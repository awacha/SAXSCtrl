from gi.repository import Gtk
from gi.repository import GObject

class FileEntryWithButton(Gtk.Box):
    _filechooserdialog = None
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ())}
    def __init__(self, dialogtitle='Open file...', dialogaction=Gtk.FileChooserAction.OPEN, fileformats=[], default_folder=None):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL)
        self._entry = Gtk.Entry()
        self.pack_start(self._entry, True, True, 0)
        self._button = Gtk.Button(stock=Gtk.STOCK_OPEN)
        self.pack_start(self._button, False, True, 0)
        self._button.connect('clicked', self._on_button)
        fileformats = fileformats + [('All files', '*')]
        
        self._filechooserdialog = Gtk.FileChooserDialog(dialogtitle, None, dialogaction, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        if default_folder is not None:
            self._filechooserdialog.set_current_folder(default_folder)
        for i, f in enumerate(fileformats):
            ff = Gtk.FileFilter()
            ff.set_name(f[0])
            if isinstance(f[1], basestring):
                ff.add_pattern(f [1])
            else:
                for p in f[1]:
                    ff.add_pattern(p)
            self._filechooserdialog.add_filter(ff)
            if not i:
                self._filechooserdialog.set_filter(ff)
        self._entry.connect('changed', lambda e:self.emit('changed'))
    def get_path(self):
        return self._entry.get_text()
    get_filename = get_path
    def _on_button(self, button):
        if self._entry.get_text():
            self._filechooserdialog.set_filename(self._entry.get_text())
        response = self._filechooserdialog.run()
        if response == Gtk.ResponseType.OK:
            self._entry.set_text(self._filechooserdialog.get_filename())
        self._filechooserdialog.hide()
        return True
    def set_filename(self, filename):
        self._entry.set_text(filename)
        if filename:
            self._filechooserdialog.set_filename(filename)
        
