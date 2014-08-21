from gi.repository import Gtk
from gi.repository import Gdk
from ..hardware.instruments import InstrumentPropertyCategory, InstrumentError, InstrumentPropertyUnknown
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class InstrumentStatusLabel(Gtk.Box):
    __gtype_name__ = 'SAXSCtrl_InstrumentStatusLabel'
    __gsignals__ = {'destroy':'override'}
    def __init__(self, instrument, propertyname, label=None, formatter=None, colourer=None):
        self._instrument = instrument
        self._propertyname = propertyname
        self._colourer = colourer
        if label is None:
            label = propertyname.capitalize()
        if formatter is None:
            self._formatter = str
        elif isinstance(formatter, basestring):
            self._formatter = lambda x: formatter % x
        else:
            self._formatter = formatter
        self._labelname = label
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, homogeneous=True)
        self._label = Gtk.Label(label=label)
        self.pack_start(self._label, True, True, 0)
        self._eventbox = Gtk.EventBox()
        self.pack_start(self._eventbox, True, True, 0)
        self._valuelabel = Gtk.Label(label='--')
        self._eventbox.add(self._valuelabel)
        if self._instrument.is_instrumentproperty(self._propertyname):
            self._connection = self._instrument.connect('instrumentproperty-notify', self._on_instrumentproperty_notify)
        else:
            self._connection = self._instrument.connect('notify::' + self._propertyname, self._on_property_notify)
        self.set_size_request(-1, 30)
    def _on_instrumentproperty_notify(self, instrument, propertyname):
        if propertyname != self._propertyname:
            return False
        try:
            value, category = instrument.get_instrument_property(propertyname)[::2]
        except (InstrumentError, InstrumentPropertyUnknown):
            value = None
            category = InstrumentPropertyCategory.UNKNOWN
        if self._colourer is None:
            if category in [InstrumentPropertyCategory.ERROR, InstrumentPropertyCategory.NO]:
                self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(*Gdk.color_parse('red').to_floats()))
            elif category in [InstrumentPropertyCategory.OK, InstrumentPropertyCategory.YES]:
                self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(*Gdk.color_parse('green').to_floats()))
            elif category in [InstrumentPropertyCategory.WARNING]:
                self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(*Gdk.color_parse('orange').to_floats()))
            elif category in [InstrumentPropertyCategory.UNKNOWN]:
                self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(*Gdk.color_parse('gray').to_floats()))
            elif category in [InstrumentPropertyCategory.NORMAL]:
                self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(*Gdk.color_parse('white').to_floats()))
            else:
                raise NotImplementedError('Instrument property category "%s" is unknown for InstrumentStatusLabel.' % category)
        else:
            self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, self._colourer(value, category))
        if category != InstrumentPropertyCategory.UNKNOWN:
            self._valuelabel.set_text(self._formatter(value))
        else:
            self._valuelabel.set_text('UNKNOWN')
        return True
    def _on_property_notify(self, instrument, prop):
        try:
            value = instrument.get_property(self._propertyname)
        except InstrumentError:
            self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(*Gdk.color_parse('gray').to_floats()))
            self._valuelabel.set_text('UNKNOWN')
        else:
            if self._colourer is None:
                self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, None)
            else:
                self._eventbox.override_background_color(Gtk.StateFlags.NORMAL, self._colourer(value, None))
            self._valuelabel.set_text(self._formatter(value))
        return True
    def do_destroy(self):
        logger.debug('Destroying an InstrumentStatusLabel')
        if hasattr(self, '_valuelabel'):
            del self._valuelabel
        if hasattr(self, '_eventbox'):
            del self._eventbox
        if hasattr(self, '_label'):
            del self._label
        if hasattr(self, '_connection'):
            self._instrument.disconnect(self._connection)
            del self._connection
            del self._instrument
        logger.debug('Destroyed an InstrumentStatusLabel')
    def refresh(self):
        if self._instrument.is_instrumentproperty(self._propertyname):
            self._on_instrumentproperty_notify(self._instrument, self._propertyname)
        else:
            self._on_property_notify(self._instrument, None)

class InstrumentStatus(Gtk.Frame):
    __gtype_name__ = 'SAXSCtrl_InstrumentStatus'
    def __init__(self, instrument, ncolumns=6, label='Instrument status'):
        Gtk.Frame.__init__(self, label=label)
        self._grid = Gtk.Grid()
        self.add(self._grid)
        self.instrument = instrument
        self._ncolumns = ncolumns
        self._grid.set_row_spacing(15)
        self._grid.set_column_spacing(5)
        self._grid.set_row_homogeneous(True)
        self._grid.set_column_homogeneous(True)
    def add_label(self, propertyname, label=None, formatter=None, colourer=None):
        newlabel = InstrumentStatusLabel(self.instrument, propertyname, label, formatter, colourer)
        numchildren = len(self._grid.get_children())
        column = (numchildren) % self._ncolumns
        row = (numchildren) / self._ncolumns
        self._grid.attach(newlabel, column, row, 1, 1)
        newlabel.show_all()
    def refresh_statuslabels(self):
        for statuslabel in self._grid.get_children():
            statuslabel.refresh()
    def do_destroy(self):
        logger.debug('InstrumentStatus.destroy() signal was emitted.')

