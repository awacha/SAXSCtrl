from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GLib
import sastool
from .spec_filechoosers import MaskEntryWithButton
from .samplesetup import SampleSelector
from .widgets import ToolDialog
from ..hardware.subsystems.transmission import TransmissionException


class TransmissionMeasurement(ToolDialog):

    def __init__(self, credo, title='Transmission measurement'):
        ToolDialog.__init__(self, credo, title, buttons=(
            'Execute', Gtk.ResponseType.OK, 'Save', Gtk.ResponseType.APPLY, 'Close', Gtk.ResponseType.CLOSE))
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        self._tsconn = []
        self._transmresult = None
        sst = self.credo.subsystems['Transmission']
        vb = self.get_content_area()
        self._entrytab = Gtk.Table()
        vb.pack_start(self._entrytab, False, True, 0)
        row = 0

        l = Gtk.Label(label='Sample:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self._entrytab.attach(
            l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._sample_combo = SampleSelector(self.credo, autorefresh=False)
        try:
            self._sample_combo.set_sample(sst.samplename)
        except ValueError:
            pass
        self._entrytab.attach(self._sample_combo, 1, 2, row, row + 1)
        self._sample_combo.connect(
            'sample-changed', lambda combo, sample: self.clear_data())
        row += 1

        l = Gtk.Label(label='Empty sample:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self._entrytab.attach(
            l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._empty_combo = SampleSelector(self.credo, autorefresh=False)
        try:
            self._empty_combo.set_sample(sst.emptyname)
        except ValueError:
            pass
        self._entrytab.attach(self._empty_combo, 1, 2, row, row + 1)
        self._empty_combo.connect(
            'sample-changed', lambda combo, sample: self.clear_data())
        row += 1

        l = Gtk.Label(label='Exposure time:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self._entrytab.attach(
            l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._exptime_entry = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(sst.countingtime, 0.0001, 1e10, 1, 10), digits=4)
        self._exptime_entry.set_value(sst.countingtime)
        self._entrytab.attach(self._exptime_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Number of exposures:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self._entrytab.attach(
            l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._nimages_entry = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(sst.nimages, 1, 1e10, 1, 10), digits=0)
        self._nimages_entry.set_value(sst.nimages)
        self._entrytab.attach(self._nimages_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Number of iterations:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self._entrytab.attach(
            l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._ncycles_entry = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(sst.iterations, 1, 1e10, 1, 10), digits=0)
        self._ncycles_entry.set_value(sst.iterations)
        self._entrytab.attach(self._ncycles_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Mask for beam area:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self._entrytab.attach(
            l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self._mask_entry = MaskEntryWithButton(self.credo)
        self._mask_entry.set_filename(sst.mask)
        self._entrytab.attach(self._mask_entry, 1, 2, row, row + 1)
        row += 1

        l = Gtk.Label(label='Method for intensity determination:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self._entrytab.attach(
            l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
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
            l = Gtk.Label(what + ':')
            l.set_halign(Gtk.Align.START)
            l.set_valign(Gtk.Align.CENTER)
            what = what.split()[0].lower()
            self._resultstable.attach(
                l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
            self._resultlabels[what] = {}
            for column, how in enumerate(['Mean cps', 'Stddev cps', '# of exposures'], 1):
                if row == 1:
                    l = Gtk.Label(how)
                    l.set_halign(Gtk.Align.START)
                    l.set_valign(Gtk.Align.CENTER)
                    self._resultstable.attach(
                        l, column, column + 1, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
                how = how.split()[0].lower()
                self._resultlabels[what][how] = Gtk.Label(label='0')
                self._resultstable.attach(
                    self._resultlabels[what][how], column, column + 1, row, row + 1, xpadding=10)

        f = Gtk.Frame(label='Measured transmission')
        vb.pack_start(f, True, True, 0)
        hb = Gtk.HBox()
        f.add(hb)
        self._transm_label = Gtk.Label(label='--')
        hb.pack_start(self._transm_label, False, True, 0)

    def do_response(self, respid):
        if respid == Gtk.ResponseType.OK:
            if self.get_widget_for_response(respid).get_label() == 'Stop':
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
                                sst.connect('dark', lambda s, mean, std, num, what: self._on_data(
                                    mean, std, num, what), 'dark'),
                                sst.connect('empty', lambda s, mean, std, num, what: self._on_data(
                                    mean, std, num, what), 'empty'),
                                sst.connect('sample', lambda s, mean, std, num, what: self._on_data(
                                    mean, std, num, what), 'sample'),
                                sst.connect(
                                    'transm', lambda s, mean, std, num: self._on_transm(mean, std, num)),
                                ]
                self._entrytab.set_sensitive(False)
                self.get_widget_for_response(respid).set_label('Stop')
                for ch in self.get_action_area().get_children():
                    ch.set_sensitive(False)
                try:
                    sst.execute()
                except TransmissionException as te:
                    md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                           Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Error starting transmission measurement')
                    md.format_secondary_text('Reason: ' + str(te))
                    md.run()
                    md.destroy()
                    del md
                    self._entrytab.set_sensitive(True)
                    self.get_widget_for_response(respid).set_label('Execute')
                    for ch in self.get_action_area().get_children():
                        ch.set_sensitive(True)
                    return
                self.get_widget_for_response(respid).set_sensitive(True)
        elif respid == Gtk.ResponseType.APPLY:
            sam = self.credo.subsystems['Samples'].set(
                self._sample_combo.get_sample().title)
            sam.transmission = sastool.classes.ErrorValue(
                self._transmresult[0], self._transmresult[1])
            self.credo.subsystems['Samples'].save()
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                   Gtk.MessageType.INFO, Gtk.ButtonsType.OK, 'Updated transmission of sample %s!' % str(sam))
            md.format_secondary_text(
                'Sample configuration also saved to file %s.' % self.credo.subsystems['Samples'].configfile)
            md.run()
            md.destroy()
            del md
            self._transmresult = None
            self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        else:
            if self._transmresult is not None:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                       Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, 'Transmission not yet saved! Do you want to save it?')
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
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label('Execute')
        for ch in self.get_action_area().get_children():
            ch.set_sensitive(True)
        pass

    def _on_data(self, mean, std, num, what):
        self._resultlabels[what]['mean'].set_text('%.4f' % mean)
        self._resultlabels[what]['stddev'].set_text('%.4f' % std)
        self._resultlabels[what]['#'].set_text('%d' % num)

    def _on_transm(self, mean, std, num):
        self._transm_label.set_text(
            '%.4f +/- %.4f (from %d points)' % (mean, std, num))
        self._transmresult = (mean, std, num)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, True)

RESP_ADD = 1
RESP_DEL = 2
RESP_CLEAR = 3


class TransmissionMeasurementMulti(ToolDialog):

    def __init__(self, credo, title='Transmission measurement from multiple samples'):
        ToolDialog.__init__(self, credo, title, buttons=('Execute', Gtk.ResponseType.OK, 'Add',
                                                         RESP_ADD, 'Remove', RESP_DEL, 'Clear', RESP_CLEAR, 'Close', Gtk.ResponseType.CLOSE))
        self._basicsettings_expander = Gtk.Expander(label='Basic settings')
        self.get_content_area().pack_start(
            self._basicsettings_expander, False, False, 0)
        grid = Gtk.Grid()
        self._basicsettings_expander.add(grid)
        row = 0

        sst = self.credo.subsystems['Transmission']
        l = Gtk.Label(label='Empty sample:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._empty_combo = SampleSelector(self.credo, autorefresh=False)
        self._empty_combo.set_sample(sst.emptyname)
        grid.attach(self._empty_combo, 1, row, 1, 1)
        self._empty_combo.set_hexpand(True)
        row += 1

        l = Gtk.Label(label='Exposure time:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._exptime_entry = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(0.5, 0.0001, 1e10, 1, 10), digits=4)
        self._exptime_entry.set_value(sst.countingtime)
        grid.attach(self._exptime_entry, 1, row, 1, 1)
        self._exptime_entry.set_hexpand(True)
        row += 1

        l = Gtk.Label(label='Number of exposures:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._nimages_entry = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(10, 1, 10000, 1, 10), digits=0)
        self._nimages_entry.set_value(sst.nimages)
        grid.attach(self._nimages_entry, 1, row, 1, 1)
        self._nimages_entry.set_hexpand(True)
        row += 1

        l = Gtk.Label(label='Number of iterations:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._ncycles_entry = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(1, 1, 1e10, 1, 10), digits=0)
        self._ncycles_entry.set_value(sst.iterations)
        grid.attach(self._ncycles_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Mask for beam area:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._mask_entry = MaskEntryWithButton(self.credo)
        self._mask_entry.set_filename(sst.mask)
        grid.attach(self._mask_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Method for intensity determination:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._method_combo = Gtk.ComboBoxText()
        grid.attach(self._method_combo, 1, row, 1, 1)
        for i, m in enumerate(['max', 'sum', 'mean']):
            self._method_combo.append_text(m)
            if sst.method == m:
                self._method_combo.set_active(i)
        row += 1

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_size_request(-1, 300)
        self.get_content_area().pack_start(sw, True, True, 0)
        # sample list: name, Idark mean, Idark std, I0 mean, I0 std, I1 mean,
        # I1 std, transm mean, transm std, spinner active, spinner pulse
        self._allsamplenames = Gtk.ListStore(GObject.TYPE_STRING)
        sss = self.credo.subsystems['Samples']
        sss.connect('changed', self._on_samples_changed)
        self._on_samples_changed(sss)
        self._samplelist = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_FLOAT, GObject.TYPE_FLOAT, GObject.TYPE_FLOAT, GObject.TYPE_FLOAT,
                                         GObject.TYPE_FLOAT, GObject.TYPE_FLOAT, GObject.TYPE_FLOAT, GObject.TYPE_FLOAT, GObject.TYPE_BOOLEAN, GObject.TYPE_UINT)
        self._sampleview = Gtk.TreeView(self._samplelist)
        self._sampleview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        sw.add(self._sampleview)
        crspinner = Gtk.CellRendererSpinner()
        # crspinner.set_property('size', Gtk.IconSize.MENU)
        self._sampleview.append_column(
            Gtk.TreeViewColumn('', crspinner, active=9, pulse=10))
        crcombo = Gtk.CellRendererCombo()
        crcombo.set_property('has-entry', False)
        crcombo.set_property('model', self._allsamplenames)
        crcombo.set_property('text-column', 0)
        crcombo.set_property('editable', True)
        crcombo.connect('changed', self._on_sample_selected)
        self._sampleview.append_column(
            Gtk.TreeViewColumn('Sample', crcombo, text=0))
        for i, title in enumerate(['mean Idark', 'std Idark', 'mean I0', 'std I0', 'mean I1', 'std I1', 'Transmission', 'Sigma T']):
            crtext = Gtk.CellRendererText()
            self._sampleview.append_column(
                Gtk.TreeViewColumn(title, crtext, text=i + 1))
        self._tsconn = []

    def _on_sample_selected(self, crcombo, path, newiter):
        self._samplelist[path][0] = crcombo.get_property('model')[newiter][0]

    def _on_samples_changed(self, sss):
        self._allsamplenames.clear()
        for sam in sss:
            self._allsamplenames.append([sam.title])

    def _measure_transmission(self):
        sst = self.credo.subsystems['Transmission']
        active_row = [
            i for i in range(len(self._samplelist)) if self._samplelist[i][9]][0]
        sst.samplename = self._samplelist[active_row][0]
        try:
            sst.execute()
        except TransmissionException as te:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                   Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Error starting transmission measurement')
            md.format_secondary_text('Reason: ' + str(te))
            md.run()
            md.destroy()
            del md
            self._cleanup_after_measurement()
            return

    def _idle_function(self):
        for row in self._samplelist:
            row[10] += 1
        return True

    def _cleanup_after_measurement(self):
        if not hasattr(self, '_tsconn') or (self._tsconn is None):
            self._tsconn = []
        for c in self._tsconn:
            self.credo.subsystems['Transmission'].disconnect(c)
        self._tsconn = []
        self._basicsettings_expander.set_sensitive(True)
        self._sampleview.set_sensitive(True)
        self.get_widget_for_response(Gtk.ResponseType.OK).set_label('Execute')
        for ch in self.get_action_area().get_children():
            ch.set_sensitive(True)
        if hasattr(self, '_timer_handler'):
            GLib.source_remove(self._timer_handler)
            del self._timer_handler
        for row in self._samplelist:
            row[9] = False
            row[10] = 0

    def do_response(self, respid):
        if respid == Gtk.ResponseType.OK:
            if self.get_widget_for_response(respid).get_label() == 'Stop':
                self.credo.subsystems['Transmission'].kill()
            else:
                if len(self._samplelist) == 0:
                    return True
                sst = self.credo.subsystems['Transmission']
                sst.countingtime = self._exptime_entry.get_value()
                sst.emptyname = self._empty_combo.get_sample().title
                sst.nimages = self._nimages_entry.get_value_as_int()
                sst.iterations = self._ncycles_entry.get_value_as_int()
                sst.mask = self._mask_entry.get_filename()
                sst.method = self._method_combo.get_active_text()
                sst.move_beamstop_back_at_end = (len(self._samplelist) == 1)

                self._tsconn = [sst.connect('end', lambda s, stat: self._on_end(stat)),
                                sst.connect('dark', lambda s, mean, std, num, what: self._on_data(
                                    mean, std, num, what), 'dark'),
                                sst.connect('empty', lambda s, mean, std, num, what: self._on_data(
                                    mean, std, num, what), 'empty'),
                                sst.connect('sample', lambda s, mean, std, num, what: self._on_data(
                                    mean, std, num, what), 'sample'),
                                sst.connect(
                                    'transm', lambda s, mean, std, num: self._on_transm(mean, std, num)),
                                ]
                self._timer_handler = GLib.timeout_add(
                    100, self._idle_function)
                self._basicsettings_expander.set_sensitive(False)
                self._sampleview.set_sensitive(False)
                self.get_widget_for_response(respid).set_label('Stop')
                for ch in self.get_action_area().get_children():
                    ch.set_sensitive(False)
                for row in self._samplelist:
                    for i in range(1, 9):
                        row[i] = 0
                self._samplelist[0][9] = True
                self._measure_transmission()
                self.get_widget_for_response(respid).set_sensitive(True)
        elif respid == RESP_ADD:
            self._samplelist.append(
                [self._allsamplenames[0][0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, 0])
        elif respid == RESP_DEL:
            model, iter_ = self._sampleview.get_selection().get_selected()
            if iter_ is not None:
                model.remove(iter_)
        elif respid == RESP_CLEAR:
            self._samplelist.clear()
        else:
            if self.get_widget_for_response(Gtk.ResponseType.OK).get_label() == 'Stop':
                self.credo.subsystems['Transmission'].kill()
            self._cleanup_after_measurement()
            self.destroy()

    def _on_end(self, status):
        if not status:
            self.credo.subsystems[
                'Transmission'].move_beamstop_back_at_end = True
            self._cleanup_after_measurement()
            return
        active_row = [
            i for i in range(len(self._samplelist)) if self._samplelist[i][9]][0]
        if active_row == len(self._samplelist) - 1:
            self._cleanup_after_measurement()
            return
        else:
            self._samplelist[active_row][9] = False
            self._samplelist[active_row + 1][9] = True
            if active_row + 1 == len(self._samplelist) - 1:
                self.credo.subsystems[
                    'Transmission'].move_beamstop_back_at_end = True
            self._measure_transmission()

    def _on_data(self, mean, std, num, what):
        active_row = [
            i for i in range(len(self._samplelist)) if self._samplelist[i][9]][0]
        if what == 'dark':
            self._samplelist[active_row][1] = mean
            self._samplelist[active_row][2] = std
        elif what == 'empty':
            self._samplelist[active_row][3] = mean
            self._samplelist[active_row][4] = std
        else:
            self._samplelist[active_row][5] = mean
            self._samplelist[active_row][6] = std

    def _on_transm(self, mean, std, num):
        active_row = [
            i for i in range(len(self._samplelist)) if self._samplelist[i][9]][0]
        self._samplelist[active_row][7] = mean
        self._samplelist[active_row][8] = std
        sam = self.credo.subsystems['Samples'].set(
            self._samplelist[active_row][0])
        sam.transmission = sastool.classes.ErrorValue(mean, std)
        self.credo.subsystems['Samples'].save()
