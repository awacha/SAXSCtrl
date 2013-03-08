from gi.repository import Gtk
from .nextfsn_monitor import NextFSNMonitor

class InstrumentSetup(Gtk.Dialog):
    def __init__(self, credo, title='Instrument parameters', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        self.credo = credo
        self.credo_callback = self.credo.connect_callback('setup-changed', self.on_credo_setup_changed)
        self.credo_callback1 = self.credo.connect_callback('path-changed', self.on_credo_setup_changed)
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

        self.shuttercontrol_checkbutton = Gtk.CheckButton('Shutter control')
        self.shuttercontrol_checkbutton.set_alignment(0, 0.5)
        tab.attach(self.shuttercontrol_checkbutton, 0, 2, row, row + 1)
        self.shuttercontrol_checkbutton.set_active(True)
        
        self.update_from_credo()
        
        self.connect('response', self.on_response)
        self.connect('delete-event', self.hide_on_delete)
        self.connect('destroy', self.on_destroy)
        vb.show_all()
    def on_destroy(self, *args):
        self.credo.disconnect_callback('setup-changed', self.credo_callback)
        self.credo.disconnect_callback('path-changed', self.credo_callback1)
        return False
    def on_credo_setup_changed(self, *args):
        self.update_from_credo()
        return False
    def on_response(self, dialog, respid):
        if respid == Gtk.ResponseType.OK or respid == Gtk.ResponseType.APPLY:
            with self.credo.callbacks_frozen('setup-changed'):
                with self.credo.callbacks_frozen('path-changed'):
                    self.credo.wavelength = self.wavelength_entry.get_value()
                    self.credo.beamposx = self.beamposx_entry.get_value()
                    self.credo.beamposy = self.beamposy_entry.get_value()
                    self.credo.dist = self.dist_entry.get_value()
                    self.credo.pixelsize = self.pixelsize_entry.get_value()
                    self.credo.filter = self.filter_entry.get_text()
                    self.credo.shuttercontrol = self.shuttercontrol_checkbutton.get_active()
                    self.credo_callback = self.credo.connect_callback('setup-changed', self.on_credo_setup_changed)
                    self.credo_callback1 = self.credo.connect_callback('path-changed', self.on_credo_setup_changed)
            self.credo.emit('setup-changed')
            self.credo.emit('path-changed')
        if respid != Gtk.ResponseType.APPLY:
            self.hide()
        return True
    def update_from_credo(self):
        self.wavelength_entry.set_value(self.credo.wavelength)
        self.beamposx_entry.set_value(self.credo.beamposx)
        self.beamposy_entry.set_value(self.credo.beamposy)
        self.dist_entry.set_value(self.credo.dist)
        self.filter_entry.set_text(self.credo.filter)
        self.pixelsize_entry.set_value(self.credo.pixelsize)
        self.shuttercontrol_checkbutton.set_active(self.credo.shuttercontrol)
