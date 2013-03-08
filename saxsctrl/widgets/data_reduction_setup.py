import gtk
import sastool
import collections
import ConfigParser
from .spec_filechoosers import ExposureLoader, FileEntryWithButton

class DataRedSetup(gtk.Dialog):
    def __init__(self, credo, title='Set-up on-line data reduction', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_APPLY, gtk.RESPONSE_APPLY)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_CLOSE)
        self.credo = credo
        self.set_resizable(False)
        vb = self.get_content_area()
        
        hb = gtk.HBox()
        vb.pack_start(hb)
        
        vb1 = gtk.VBox()
        hb.pack_start(vb1)
        vb2 = gtk.VBox()
        hb.pack_start(vb2)
        
        self.scalingframe = gtk.Frame('Scaling')
        vb1.pack_start(self.scalingframe)
        tab = gtk.Table()
        self.scalingframe.add(tab)
        row = 0
        self.monitor_cb = gtk.CheckButton('Normalize by measurement time'); self.monitor_cb.set_alignment(0, 0.5)
        tab.attach(self.monitor_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        row += 1
        self.thickness_cb = gtk.CheckButton('Normalize by thickness'); self.thickness_cb.set_alignment(0, 0.5)
        tab.attach(self.thickness_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        row += 1
        self.transmission_cb = gtk.CheckButton('Normalize by transmission'); self.transmission_cb.set_alignment(0, 0.5)
        tab.attach(self.transmission_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        row += 1
        self.bgsub_cb = gtk.CheckButton('Subtract background'); self.bgsub_cb.set_alignment(0, 0.5)
        tab.attach(self.bgsub_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        row += 1
        self.GCcalib_cb = gtk.CheckButton('Scale to 1/cm'); self.GCcalib_cb.set_alignment(0, 0.5)
        tab.attach(self.GCcalib_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        row += 1
        
        
        
        self.geoframe = gtk.Frame('Geometry')
        vb1.pack_start(self.geoframe)
        tab = gtk.Table()
        self.geoframe.add(tab)
        row = 0
        
        self.solidangle_cb = gtk.CheckButton('Solid angle correction'); self.solidangle_cb.set_alignment(0, 0.5)
        tab.attach(self.solidangle_cb, 0, 1, row, row + 1)
        row += 1
        
        self.transmframe = gtk.Frame('Transmission')
        vb2.pack_start(self.transmframe)
        tab = gtk.Table()
        self.transmframe.add(tab)
        self.on_coupled_cb_entry(self.transmission_cb, self.transmframe)
        self.transmission_cb.connect('toggled', self.on_coupled_cb_entry, self.transmframe)
        row = 0

        self.transmoverride_cb = gtk.CheckButton('Override value:'); self.transmoverride_cb.set_alignment(0, 0.5)
        tab.attach(self.transmoverride_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.transmoverride_entry = gtk.SpinButton(gtk.Adjustment(0.5, 0, 1, 0.01, 0.1), digits=4)
        tab.attach(self.transmoverride_entry, 1, 2, row, row + 1)
        self.transmoverride_cb.connect('toggled', self.on_coupled_cb_entry, self.transmoverride_entry)
        self.on_coupled_cb_entry(self.transmoverride_cb, self.transmoverride_entry)
        row += 1
        self.angledepabs_cb = gtk.CheckButton('Angle-dependent self-absorption'); self.angledepabs_cb.set_alignment(0, 0.5)
        tab.attach(self.angledepabs_cb, 0, 1, row, row + 1)
        row += 1


        self.bgframe = gtk.Frame('Background (Empty beam)')
        vb1.pack_start(self.bgframe)
        tab = gtk.Table()
        self.bgframe.add(tab)
        self.on_coupled_cb_entry(self.bgsub_cb, self.bgframe)
        self.bgsub_cb.connect('toggled', self.on_coupled_cb_entry, self.bgframe)
        row = 0
        
        l = gtk.Label('Name of background measurement:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.bgname_entry = gtk.Entry();
        self.bgname_entry.set_text('Empty beam')
        tab.attach(self.bgname_entry, 1, 2, row, row + 1)
        row += 1
        l = gtk.Label('Background measurement:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.bgloader = ExposureLoader(self.credo)
        tab.attach(self.bgloader, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Background FSN finding:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.bgfind_combo = gtk.combo_box_new_text()
        tab.attach(self.bgfind_combo, 1, 2, row, row + 1, gtk.FILL, gtk.FILL)
        self.bgfind_combo.append_text('Static')
        self.bgfind_combo.append_text('Nearest in time')
        self.bgfind_combo.append_text('Nearest in time before')
        self.bgfind_combo.append_text('Nearest in time after')
        self.bgfind_combo.set_active(0)
        self.bgfind_combo.connect('changed', self.on_coupled_cb_entry, [self.bgname_entry], [self.bgloader])
        self.on_coupled_cb_entry(self.bgfind_combo, [self.bgname_entry], [self.bgloader])
        row += 1
        
        l = gtk.Label('Distance tolerance (mm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.bg_disttol_entry = gtk.SpinButton(gtk.Adjustment(20, 0, 10000, 1, 10), digits=2)
        tab.attach(self.bg_disttol_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Energy tolerance (eV):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.bg_energytol_entry = gtk.SpinButton(gtk.Adjustment(2, 0, 10000, 1, 10), digits=2)
        tab.attach(self.bg_energytol_entry, 1, 2, row, row + 1)
        row += 1

        
        self.absintframe = gtk.Frame('Absolute intensity')
        vb2.pack_start(self.absintframe)
        tab = gtk.Table()
        self.absintframe.add(tab)
        self.GCcalib_cb.connect('toggled', self.on_coupled_cb_entry, self.absintframe)
        self.on_coupled_cb_entry(self.GCcalib_cb, self.absintframe)
        
        row = 0
        l = gtk.Label('Name of reference measurement:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.GCname_entry = gtk.Entry();
        self.GCname_entry.set_text('GC')
        tab.attach(self.GCname_entry, 1, 2, row, row + 1)
        row += 1
        l = gtk.Label('Reference measurement:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.GCloader = ExposureLoader(self.credo)
        tab.attach(self.GCloader, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Reference FSN finding:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.GCfind_combo = gtk.combo_box_new_text()
        tab.attach(self.GCfind_combo, 1, 2, row, row + 1, gtk.FILL, gtk.FILL)
        self.GCfind_combo.append_text('Static')
        self.GCfind_combo.append_text('Nearest in time')
        self.GCfind_combo.append_text('Nearest in time before')
        self.GCfind_combo.append_text('Nearest in time after')
        self.GCfind_combo.set_active(0)
        self.GCfind_combo.connect('changed', self.on_coupled_cb_entry, [self.GCname_entry], [self.GCloader])
        self.on_coupled_cb_entry(self.GCfind_combo, [self.GCname_entry], [self.GCloader])
        row += 1
        
        l = gtk.Label('Distance tolerance (mm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.GC_disttol_entry = gtk.SpinButton(gtk.Adjustment(20, 0, 10000, 1, 10), digits=2)
        tab.attach(self.GC_disttol_entry, 1, 2, row, row + 1)
        row += 1

        l = gtk.Label('Energy tolerance (eV):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.GC_energytol_entry = gtk.SpinButton(gtk.Adjustment(2, 0, 10000, 1, 10), digits=2)
        tab.attach(self.GC_energytol_entry, 1, 2, row, row + 1)
        row += 1
        
        l = gtk.Label('Reference dataset:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.GC_refdataset_entry = FileEntryWithButton()

        vb.show_all()
        self.from_credo()
        self.credo.datareduction.connect('changed', self.on_datareduction_changed)
        self.connect('response', self.on_response)
    def on_datareduction_changed(self, *args):
        self.from_credo()
        return True
    def on_coupled_cb_entry(self, cb, widgets_on, widgets_off=[]):
        if not isinstance(widgets_on, collections.Sequence):
            widgets_on = [widgets_on]
        if not isinstance(widgets_off, collections.Sequence):
            widgets_off = [widgets_off]
        for w in widgets_on:
            w.set_sensitive(cb.get_active())
        for w in widgets_off:
            w.set_sensitive(not cb.get_active())
        return True
    def on_response(self, dialog, respid):
        if respid in (gtk.RESPONSE_ACCEPT, gtk.RESPONSE_OK):
            self.to_credo()
            self.credo.datareduction.save_state()
        if respid in (gtk.RESPONSE_OK, gtk.RESPONSE_CANCEL):
            self.hide()
        return True
    def to_credo(self):
        self.credo.datareduction.do_monitor = self.monitor_cb.get_active()
        self.credo.datareduction.do_transmission = self.transmission_cb.get_active()
        self.credo.datareduction.do_solidangle = self.solidangle_cb.get_active()
        self.credo.datareduction.transmission_selfabsorption = self.angledepabs_cb.get_active()
        self.credo.datareduction.do_bgsub = self.bgsub_cb.get_active()
        self.credo.datareduction.do_absint = self.GCcalib_cb.get_active()
        self.credo.datareduction.bg_name = self.bgname_entry.get_text()
        self.credo.datareduction.bg_dist_tolerance = self.bg_disttol_entry.get_value()
        self.credo.datareduction.bg_energy_tolerance = self.bg_energytol_entry.get_value()
        if self.bgfind_combo.get_active_text() == 'Static':
            self.credo.datareduction.bg_select_method = self.bgloader.get_filename()
        elif self.bgfind_combo.get_active_text() == 'Nearest in time':
            self.credo.datareduction.bg_select_method = 'nearest' 
        elif self.bgfind_combo.get_active_text() == 'Nearest in time before':
            self.credo.datareduction.bg_select_method = 'prev'
        elif self.bgfind_combo.get_active_text() == 'Nearest in time after':
            self.credo.datareduction.bg_select_method = 'next'
        self.credo.datareduction.absint_name = self.GCname_entry.get_text()
        self.credo.datareduction.absint_dist_tolerance = self.GC_disttol_entry.get_value()
        self.credo.datareduction.absint_energy_tolerance = self.GC_energytol_entry.get_value()
        self.credo.datareduction.absint_reffile = self.GC_refdataset_entry.get_path()
        self.credo.datareduction.monitor_attr = 'MeasTime'     
        if self.GCfind_combo.get_active_text() == 'Static':
            self.credo.datareduction.absint_select_method = self.GCloader.get_filename()
        elif self.GCfind_combo.get_active_text() == 'Nearest in time':
            self.credo.datareduction.absint_select_method = 'nearest' 
        elif self.GCfind_combo.get_active_text() == 'Nearest in time before':
            self.credo.datareduction.absint_select_method = 'prev'
        elif self.GCfind_combo.get_active_text() == 'Nearest in time after':
            self.credo.datareduction.absint_select_method = 'next'
        self.credo.datareduction.do_thickness = self.thickness_cb.get_active()
    def from_credo(self):
        self.monitor_cb.set_active(self.credo.datareduction.do_monitor)
        self.transmission_cb.set_active(self.credo.datareduction.do_transmission)
        self.solidangle_cb.set_active(self.credo.datareduction.do_solidangle)
        self.angledepabs_cb.set_active(self.credo.datareduction.transmission_selfabsorption)
        self.bgsub_cb.set_active(self.credo.datareduction.do_bgsub)
        self.GCcalib_cb.set_active(self.credo.datareduction.do_absint)
        self.bgname_entry.set_text(self.credo.datareduction.bg_name)
        self.bg_disttol_entry.set_value(self.credo.datareduction.bg_dist_tolerance)
        self.bg_energytol_entry.set_value(self.credo.datareduction.bg_energy_tolerance)
        if self.credo.datareduction.bg_select_method == 'nearest':
            self.bgfind_combo.set_active(1)
        elif self.credo.datareduction.bg_select_method == 'prev':
            self.bgfind_combo.set_active(2)
        elif self.credo.datareduction.bg_select_method == 'next':
            self.bgfind_combo.set_active(3)
        else:
            self.bgfind_combo.set_active(0)
            self.bgloader.set_filename(self.credo.datareduction.bg_select_method)
        self.GCname_entry.set_text(self.credo.datareduction.absint_name)
        self.GC_disttol_entry.set_value(self.credo.datareduction.absint_dist_tolerance)
        self.GC_energytol_entry.set_value(self.credo.datareduction.absint_energy_tolerance)
        self.GC_refdataset_entry.set_filename(self.credo.datareduction.absint_reffile)
        if self.credo.datareduction.absint_select_method == 'nearest':
            self.GCfind_combo.set_active(1)
        elif self.credo.datareduction.absint_select_method == 'prev':
            self.GCfind_combo.set_active(2)
        elif self.credo.datareduction.absint_select_method == 'next':
            self.GCfind_combo.set_active(3)
        else:
            self.GCfind_combo.set_active(0)
            self.GCloader.set_filename(self.credo.datareduction.absint_select_method)
        self.thickness_cb.set_active(self.credo.datareduction.do_thickness)
