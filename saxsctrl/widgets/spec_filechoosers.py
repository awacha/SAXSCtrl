from gi.repository import Gtk
from gi.repository import GObject
import sastool
import os
import re
from ..utils import fileentry

class MaskEntryWithButton(fileentry.FileEntryWithButton):
    def __init__(self, credo, dialogtitle='Open mask...'):
        fileentry.FileEntryWithButton.__init__(self, dialogtitle, Gtk.FileChooserAction.OPEN, [('All mask files', ('*.mat', '*.npy', '*.npz', '*.sma', '*.edf')), ('MAT files', '*.mat'), ('Numpy files', ('*.npy', '*.npz')),
                                                                        ('BerSANS mask files', '*.sma'), ('EDF files', '*.edf')], default_folder=credo.subsystems['Files'].maskpath)
    def get_mask(self):
        return sastool.classes.SASMask(self.get_filename())
        


class MaskChooserDialog(Gtk.FileChooserDialog):
    def __init__(self, title='Select mask file...', parent=None, action=Gtk.FileChooserAction.OPEN, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.FileChooserDialog.__init__(self, title, parent, action, buttons)
        ff = Gtk.FileFilter(); ff.set_name('MAT files'); ff.add_pattern('*.mat')
        self.add_filter(ff)
        ff = Gtk.FileFilter(); ff.set_name('Numpy files'); ff.add_pattern('*.npy'); ff.add_pattern('*.npz')
        self.add_filter(ff)
        ff = Gtk.FileFilter(); ff.set_name('BerSANS mask files'); ff.add_pattern('*.sma');
        self.add_filter(ff)
        ff = Gtk.FileFilter(); ff.set_name('EDF files'); ff.add_pattern('*.edf')
        self.add_filter(ff)
        ff = Gtk.FileFilter(); ff.set_name('All files'); ff.add_pattern('*')
        self.add_filter(ff)
        ff = Gtk.FileFilter(); ff.set_name('All mask files'); ff.add_pattern('*.mat'); ff.add_pattern('*.npy'); ff.add_pattern('*.npz'); ff.add_pattern('*.sma'); ff.add_pattern('*.edf')
        self.add_filter(ff)
        self.set_filter(ff)

RESPONSE_REFRESH = 1
RESPONSE_OPEN = 2

class FileEntryWithButton(Gtk.HBox):
    _filechooserdialog = None
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ())}
    _changed = False
    def __init__(self, dialogtitle='Open file...', dialogaction=Gtk.FileChooserAction.OPEN, currentfolder=None, dialogclass=Gtk.FileChooserDialog, * args):
        Gtk.HBox.__init__(self, *args)
        self.entry = Gtk.Entry()
        self.pack_start(self.entry, True, True, 0)
        self.button = Gtk.Button(stock=Gtk.STOCK_OPEN)
        self.pack_start(self.button, False, True, 0)
        self.dialogtitle = dialogtitle
        self.currentfolder = currentfolder
        self.button.connect('clicked', self.on_button, self.entry, dialogaction)
        self.dialogclass = dialogclass
        self.entry.connect('changed', lambda e:self._entry_changed())
        self.entry.connect('focus-out-event', lambda entry, event: self._entry_finalized())
    def _entry_changed(self):
        self._changed = True
    def _entry_finalized(self):
        if self._changed:
            self.emit('changed')
    def do_changed(self):
        self._changed = False
    def get_path(self):
        return self.entry.get_text()
    get_filename = get_path
    def on_button(self, button, entry, action):
        if self._filechooserdialog is None:
            self._filechooserdialog = self.dialogclass(self.dialogtitle, self.get_toplevel(),
                                                       action, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
            if self.currentfolder is not None:
                if callable(self.currentfolder):
                    self._filechooserdialog.set_current_folder(self.currentfolder())
                else:
                    self._filechooserdialog.set_current_folder(self.currentfolder)
        if entry.get_text():
            self._filechooserdialog.set_filename(entry.get_text())
        response = self._filechooserdialog.run()
        if response == Gtk.ResponseType.OK:
            entry.set_text(self._filechooserdialog.get_filename())
            self.emit('changed')
        self._filechooserdialog.hide()
        return True
    def set_filename(self, filename):
        self.entry.set_text(filename)


class ExposureLoader(Gtk.HBox):
    __gsignals__ = {'exposure-loaded':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                  }
    def __init__(self, credo, *args, **kwargs):
        Gtk.HBox.__init__(self, *args, **kwargs)
        self.label = Gtk.Label()
        self.pack_start(self.label, True, True, 0)
        self.label.set_alignment(0, 0.5)
        self.button = Gtk.Button(stock=Gtk.STOCK_OPEN)
        self.pack_start(self.button, False, True, 0)
        self.button.connect('clicked', self.on_openbutton)
        self.credo = credo
        self._eod = None
        self._exposure = None
        self._filename = None
    def _get_eod(self):
        if self._eod is None:
            self._eod = ExposureOpenDialog(self.credo, 'Open exposure', self.get_toplevel(), Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
            self._eod.connect('exposure-loaded', self.on_load_exposure)
        return self._eod
        
    def on_openbutton(self, button):
        eod = self._get_eod()
        while eod.run() not in (Gtk.ResponseType.CLOSE , RESPONSE_OPEN, Gtk.ResponseType.DELETE_EVENT):
            pass
        eod.hide()
    def on_load_exposure(self, eod, ex):
        self.label.set_text(ex['FileName'] + ': ' + ex['Title'] + '(' + str(ex['MeasTime']) + ' s)')
        self._exposure = ex
        self.emit('exposure-loaded', ex)
    def get_exposure(self):
        return self._exposure
    def forget_exposure(self):
        del self._exposure
        self.label.set_text('')
        self.exposure = None
    def get_filename(self):
        return self._exposure['FileName']
    def set_filename(self, filename):
        datadirs = self.credo.get_exploaddirs()
        self.on_load_exposure(None, sastool.classes.SASExposure(filename, dirs=datadirs))
        return
            

