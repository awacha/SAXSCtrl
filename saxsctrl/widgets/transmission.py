# coding: utf-8
from gi.repository import Gtk
import sastool
from .spec_filechoosers import MaskEntryWithButton
from .samplesetup import SampleSelector
from .widgets import ToolDialog

class TransmissionMeasurement(ToolDialog):
    def __init__(self, credo, title='Transmission measurement'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.OK, Gtk.STOCK_SAVE, Gtk.ResponseType.APPLY, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        self._tsconn = []
        self._transmresult = None
        sst = self.credo.subsystems['Transmission']
        vb = self.get_content_area()
        self._entrytab = Gtk.Table()
        vb.pack_start(self._entrytab, False, True, 0)
        row = 0
    
        l = Gtk.Label(label='Sample:'); l.set_alignment(0, 0.5)
        self._entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._sample_combo = SampleSelector(self.credo, autorefresh=False)
        try:
            self._sample_combo.set_sample(sst.samplename)
        except ValueError:
            pass
        self._entrytab.attach(self._sample_combo, 1, 2, row, row + 1)
        self._sample_combo.connect('sample-changed', lambda combo, sample:self.clear_data())
        row += 1

        l = Gtk.Label(label='Empty sample:'); l.set_alignment(0, 0.5)
        self._entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._empty_combo = SampleSelector(self.credo, autorefresh=False)
        try:
            self._empty_combo.set_sample(sst.emptyname)
        except ValueError:
            pass
        self._entrytab.attach(self._empty_combo, 1, 2, row, row + 1)
        self._empty_combo.connect('sample-changed', lambda combo, sample:self.clear_data())
        row += 1
        
        l = Gtk.Label(label='Exposure time:'); l.set_alignment(0, 0.5)
        self._entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(sst.countingtime, 0.0001, 1e10, 1, 10), digits=4)
        self._exptime_entry.set_value(sst.countingtime)
        self._entrytab.attach(self._exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Number of exposures:'); l.set_alignment(0, 0.5)
        self._entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._nimages_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(sst.nimages, 1, 1e10, 1, 10), digits=0)
        self._nimages_entry.set_value(sst.nimages)
        self._entrytab.attach(self._nimages_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Number of iterations:'); l.set_alignment(0, 0.5)
        self._entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._ncycles_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(sst.iterations, 1, 1e10, 1, 10), digits=0)
        self._ncycles_entry.set_value(sst.iterations)
        self._entrytab.attach(self._ncycles_entry, 1, 2, row, row + 1)
        row += 1
    
        l = Gtk.Label(label='Mask for beam area:'); l.set_alignment(0, 0.5)
        self._entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._mask_entry = MaskEntryWithButton(self.credo)
        self._mask_entry.set_filename(sst.mask)
        self._entrytab.attach(self._mask_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Method for intensity determination:'); l.set_alignment(0, 0.5)
        self._entrytab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._method_combo = Gtk.ComboBoxText()
        self._entrytab.attach(self._method_combo, 1, 2, row, row + 1)
        for i, m in enumerate(['max', 'sum', 'mean']):
            self._method_combo.append_text(m)
            if sst.method == m:
                self._method_combo.set_active(i)
        row += 1


        self._resultstable = Gtk.Table()        
        vb.pack_start(self._resultstable, False, True, 0)
        
        self._resultlabels = {}
        for row, what in enumerate(['Dark background', 'Empty beam', 'Sample'], 1):
            l = Gtk.Label(what + ':'); l.set_alignment(0, 0.5)
            what = what.split()[0].lower()
            self._resultstable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
            self._resultlabels[what] = {}
            for column, how in enumerate(['Mean cps', 'Stddev cps', '# of exposures'], 1):
                if row == 1:
                    l = Gtk.Label(how); l.set_alignment(0, 0.5)
                    self._resultstable.attach(l, column, column + 1, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
                how = how.split()[0].lower()
                self._resultlabels[what][how] = Gtk.Label('0')
                self._resultstable.attach(self._resultlabels[what][how], column, column + 1, row, row + 1, xpadding=10)

        
        f = Gtk.Frame(label='Measured transmission')
        vb.pack_start(f, True, True, 0)
        hb = Gtk.HBox()
        f.add(hb)
        self._transm_label = Gtk.Label(label='--')
        hb.pack_start(self._transm_label, False, True, 0)
        
    def do_response(self, respid):
        if respid == Gtk.ResponseType.OK:
            if self.get_widget_for_response(respid).get_label() == Gtk.STOCK_STOP:
                self.credo.subsystems['Transmission'].kill()
            else:
                sst = self.credo.subsystems['Transmission']
                sst.countingtime = self._exptime_entry.get_value()
                sst.samplename = self._sample_combo.get_sample().title
                sst.emptyname = self._empty_combo.get_sample().title
                sst.nimages = self._nimages_entry.get_value_as_int()
                sst.iterations = self._ncycles_entry.get_value_as_int()
                sst.mask = self._mask_entry.get_filename()
                sst.method = self._method_combo.get_active_text()
                self._tsconn = [sst.connect('end', lambda s, stat: self._on_end(stat)),
                                sst.connect('dark', lambda s, mean, std, num, what: self._on_data(mean, std, num, what), 'dark'),
                                sst.connect('empty', lambda s, mean, std, num, what: self._on_data(mean, std, num, what), 'empty'),
                                sst.connect('sample', lambda s, mean, std, num, what: self._on_data(mean, std, num, what), 'sample'),
                                sst.connect('transm', lambda s, mean, std, num: self._on_transm(mean, std, num)),
                                ]
                self._entrytab.set_sensitive(False)
                self.get_widget_for_response(respid).set_label(Gtk.STOCK_STOP)
                for ch in self.get_action_area().get_children():
                    ch.set_sensitive(False)
                sst.execute()
                self.get_widget_for_response(respid).set_sensitive(True)
        elif respid == Gtk.ResponseType.APPLY:
            sam = self.credo.subsystems['Samples'].set(self._sample_combo.get_sample().title)
            sam.transmission = sastool.classes.ErrorValue(self._transmresult[0], self._transmresult[1])
            self.credo.subsystems['Samples'].save()
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, 'Updated transmission of sample %s!' % str(sam))
            md.format_secondary_text('Sample configuration also saved to file %s.' % self.credo.subsystems['Samples'].configfile)
            md.run()
            md.destroy()
            del md
            self._transmresult = None
            self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        else:
            if self._transmresult is not None:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, 'Transmission not yet saved! Do you want to save it?')
                if md.run() == Gtk.ResponseType.YES:
                    self.do_response(Gtk.ResponseType.APPLY)
                md.destroy()
                del md
                
            self.destroy()
    def clear_data(self):
        for what in ['dark', 'empty', 'sample']:
            for how in ['mean', 'stddev', '#']:
                self._resultlabels[what][how].set_text('N/A')
    def _on_end(self, status):
        for c in self._tsconn:
            self.credo.subsystems['Transmission'].disconnect(c)
        self._tsconn = []
        self._entrytab.set_sensitive(True)
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label(Gtk.STOCK_EXECUTE)
        for ch in self.get_action_area().get_children():
            ch.set_sensitive(True)
        pass
    def _on_data(self, mean, std, num, what):
        self._resultlabels[what]['mean'].set_text('%.4f' % mean)
        self._resultlabels[what]['stddev'].set_text('%.4f' % std)
        self._resultlabels[what]['#'].set_text('%d' % num)
    def _on_transm(self, mean, std, num):
        self._transm_label.set_text('%.4f +/- %.4f (from %d points)' % (mean, std, num))
        self._transmresult = (mean, std, num)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, True)
