#
# coding: utf-8
import gtk
from ..hardware import sample

class SampleSetup(gtk.Dialog):
    def __init__(self, credo, title='Define sample', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.credo = credo
        vb = self.get_content_area()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        self.set_resizable(False)
        row = 0
        
        l = gtk.Label('Sample name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.samplename_entry = gtk.Entry()
        self.samplename_entry.set_text('-- please fill --')
        tab.attach(self.samplename_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Thickness (cm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.thickness_entry = gtk.SpinButton(gtk.Adjustment(0.1, 0, 100, 0.1, 1), digits=4)
        tab.attach(self.thickness_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Position:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.position_entry = gtk.SpinButton(gtk.Adjustment(0, -10, 10, 0.1, 1), digits=2)
        tab.attach(self.position_entry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label(u'Temperature (°C):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.temperature_entry = gtk.SpinButton(gtk.Adjustment(25, -273, 1000, 0.1, 1), digits=2)
        tab.attach(self.temperature_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label(u'Transmission:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.transmission_entry = gtk.SpinButton(gtk.Adjustment(0.5, 0, 1, 0.1, 1), digits=2)
        tab.attach(self.transmission_entry, 1, 2, row, row + 1)
        row += 1
        self.connect('response', self.on_response)
        self.connect('delete-event', self.hide_on_delete)
        vb.show_all()
    def on_response(self, dialog, respid):
        if respid == gtk.RESPONSE_OK:
            self.credo.set_sample(self.get_sample())
        self.hide()
        return True
    def get_sample(self):
        title = self.samplename_entry.get_text()
        temperature = self.temperature_entry.get_value()
        thickness = self.thickness_entry.get_value()
        position = self.position_entry.get_value()
        transmission = self.transmission_entry.get_value()
        return sample.SAXSSample(title, position, thickness, transmission, temperature)
