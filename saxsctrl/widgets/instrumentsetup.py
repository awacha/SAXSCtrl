from gi.repository import Gtk
from .nextfsn_monitor import NextFSNMonitor

class InstrumentSetup(Gtk.Dialog):
    def __init__(self, credo, title='Instrument parameters', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        self.credo = credo
        self.credo_callback = self.credo.connect('setup-changed', self.on_credo_setup_changed)
        self.credo_callback1 = self.credo.connect('path-changed', self.on_credo_setup_changed)
        vb = self.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        self.set_resizable(False)
        row = 0

        l = Gtk.Label(label=u'Wavelength (\xc5):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.wavelength_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1.54182, 0, 100, 0.1, 1), digits=4)
        tab.attach(self.wavelength_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Sample-detector distance (mm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.dist_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1000, 0, 10000, 0.1, 1), digits=4)
        tab.attach(self.dist_entry, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label=u'Beam position (vertical):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.beamposx_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(308.298, -1000, 1000, 0.1, 1), digits=4)
        tab.attach(self.beamposx_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label=u'Beam position (horizontal):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.beamposy_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(243.63, -1000, 1000, 0.1, 1), digits=4)
        tab.attach(self.beamposy_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label=u'Pixel size (\u03bcm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.pixelsize_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(172, 0, 5000, 1, 10), digits=2)
        tab.attach(self.pixelsize_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Filter:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.filter_entry = Gtk.Entry()
        self.filter_entry.set_text('None')
        tab.attach(self.filter_entry, 1, 2, row, row + 1)
        row += 1
        
        vb.pack_start(NextFSNMonitor(self.credo, 'Next exposure'), True, True, 0)

        self.shuttercontrol_entry = Gtk.CheckButton('Shutter control')
        self.shuttercontrol_entry.set_alignment(0, 0.5)
        tab.attach(self.shuttercontrol_entry, 0, 2, row, row + 1)
        self.shuttercontrol_entry.set_active(True)
        
        self.update_from_credo()
        
        self.connect('response', self.on_response)
        self.connect('delete-event', self.hide_on_delete)
        self.connect('destroy', self.on_destroy)
        vb.show_all()
    def on_destroy(self, *args):
        self.credo.disconnect('setup-changed', self.credo_callback)
        self.credo.disconnect('path-changed', self.credo_callback1)
        return False
    def on_credo_setup_changed(self, *args):
        self.update_from_credo()
        return False
    def on_response(self, dialog, respid):
        if respid == Gtk.ResponseType.OK or respid == Gtk.ResponseType.APPLY:
            for attrname in ['wavelength', 'beamposx', 'beamposy', 'dist', 'pixelsize', 'filter', 'shuttercontrol']:
                widget = self.__getattribute__(attrname + '_entry')
                if isinstance(widget, Gtk.SpinButton):
                    value = widget.get_value()
                elif isinstance(widget, Gtk.Entry):
                    value = widget.get_text()
                elif isinstance(widget, Gtk.ToggleButton):
                    value = widget.get_active()
                if self.credo.__getattribute__(attrname) != value:
                    print "Setting credo property: ", attrname, " to ", value
                    self.credo.set_property(attrname, value)
        if respid != Gtk.ResponseType.APPLY:
            self.hide()
        return True
    def update_from_credo(self):
        for attrname in ['wavelength', 'beamposx', 'beamposy', 'dist', 'pixelsize', 'filter', 'shuttercontrol']:
            widget = self.__getattribute__(attrname + '_entry')
            value = self.credo.get_property(attrname)
            if isinstance(widget, Gtk.SpinButton):
                widget.set_value(float(value))
            elif isinstance(widget, Gtk.Entry):
                widget.set_text(str(value))
            elif isinstance(widget, Gtk.ToggleButton):
                widget.set_active(bool(value))
