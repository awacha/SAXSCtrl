from gi.repository import Gtk
import sastool
import collections
import ConfigParser
from .spec_filechoosers import ExposureLoader, FileEntryWithButton

class PleaseWaitDialog(Gtk.Dialog):
    def __init__(self, title='Data reduction running, please wait...', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        vb = self.get_content_area()
        self.pbar = Gtk.ProgressBar()
        self.pbar.set_text('Working...')
        self.label = Gtk.Label()
        self.label.set_line_wrap(True)
        vb.pack_start(self.pbar, False, True, 0)
        vb.pack_start(self.label, True, True, 0)
        vb.show_all()
    def set_label_text(self, msg):
        self.label.set_text(msg)
        self.pbar.pulse()
        
class PleaseWaitInfoBar(Gtk.InfoBar):
    def __init__(self, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.InfoBar.__init__(self)
        for i in range(len(buttons) / 2):
            self.add_button(buttons[2 * i], buttons[2 * i + 1])
        self.set_message_type(Gtk.MessageType.INFO)
        vb = self.get_content_area()
        self.label = Gtk.Label('Data reduction running...')
        self.pbar = Gtk.ProgressBar()
        self.pbar.set_text('Working...')
        vb.pack_start(self.label, False, True, 0)
        vb.pack_start(self.pbar, False, True, 0)
        self.show_all()
    def set_label_text(self, msg):
        self.pbar.set_text(msg)
        self.pbar.pulse()
    def set_n_jobs(self, n):
        self.label.set_text('%d data reduction job(s) running...' % n)


    
class DataRedSetup(Gtk.Dialog):
    def __init__(self, credo, title='Set-up on-line data reduction', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.CLOSE)
        self.credo = credo
        self.set_resizable(False)
        vb = self.get_content_area()
        
        hb = Gtk.HBox()
        vb.pack_start(hb, True, True, 0)
        
        vb1 = Gtk.VBox()
        hb.pack_start(vb1, True, True, 0)
        vb2 = Gtk.VBox()
        hb.pack_start(vb2, True, True, 0)
        
        self.scalingframe = Gtk.Frame(label='Scaling')
        vb1.pack_start(self.scalingframe, True, True, 0)
        tab = Gtk.Table()
        self.scalingframe.add(tab)
        row = 0
        self.monitor_cb = Gtk.CheckButton('Normalize by measurement time'); self.monitor_cb.set_alignment(0, 0.5)
        tab.attach(self.monitor_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        self.thickness_cb = Gtk.CheckButton('Normalize by thickness'); self.thickness_cb.set_alignment(0, 0.5)
        tab.attach(self.thickness_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        self.transmission_cb = Gtk.CheckButton('Normalize by transmission'); self.transmission_cb.set_alignment(0, 0.5)
        tab.attach(self.transmission_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        self.bgsub_cb = Gtk.CheckButton('Subtract background'); self.bgsub_cb.set_alignment(0, 0.5)
        tab.attach(self.bgsub_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        self.GCcalib_cb = Gtk.CheckButton('Scale to 1/cm'); self.GCcalib_cb.set_alignment(0, 0.5)
        tab.attach(self.GCcalib_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        
        
        
        self.geoframe = Gtk.Frame(label='Geometry')
        vb1.pack_start(self.geoframe, True, True, 0)
        tab = Gtk.Table()
        self.geoframe.add(tab)
        row = 0
        
        self.solidangle_cb = Gtk.CheckButton('Solid angle correction'); self.solidangle_cb.set_alignment(0, 0.5)
        tab.attach(self.solidangle_cb, 0, 1, row, row + 1)
        row += 1
        
        self.transmframe = Gtk.Frame(label='Transmission')
        vb2.pack_start(self.transmframe, True, True, 0)
        tab = Gtk.Table()
        self.transmframe.add(tab)
        self.on_coupled_cb_entry(self.transmission_cb, self.transmframe)
        self.transmission_cb.connect('toggled', self.on_coupled_cb_entry, self.transmframe)
        row = 0

        self.transmoverride_cb = Gtk.CheckButton('Override value:'); self.transmoverride_cb.set_alignment(0, 0.5)
        tab.attach(self.transmoverride_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.transmoverride_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0.5, 0, 1, 0.01, 0.1), digits=4)
        tab.attach(self.transmoverride_entry, 1, 2, row, row + 1)
        self.transmoverride_cb.connect('toggled', self.on_coupled_cb_entry, self.transmoverride_entry)
        self.on_coupled_cb_entry(self.transmoverride_cb, self.transmoverride_entry)
        row += 1
        self.angledepabs_cb = Gtk.CheckButton('Angle-dependent self-absorption'); self.angledepabs_cb.set_alignment(0, 0.5)
        tab.attach(self.angledepabs_cb, 0, 1, row, row + 1)
        row += 1


        self.bgframe = Gtk.Frame(label='Background (Empty beam)')
        vb1.pack_start(self.bgframe, True, True, 0)
        tab = Gtk.Table()
        self.bgframe.add(tab)
        self.on_coupled_cb_entry(self.bgsub_cb, self.bgframe)
        self.bgsub_cb.connect('toggled', self.on_coupled_cb_entry, self.bgframe)
        row = 0
        
        l = Gtk.Label(label='Name of background measurement:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.bgname_entry = Gtk.Entry();
        self.bgname_entry.set_text('Empty beam')
        tab.attach(self.bgname_entry, 1, 2, row, row + 1)
        row += 1
        l = Gtk.Label(label='Background measurement:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.bgloader = ExposureLoader(self.credo)
        tab.attach(self.bgloader, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Background FSN finding:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.bgfind_combo = Gtk.ComboBoxText()
        tab.attach(self.bgfind_combo, 1, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.bgfind_combo.append_text('Static')
        self.bgfind_combo.append_text('Nearest in time')
        self.bgfind_combo.append_text('Nearest in time before')
        self.bgfind_combo.append_text('Nearest in time after')
        self.bgfind_combo.set_active(0)
        self.bgfind_combo.connect('changed', self.on_coupled_cb_entry, [self.bgname_entry], [self.bgloader])
        self.on_coupled_cb_entry(self.bgfind_combo, [self.bgname_entry], [self.bgloader])
        row += 1
        
        l = Gtk.Label(label='Distance tolerance (mm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.bg_disttol_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(20, 0, 10000, 1, 10), digits=2)
        tab.attach(self.bg_disttol_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Energy tolerance (eV):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.bg_energytol_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(2, 0, 10000, 1, 10), digits=2)
        tab.attach(self.bg_energytol_entry, 1, 2, row, row + 1)
        row += 1

        
        self.absintframe = Gtk.Frame(label='Absolute intensity')
        vb2.pack_start(self.absintframe, True, True, 0)
        tab = Gtk.Table()
        self.absintframe.add(tab)
        self.GCcalib_cb.connect('toggled', self.on_coupled_cb_entry, self.absintframe)
        self.on_coupled_cb_entry(self.GCcalib_cb, self.absintframe)
        
        row = 0
        l = Gtk.Label(label='Name of reference measurement:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GCname_entry = Gtk.Entry();
        self.GCname_entry.set_text('GC')
        tab.attach(self.GCname_entry, 1, 2, row, row + 1)
        row += 1
        l = Gtk.Label(label='Reference measurement:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GCloader = ExposureLoader(self.credo)
        tab.attach(self.GCloader, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Reference FSN finding:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GCfind_combo = Gtk.ComboBoxText()
        tab.attach(self.GCfind_combo, 1, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GCfind_combo.append_text('Static')
        self.GCfind_combo.append_text('Nearest in time')
        self.GCfind_combo.append_text('Nearest in time before')
        self.GCfind_combo.append_text('Nearest in time after')
        self.GCfind_combo.set_active(0)
        self.GCfind_combo.connect('changed', self.on_coupled_cb_entry, [self.GCname_entry], [self.GCloader])
        self.on_coupled_cb_entry(self.GCfind_combo, [self.GCname_entry], [self.GCloader])
        row += 1
        
        l = Gtk.Label(label='Distance tolerance (mm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GC_disttol_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(20, 0, 10000, 1, 10), digits=2)
        tab.attach(self.GC_disttol_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Energy tolerance (eV):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GC_energytol_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(2, 0, 10000, 1, 10), digits=2)
        tab.attach(self.GC_energytol_entry, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label(label='Reference dataset:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GC_refdataset_entry = FileEntryWithButton()
        tab.attach(self.GC_refdataset_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1

        self.GC_qmin_cb = Gtk.CheckButton(label='Q min:'); self.GC_qmin_cb.set_alignment(0, 0.5)
        tab.attach(self.GC_qmin_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GC_qmin_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 10000, 0.1, 1), digits=4)
        tab.attach(self.GC_qmin_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GC_qmin_cb.connect('toggled', self.on_coupled_cb_entry, self.GC_qmin_entry)
        self.on_coupled_cb_entry(self.GC_qmin_cb, self.GC_qmin_entry)
        row += 1

        self.GC_qmax_cb = Gtk.CheckButton(label='Q max:'); self.GC_qmax_cb.set_alignment(0, 0.5)
        tab.attach(self.GC_qmax_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GC_qmax_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 10000, 0.1, 1), digits=4)
        tab.attach(self.GC_qmax_entry, 1, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.GC_qmax_cb.connect('toggled', self.on_coupled_cb_entry, self.GC_qmax_entry)
        self.on_coupled_cb_entry(self.GC_qmax_cb, self.GC_qmax_entry)
        row += 1
        
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
        if respid in (Gtk.ResponseType.ACCEPT, Gtk.ResponseType.OK):
            self.to_credo()
            self.credo.datareduction.save_state()
        if respid in (Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL):
            self.hide()
        return True
    def to_credo(self):
        self.credo.datareduction.set_property('do_monitor', self.monitor_cb.get_active())
        self.credo.datareduction.set_property('do_transmission', self.transmission_cb.get_active())
        self.credo.datareduction.set_property('do_solidangle', self.solidangle_cb.get_active())
        self.credo.datareduction.set_property('transmission_selfabsorption', self.angledepabs_cb.get_active())
        self.credo.datareduction.set_property('do_bgsub', self.bgsub_cb.get_active())
        self.credo.datareduction.set_property('do_absint', self.GCcalib_cb.get_active())
        self.credo.datareduction.set_property('bg_name', self.bgname_entry.get_text())
        self.credo.datareduction.set_property('bg_dist_tolerance', self.bg_disttol_entry.get_value())
        self.credo.datareduction.set_property('bg_energy_tolerance', self.bg_energytol_entry.get_value())
        if self.bgfind_combo.get_active_text() == 'Static':
            self.credo.datareduction.set_property('bg_select_method', self.bgloader.get_filename())
        elif self.bgfind_combo.get_active_text() == 'Nearest in time':
            self.credo.datareduction.set_property('bg_select_method', 'nearest')
        elif self.bgfind_combo.get_active_text() == 'Nearest in time before':
            self.credo.datareduction.set_property('bg_select_method', 'prev')
        elif self.bgfind_combo.get_active_text() == 'Nearest in time after':
            self.credo.datareduction.set_property('bg_select_method', 'next')
        self.credo.datareduction.set_property('absint_name', self.GCname_entry.get_text())
        self.credo.datareduction.set_property('absint_dist_tolerance', self.GC_disttol_entry.get_value())
        self.credo.datareduction.set_property('absint_energy_tolerance', self.GC_energytol_entry.get_value())
        self.credo.datareduction.set_property('absint_reffile', self.GC_refdataset_entry.get_path())
        self.credo.datareduction.set_property('monitor_attr', 'MeasTime')
        if self.GCfind_combo.get_active_text() == 'Static':
            self.credo.datareduction.set_property('absint_select_method', self.GCloader.get_filename())
        elif self.GCfind_combo.get_active_text() == 'Nearest in time':
            self.credo.datareduction.set_property('absint_select_method', 'nearest') 
        elif self.GCfind_combo.get_active_text() == 'Nearest in time before':
            self.credo.datareduction.set_property('absint_select_method', 'prev')
        elif self.GCfind_combo.get_active_text() == 'Nearest in time after':
            self.credo.datareduction.set_property('absint_select_method', 'next')
        self.credo.datareduction.set_property('do_thickness', self.thickness_cb.get_active())
        if self.GC_qmin_cb.get_active():
            self.credo.datareduction.set_property('absint_qmin', self.GC_qmin_entry.get_value())
        else:
            self.credo.datareduction.set_property('absint_qmin', -100)
        if self.GC_qmax_cb.get_active():
            self.credo.datareduction.set_property('absint_qmax', self.GC_qmax_entry.get_value())
        else:
            self.credo.datareduction.set_property('absint_qmax', -100)
    def from_credo(self):
        self.monitor_cb.set_active(self.credo.datareduction.get_property('do_monitor'))
        self.transmission_cb.set_active(self.credo.datareduction.get_property('do_transmission'))
        self.solidangle_cb.set_active(self.credo.datareduction.get_property('do_solidangle'))
        self.angledepabs_cb.set_active(self.credo.datareduction.get_property('transmission_selfabsorption'))
        self.bgsub_cb.set_active(self.credo.datareduction.get_property('do_bgsub'))
        self.GCcalib_cb.set_active(self.credo.datareduction.get_property('do_absint'))
        self.bgname_entry.set_text(self.credo.datareduction.get_property('bg_name'))
        self.bg_disttol_entry.set_value(self.credo.datareduction.get_property('bg_dist_tolerance'))
        self.bg_energytol_entry.set_value(self.credo.datareduction.get_property('bg_energy_tolerance'))
        if self.credo.datareduction.get_property('bg_select_method') == 'nearest':
            self.bgfind_combo.set_active(1)
        elif self.credo.datareduction.get_property('bg_select_method') == 'prev':
            self.bgfind_combo.set_active(2)
        elif self.credo.datareduction.get_property('bg_select_method') == 'next':
            self.bgfind_combo.set_active(3)
        else:
            self.bgfind_combo.set_active(0)
            self.bgloader.set_filename(self.credo.datareduction.get_property('bg_select_method'))
        self.GCname_entry.set_text(self.credo.datareduction.get_property('absint_name'))
        self.GC_disttol_entry.set_value(self.credo.datareduction.get_property('absint_dist_tolerance'))
        self.GC_energytol_entry.set_value(self.credo.datareduction.get_property('absint_energy_tolerance'))
        self.GC_refdataset_entry.set_filename(self.credo.datareduction.get_property('absint_reffile'))
        if self.credo.datareduction.get_property('absint_select_method') == 'nearest':
            self.GCfind_combo.set_active(1)
        elif self.credo.datareduction.get_property('absint_select_method') == 'prev':
            self.GCfind_combo.set_active(2)
        elif self.credo.datareduction.get_property('absint_select_method') == 'next':
            self.GCfind_combo.set_active(3)
        else:
            self.GCfind_combo.set_active(0)
            self.GCloader.set_filename(self.credo.datareduction.get_property('absint_select_method'))
        self.thickness_cb.set_active(self.credo.datareduction.get_property('do_thickness'))
        if self.credo.datareduction.get_property('absint_qmax') < 0:
            self.GC_qmax_cb.set_active(False)
        else:
            self.GC_qmax_cb.set_active(True)
            self.GC_qmax_entry.set_value(self.credo.datareduction.get_property('absint_qmax'))
        if self.credo.datareduction.get_property('absint_qmin') < 0:
            self.GC_qmin_cb.set_active(False)
        else:
            self.GC_qmin_cb.set_active(True)
            self.GC_qmin_entry.set_value(self.credo.datareduction.get_property('absint_qmin'))            
