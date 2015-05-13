from gi.repository import Gtk
from gi.repository import GLib

from .widgets import ToolDialog
from . import scangraph
import logging
import datetime
import time
import math
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ScanDeviceSelector(Gtk.ComboBoxText):

    def __init__(self, credo):
        Gtk.ComboBoxText.__init__(self)
        self.credo = credo
        self._fromcredo()

    def _fromcredo(self):
        for i, sd in enumerate(self.credo.subsystems['Scan'].get_supported_devices()):
            self.append_text(sd)
            if self.credo.subsystems['Scan'].devicename == sd:
                self.set_active(i)

    def _tocredo(self):
        self.credo.subsystems['Scan'].devicename = self.get_active_text()

    def get(self):
        return self.get_active_text()

    def set(self, devname):
        self.credo.subsystems['Scan'].devicename = devname
        for i, row in enumerate(self.get_model()):
            if row[0] == devname:
                self.set_active(i)
                return
        raise NotImplementedError('Cannot set active device.')


class Scan(ToolDialog):
    __gsignals__ = {'response': 'override'}

    def __init__(self, credo, title='Scan'):
        ToolDialog.__init__(self, credo, title, buttons=(
            'Execute', Gtk.ResponseType.OK, 'Close', Gtk.ResponseType.CLOSE))
        vb = self.get_content_area()
        self.entrytable = Gtk.Grid()
        self.entrytable.set_hexpand(True)
        self.entrytable.set_vexpand(True)
        vb.pack_start(self.entrytable, False, True, 0)
        self.set_resizable(True)
        row = 0

        l = Gtk.Label(label='Scan device:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, row, 1, 1)
        self.scandevice_selector = ScanDeviceSelector(self.credo)
        self.scandevice_selector.set_hexpand(True)
        self.entrytable.attach(self.scandevice_selector, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Comment:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, row, 1, 1)
        self.samplename_entry = Gtk.Entry()
        self.samplename_entry.set_text(self.credo.subsystems['Scan'].comment)
        self.samplename_entry.set_hexpand(True)
        self.entrytable.attach(self.samplename_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Counting time (s):')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, row, 1, 1)
        self.exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            lower=0, upper=100, step_increment=0.1, page_increment=1), digits=4)
        self.exptime_entry.set_value(
            self.credo.subsystems['Scan'].countingtime)
        self.exptime_entry.set_hexpand(True)
        self.entrytable.attach(self.exptime_entry, 1, row, 1, 1)
        row += 1

        self.symmetric_scan_check = Gtk.CheckButton(label='Symmetric scan')
        self.symmetric_scan_check.set_halign(Gtk.Align.START)
        self.entrytable.attach(self.symmetric_scan_check, 0, row, 2, 1)
        row += 1

        self.start_label = Gtk.Label(label='Start:')
        self.start_label.set_halign(Gtk.Align.START)
        self.start_label.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(self.start_label, 0, row, 1, 1)
        self.start_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            lower=-1e9, upper=1e9, step_increment=1, page_increment=10), digits=4)
        self.entrytable.attach(self.start_entry, 1, row, 1, 1)
        self.start_entry.set_value(self.credo.subsystems['Scan'].value_begin)
        self.start_entry.connect(
            'value-changed', lambda sb: self._recalculate_stepsize())
        row += 1

        self.end_label = Gtk.Label(label='End:')
        self.end_label.set_halign(Gtk.Align.START)
        self.end_label.set_valign(Gtk.Align.CENTER)
        self.end_label.set_no_show_all(True)
        self.entrytable.attach(self.end_label, 0, row, 1, 1)
        self.end_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            lower=-1e9, upper=1e9, step_increment=1, page_increment=10), digits=4)
        self.end_entry.set_no_show_all(True)
        self.entrytable.attach(self.end_entry, 1, row, 1, 1)
        self.end_entry.set_value(self.credo.subsystems['Scan'].value_end)
        self.end_entry.connect(
            'value-changed', lambda sb: self._recalculate_stepsize())
        row += 1

        self.symmetric_scan_check.connect(
            'toggled', self.on_symmetric_scan_toggled)

        l = Gtk.Label(label='Number of steps:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, row, 1, 1)
        self.step_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            lower=2, upper=1e9, step_increment=1, page_increment=10), digits=0)
        self.entrytable.attach(self.step_entry, 1, row, 1, 1)
        self.step_entry.set_value(self.credo.subsystems['Scan'].nstep)
        self.step_entry.connect(
            'value-changed', lambda sb: self._recalculate_stepsize())
        row += 1

        l = Gtk.Label(label='Step size:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, row, 1, 1)
        self.stepsize_label = Gtk.Label(label='--')
        self.stepsize_label.set_halign(Gtk.Align.START)
        self.stepsize_label.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(self.stepsize_label, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Delay between exposures (s):')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, row, 1, 1)
        self.dwelltime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            lower=0.003, upper=10000, step_increment=1, page_increment=10), digits=4)
        self.dwelltime_entry.set_value(self.credo.subsystems['Scan'].waittime)
        self.entrytable.attach(self.dwelltime_entry, 1, row, 1, 1)
        row += 1

