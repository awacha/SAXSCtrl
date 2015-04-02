from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GLib

import traceback
from .spec_filechoosers import MaskEntryWithButton
import time
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ExposureFrame(Gtk.Frame):
    __gsignals__ = {'started':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'image':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'destroy':'override'}
    def __init__(self, credo, fixedformat=None):
        Gtk.Frame.__init__(self, label='Expose...')
        self._connections = []
        self.credo = credo
        grid = Gtk.Grid()
        self.add(grid)
        row = 0
        l = Gtk.Label(label='Filename prefix:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._fileformat_entry = Gtk.ComboBoxText.new_with_entry()
        for i, f in enumerate(self.credo.subsystems['Files'].formats()):
            self._fileformat_entry.append_text(f)
            if (fixedformat is not None):
                if f == fixedformat:
                    self._fileformat_entry.set_active(i)
            elif f == self.credo.subsystems['Files'].filebegin:
                self._fileformat_entry.set_active(i)
        self._connections.append((self._fileformat_entry, self._fileformat_entry.connect('changed', lambda ffe:self._fileformat_entry_changed())))
        if fixedformat is None:
            self._connections.append((self.credo.subsystems['Files'], self.credo.subsystems['Files'].connect('notify::filebegin', self._on_filebegin_changed)))
        if fixedformat is not None:
            self._fileformat_entry.set_sensitive(False)
        self._fileformat_entry.set_hexpand(True)
        grid.attach(self._fileformat_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Exposure time (sec):'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._exptime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=10, lower=0.0001, upper=3600 * 24 * 7, step_increment=10, page_increment=100), digits=4)
        self._exptime_entry.set_value(self.credo.subsystems['Exposure'].exptime)
        grid.attach(self._exptime_entry, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Dwell time (sec):'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._dwelltime_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=0.003, lower=0.003, upper=3600 * 24 * 7, step_increment=10, page_increment=100), digits=4)
        grid.attach(self._dwelltime_entry, 1, row, 1, 1)
        self._dwelltime_entry.set_value(self.credo.subsystems['Exposure'].dwelltime)
        self._dwelltime_entry.set_sensitive(False)
        row += 1

        l = Gtk.Label(label='Number of images:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._nimages_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(value=1, lower=1, upper=9999999999, step_increment=1, page_increment=10), digits=0)
        grid.attach(self._nimages_entry, 1, row, 1, 1)
        self._nimages_entry.set_value(self.credo.subsystems['Exposure'].nimages)
        self._connections.append((self._nimages_entry, self._nimages_entry.connect('value-changed', lambda sb:self._dwelltime_entry.set_sensitive(self._nimages_entry.get_value_as_int() > 1))))
        row += 1

        l = Gtk.Label(label='Mask file:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._maskfile_entry = MaskEntryWithButton(self.credo)
        grid.attach(self._maskfile_entry, 1, row, 1, 1)
        self._maskfile_entry.set_filename(self.credo.subsystems['Exposure'].default_mask)
        row += 1

        l = Gtk.Label(label='Next FSN:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        if fixedformat:
            self._nextfsn_label = Gtk.Label(label=str(self.credo.subsystems['Files'].get_next_fsn(self.credo.subsystems['Files'].get_format_re(fixedformat, None))))
        else:
            self._nextfsn_label = Gtk.Label(label=str(self.credo.subsystems['Files'].get_next_fsn()))
        self._connections.append((self.credo.subsystems['Files'], self.credo.subsystems['Files'].connect('new-nextfsn', lambda ssf, fsn, regex: (regex.startswith(self._fileformat_entry.get_active_text()) and  (self._nextfsn_label.set_text(str(fsn)))))))
        grid.attach(self._nextfsn_label, 1, row, 1, 1)
        row += 1

        self.exposure_progress = Gtk.ProgressBar()
        self.exposure_progress.set_no_show_all(True)
        self.exposure_progress.set_show_text(True)
        grid.attach(self.exposure_progress, 0, row, 1, 2)
        row += 1

        self.nimages_progress = Gtk.ProgressBar()
        self.nimages_progress.set_no_show_all(True)
        self.nimages_progress.set_show_text(True)
        grid.attach(self.nimages_progress, 0, row, 1, 2)
        row += 1

        self._conns = []
        self.show_all()
        self._starttime = None
        self._remtime_timeout = None
        self._images_remaining = 0
    def do_destroy(self):
        if hasattr(self, '_conns'):
            for c in self._conns:
                self.credo.subsystems['Exposure'].disconnect(c)
        if hasattr(self, '_connections'):
            for entity, c in self._connections:
                entity.disconnect(c)
    def _on_filebegin_changed(self, ssf, par=None):
        idx = [i for i, row in enumerate(self._fileformat_entry.get_model()) if row[0] == ssf.filebegin]
        if not idx:
            self._fileformat_entry.append_text(ssf.filebegin)
            idx = [i for i, row in enumerate(self._fileformat_entry.get_model()) if row[0] == ssf.filebegin]
        self._fileformat_entry.set_active(idx[0])
    def _fileformat_entry_changed(self):
        self._nextfsn_label.set_text(str(self.credo.subsystems['Files'].get_next_fsn(self.credo.subsystems['Files'].get_format_re(self._fileformat_entry.get_active_text(), None))))
    def execute(self, header_template={}, write_nexus=False):
        if self.credo.subsystems['Files'].filebegin != self._fileformat_entry.get_active_text():
            self.credo.subsystems['Files'].filebegin = self._fileformat_entry.get_active_text()
        self._conns = [self.credo.subsystems['Exposure'].connect('exposure-image', lambda sse, img: self.emit('image', img)),
                       self.credo.subsystems['Exposure'].connect('exposure-fail', lambda sse, err: self.emit('fail', err)),
                       self.credo.subsystems['Exposure'].connect('exposure-end', lambda sse, state: self.emit('end', state)), ]
        self._images_remaining = self._nimages_entry.get_value_as_int()
        try:
            fsn = self.credo.expose(self._exptime_entry.get_value(), self._nimages_entry.get_value_as_int(), self._dwelltime_entry.get_value(), self._maskfile_entry.get_mask(), header_template=header_template, write_nexus=write_nexus)
            logger.info('Started exposure for %g seconds at %s (%d images requested).' % (self._exptime_entry.get_value(), self.credo.subsystems['Files'].get_fileformat() % fsn, self._nimages_entry.get_value_as_int()))
            self._starttime = time.time()
        except Exception as exc:
            md = Gtk.MessageDialog(transient_for=self.get_toplevel(), destroy_with_parent=True,
                                   modal=True, type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, message_format='Error starting exposure')
            md.format_secondary_text(traceback.format_exc(exc))
            md.run()
            md.destroy()
            del md
        else:
            self.emit('started')
    def do_started(self):
        self.set_sensitive(False)
        self.exposure_progress.show()
        if self._nimages_entry.get_value_as_int() > 1:
            self.nimages_progress.show()
        self._remtime_timeout = GLib.timeout_add(500, self._update_remtime)
    def do_image(self, img):
        logger.debug('Exposureframe::image')
        self._images_remaining -= 1
        self._starttime = time.time()
    def _update_remtime(self):
        remtime = self._exptime_entry.get_value() - time.time() + self._starttime
        if remtime >= 0:
            self.exposure_progress.set_fraction(1 - remtime / self._exptime_entry.get_value())
            self.exposure_progress.set_text('Remaining time: %.2f sec' % remtime)
        else:
            self.exposure_progress.set_text('Waiting for image...')
            self.exposure_progress.pulse()
        if self._nimages_entry.get_value_as_int() > 1:
            self.nimages_progress.set_fraction(1 - self._images_remaining / self._nimages_entry.get_value())
            self.nimages_progress.set_text('%d images remaining' % self._images_remaining)
        return True
    def do_end(self, state):
        self.set_sensitive(True)
        for c in self._conns:
            self.credo.subsystems['Exposure'].disconnect(c)
        self._conns = []
        GLib.source_remove(self._remtime_timeout)
        self._remtime_timeout = None
        self.exposure_progress.hide()
        self.nimages_progress.hide()
        if not state:
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, 'User break!')
            md.run()
            md.destroy()
            del md
    def do_fail(self, message):
        md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Error during exposure')
        md.format_secondary_text(message)
        md.run()
        md.destroy()
        del md
    def kill(self):
        self.credo.subsystems['Exposure'].kill()

