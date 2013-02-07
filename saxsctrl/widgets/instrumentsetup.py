import gtk

class InstrumentSetup(gtk.Dialog):
    def __init__(self, credo, title='Instrument parameters', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.credo = credo
        self.credo_callback = self.credo.connect_callback('setup-changed', self.on_credo_setup_changed)
        vb = self.get_content_area()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        self.set_resizable(False)
        row = 0

        l = gtk.Label(u'Wavelength (\xc5):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.wavelength_entry = gtk.SpinButton(gtk.Adjustment(1.54182, 0, 100, 0.1, 1), digits=4)
        tab.attach(self.wavelength_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Sample-detector distance (mm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.dist_entry = gtk.SpinButton(gtk.Adjustment(0, 1000, 10000, 0.1, 1), digits=2)
        tab.attach(self.dist_entry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label(u'Beam position (vertical):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.beamposx_entry = gtk.SpinButton(gtk.Adjustment(308.298, -1000, 1000, 0.1, 1), digits=2)
        tab.attach(self.beamposx_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label(u'Beam position (horizontal):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.beamposy_entry = gtk.SpinButton(gtk.Adjustment(243.63, -1000, 1000, 0.1, 1), digits=2)
        tab.attach(self.beamposy_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label(u'Pixel size (\u03bcm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.pixelsize_entry = gtk.SpinButton(gtk.Adjustment(172, 0, 5000, 1, 10), digits=0)
        tab.attach(self.pixelsize_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Filter:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.filter_entry = gtk.Entry()
        self.filter_entry.set_text('None')
        tab.attach(self.filter_entry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Filename format:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fileformat_label = gtk.Label()
        self.fileformat_label.set_text('None')
        tab.attach(self.fileformat_label, 1, 2, row, row + 1)
        row += 1 

        l = gtk.Label('Next FSN:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.nextfsn_label = gtk.Label()
        self.nextfsn_label.set_text('None')
        tab.attach(self.nextfsn_label, 1, 2, row, row + 1)
        row += 1 

        self.shuttercontrol_checkbutton = gtk.CheckButton('Shutter control')
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
        return False
    def on_credo_setup_changed(self, *args):
        self.update_from_credo()
        return False
    def on_response(self, dialog, respid):
        if respid == gtk.RESPONSE_OK:
            self.credo.wavelength = self.wavelength_entry.get_value()
            self.credo.beamposx = self.beamposx_entry.get_value()
            self.credo.beamposy = self.beamposy_entry.get_value()
            self.credo.dist = self.dist_entry.get_value()
            self.credo.pixelsize = self.pixelsize_entry.get_value()
            self.credo.filter = self.filter_entry.get_text()
            self.credo.shuttercontrol = self.shuttercontrol_checkbutton.get_active()
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
        self.nextfsn_label.set_text(str(self.credo.get_next_fsn()))
        self.fileformat_label.set_text(self.credo.fileformat)