#        self.shutter_checkbutton = Gtk.CheckButton('Open shutter at start and close at end')
#        self.shutter_checkbutton.set_halign(Gtk.Align.START)
#        self.entrytable.attach(self.shutter_checkbutton, 0, 2, row, row + 1)
#        self.shutter_checkbutton.set_active(self.credo.subsystems['Scan'].operate_shutter)
#        row += 1

        self.autoreturn_checkbutton = Gtk.CheckButton(
            'Auto-return to start at end')
        self.autoreturn_checkbutton.set_halign(Gtk.Align.START)
        self.entrytable.attach(self.autoreturn_checkbutton, 0, row, 2, 1)
        self.autoreturn_checkbutton.set_active(
            self.credo.subsystems['Scan'].autoreturn)
        row += 1

        l = Gtk.Label(label='Iterations:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, row, 1, 1)
        self.repetitions_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            lower=1, upper=100000, step_increment=1, page_increment=10), digits=0)
        self.repetitions_entry.set_value(1)
        self.entrytable.attach(self.repetitions_entry, 1, row, 1, 1)
        row += 1

        self._progress_frame = Gtk.Frame(label='Progress')
        self._progress_frame.set_no_show_all(True)
        self.get_content_area().pack_start(
            self._progress_frame, False, False, 0)
        self._progressbar = Gtk.ProgressBar()
        self._progress_frame.add(self._progressbar)
        self._progressbar.set_show_text(True)
        self._progressbar.show()

        self.lazystop_button = Gtk.ToggleButton(label="Stop after current run")
        self.lazystop_button.connect('toggled', self.on_lazystop)
        self.lazystop_button.set_sensitive(False)
        self.get_action_area().pack_start(
            self.lazystop_button, False, False, 0)

        self._recalculate_stepsize()
        self.on_symmetric_scan_toggled(self.symmetric_scan_check)
        vb.show_all()

    def on_symmetric_scan_toggled(self, sscb):
        if sscb.get_active():
            self.end_label.hide()
            self.end_entry.hide()
            self.start_label.set_text('Half scan width:')
        else:
            self.end_label.show()
            self.end_entry.show()
            self.start_label.set_text('Start:')
        self._recalculate_stepsize()

    def _recalculate_stepsize(self):
        if self.symmetric_scan_check.get_active():
            self.stepsize_label.set_label(
                str((self.start_entry.get_value() * 2) / (self.step_entry.get_value_as_int() - 1)))
        else:
            self.stepsize_label.set_label(str((self.end_entry.get_value(
            ) - self.start_entry.get_value()) / (self.step_entry.get_value_as_int() - 1)))

    def on_lazystop(self, button):
        if self.lazystop_button.get_active():
            self.lazystop_button.set_label('Will stop...')
        else:
            self.lazystop_button.set_label('Stop after current run')

    def start_scan(self):
        if self.repetitions_entry.get_value_as_int() == 0:
            return
        self.credo.subsystems['Samples'].set(None)
        self.credo.subsystems[
            'Scan'].countingtime = self.exptime_entry.get_value()
        self.credo.subsystems[
            'Scan'].waittime = self.dwelltime_entry.get_value()
        self.credo.subsystems[
            'Scan'].devicename = self.scandevice_selector.get()
        if self.symmetric_scan_check.get_active():
            self.credo.subsystems['Scan'].value_begin = self.credo.subsystems[
                'Scan'].scandevice.where() - self.start_entry.get_value()
            self.credo.subsystems['Scan'].value_end = self.credo.subsystems[
                'Scan'].scandevice.where() + self.start_entry.get_value()
        else:
            self.credo.subsystems[
                'Scan'].value_begin = self.start_entry.get_value()
            self.credo.subsystems[
                'Scan'].value_end = self.end_entry.get_value()
        self.credo.subsystems[
            'Scan'].nstep = self.step_entry.get_value_as_int()
        self.credo.subsystems[
            'Scan'].comment = self.samplename_entry.get_text()
        self.credo.subsystems[
            'Scan'].autoreturn = self.autoreturn_checkbutton.get_active()
        self._scanconnections = [self.credo.subsystems['Scan'].connect('scan-end', self._scan_end),
                                 self.credo.subsystems['Scan'].connect(
                                     'scan-report', self._scan_report),
                                 self.credo.subsystems['Scan'].connect('scan-fail', self._scan_fail)]
        try:
            logger.debug('Preparing scan.')
            self.credo.subsystems['Scan'].prepare()
            logger.debug('Setting up scangraph')
            self._scangraph = scangraph.ScanGraph(self.credo.subsystems[
                                                  'Scan'].currentscan, self.credo, 'Scan #%d' % (self.credo.subsystems['Scan'].currentscan.fsn))
            print(self.credo.username, type(self.credo.username))
            uname = self.credo.username
            self._scangraph.figtext(
                1, 0, self.credo.username + '@' + 'CREDO  ' + str(datetime.datetime.now()), ha='right', va='bottom')
            self._scangraph.show_all()
            self._scangraph.set_scalers(
                [(vd.name, vd.visible, vd.scaler) for vd in self.credo.subsystems['VirtualDetectors']])
            self._scangraph.is_recording = True
            logger.debug('Starting scan')
            self.credo.subsystems['Scan'].start()
            logger.debug('Adjusting GUI sensitivity')
            self.entrytable.set_sensitive(False)
            self.set_sensitive(False)
            logger.debug('Scan started')
        except Exception as exc:
            md = Gtk.MessageDialog(transient_for=self, destroy_with_parent=True, modal=True,
                                   type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, message_format='Error starting scan.')
            md.format_secondary_markup(
                '<b>Reason:</b>\n' + str(traceback.format_exc()))
            md.run()
            md.destroy()
            self.entrytable.set_sensitive(True)
            self.set_sensitive(True)
            self.lazystop_button.set_sensitive(False)
        else:
            self.set_sensitive(True)
            self.entrytable.set_sensitive(False)
            self.get_widget_for_response(Gtk.ResponseType.OK).set_label('Stop')
            self.lazystop_button.set_sensitive(True)
            self._progress_frame.show_now()
            self._progressbar.set_fraction(0.0)
            self._progressbar.set_text('Estimating end time...')
            self._starttime = time.time()

    def do_response(self, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            if self.get_sensitive() and self.get_widget_for_response(Gtk.ResponseType.OK).get_label() == 'Execute':
                self.destroy()
                return True
            else:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                       Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot close window: a scan is running.')
                md.run()
                md.destroy()
                del md
                return True
        if respid == Gtk.ResponseType.OK:
            if self.get_widget_for_response(respid).get_label() == 'Stop':
                self.set_response_sensitive(respid, False)
                self.credo.subsystems['Scan'].kill()
            elif self.get_widget_for_response(respid).get_label() == 'Execute':
                self.start_scan()
            else:
                raise NotImplementedError

    def _scan_end(self, subsys, state):
        logger.debug('last scan point received.')
        try:
            for c in self._scanconnections:
                subsys.disconnect(c)
            del self._scanconnections
        except AttributeError:
            pass
        if self.lazystop_button.get_active():
            state = False
        if not state:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT |
                                   Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, 'User break!')
            md.run()
            md.destroy()
            del md
        # should do one more run
        if state and (self.repetitions_entry.get_value_as_int() > 1):
            self.repetitions_entry.set_value(
                self.repetitions_entry.get_value_as_int() - 1)
            logger.info('Re-starting scan: %d repetitions left' %
                        (self.repetitions_entry.get_value_as_int()))
            GLib.idle_add(lambda: self.start_scan() and False)
        else:
            logger.info('Scan ended, no repetitions requested.')
            self.get_widget_for_response(
                Gtk.ResponseType.OK).set_label('Execute')
            self.set_response_sensitive(Gtk.ResponseType.OK, True)
            self.lazystop_button.set_sensitive(False)
            self.entrytable.set_sensitive(True)
            self._progress_frame.hide()
            self._scangraph.is_recording = False
        return True

    def _scan_report(self, subsys, scan):
        self._scangraph.redraw_scan()
        self._progressbar.set_fraction(
            len(self.credo.subsystems['Scan'].currentscan) / self.step_entry.get_value())
        remaining = (time.time() - self._starttime) / len(self.credo.subsystems['Scan'].currentscan) * (
            self.step_entry.get_value() - len(self.credo.subsystems['Scan'].currentscan))
        remainingmin = math.floor(remaining / 60.)
        remainingsec = remaining - remainingmin * 60
        self._progressbar.set_text(
            'Est. remaining: %02d:%02d' % (remainingmin, remainingsec))

    def _scan_fail(self, subsys, mesg):
        md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT |
                               Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Scan failure')
        md.format_secondary_text(mesg)
        md.run()
        md.destroy()
        del md
