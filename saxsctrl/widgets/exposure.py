from gi.repository import Gtk
from gi.repository import GObject
from .spec_filechoosers import MaskEntryWithButton

class ExposureFrame(Gtk.Frame):
    __gsignals__ = {'started':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'image':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'fail':(GObject.SignalFlags.RUN_FIRST, None, (str,))}
    def __init__(self, credo, fixedformat=None):
        Gtk.Frame.__init__(self, label='Expose...')
        self.credo = credo
        tab = Gtk.Table()
        self.add(tab)
        row = 0
        
            
        l = Gtk.Label('File format:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        if fixedformat is not None:
            self._fileformat_entry = Gtk.ComboBoxText.new_with_entry()
            for i, f in enumerate(self.credo.subsystems['Files'].formats()):
                self._fileformat_entry.append_text(f)
                if f == self.credo.subsystems['Files'].filebegin:
                    self._fileformat_entry.set_active(i)
            self._fileformat_entry.connect('changed', lambda ffe:self._fileformat_entry_changed())
            self.credo.subsystems['Files'].connect('notify::filebegin', lambda ssf, par: (ssf.filebegin in [x[0] for x in self._fileformat_entry.get_model()]) or (self._fileformat_entry.append_text(ssf.filebegin)))
            tab.attach(self._fileformat_entry, 1, 2, row, row + 1)
        else:
            l = Gtk.Label(fixedformat); l.set_alignment(0, 0.5)
            tab.attach(l, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label('Exposure time (sec):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(10, 0.0001, 3600 * 24 * 7, 10, 100), digits=4)
        tab.attach(self._exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label('Dwell time (sec):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._dwelltime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0.003, 0.0001, 3600 * 24 * 7, 10, 100), digits=4)
        tab.attach(self._dwelltime_entry, 1, 2, row, row + 1)
        self._dwelltime_entry.set_sensitive(False)
        row += 1
        
        l = Gtk.Label('Number of images:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._nimages_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 1, 9999999999, 1, 10), digits=0)
        tab.attach(self._nimages_entry, 1, 2, row, row + 1)
        self._nimages_entry.connect('value-changed', lambda sb:self._dwelltime_entry.set_sensitive(self._nimages_entry.get_value_as_int() > 1))
        row += 1

        l = Gtk.Label('Mask file:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._maskfile_entry = MaskEntryWithButton(self.credo)
        tab.attach(self._maskfile_entry, 1, 2, row, row + 1)
        self._maskfile_entry.set_filename(self.credo.default_mask)
        row += 1
        
        l = Gtk.Label('Next FSN:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        if fixedformat:
            self._nextfsn_label = Gtk.Label(str(self.credo.subsystems['Files'].get_next_fsn(self.credo.subsystems['Files'].get_format_regex(fixedformat, None))))
        else:
            self._nextfsn_label = Gtk.Label(str(self.credo.subsystems['Files'].get_next_fsn()))
        self.credo.subsystems['Files'].connect('new-nextfsn', lambda ssf, fsn, regex: self._nextfsn_label.set_text(str(fsn)))
        tab.attach(self._nextfsn_label, 1, 2, row, row + 1, xpadding=2)
        row += 1
        
        self._conns = []
        self.show_all()
    def _fileformat_entry_changed(self):
        self._nextfsn_label.set_text(str(self.credo.subsystems['Files'].get_next_fsn(self.credo.subsystems['Files'].get_format_regex(self._fileformat_entry.get_active_text(), None))))
    def execute(self):
        if self.credo.subsystems['Files'].filebegin != self._fileformat_entry.get_active_text():
            self.credo.subsystems['Files'].filebegin = self._fileformat_entry.get_active_text()
        self._conns = [self.credo.subsystems['Exposure'].connect('exposure-image', lambda sse, img: self.emit('image', img)),
                       self.credo.subsystems['Exposure'].connect('exposure-fail', lambda sse, err: self.emit('fail', err)),
                       self.credo.subsystems['Exposure'].connect('exposure-end', lambda sse, state: self.emit('end', state)), ]
        self.credo.expose(self._exptime_entry.get_value(), self._nimages_entry.get_value_as_int(), self._dwelltime_entry.get_value(), self._maskfile_entry.get_mask())
        self.emit('started')
    def do_started(self):
        self.set_sensitive(False)
    def do_end(self, state):
        self.set_sensitive(True)
        for c in self._conns:
            self.credo.subsystems['Exposure'].disconnect(c)
        self._conns = []
