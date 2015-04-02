from gi.repository import Gtk
import sastool
from sasgui import fileentry

class MaskEntryWithButton(fileentry.FileEntryWithButton):
    def __init__(self, credo, dialogtitle='Open mask...'):
        fileentry.FileEntryWithButton.__init__(self, dialogtitle, Gtk.FileChooserAction.OPEN, [('All mask files', ('*.mat', '*.npy', '*.npz', '*.sma', '*.edf')), ('MAT files', '*.mat'), ('Numpy files', ('*.npy', '*.npz')),
                                                                        ('BerSANS mask files', '*.sma'), ('EDF files', '*.edf')], default_folder=credo.subsystems['Files'].maskpath)
    def get_mask(self):
        return sastool.classes.SASMask(self.get_filename())

class MaskChooserDialog(Gtk.FileChooserDialog):
    def __init__(self, title='Select mask file...', parent=None,
                 action=Gtk.FileChooserAction.OPEN, buttons=(
                     'OK', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL)):
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


