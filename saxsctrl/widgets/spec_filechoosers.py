import gtk

class MaskChooserDialog(gtk.FileChooserDialog):
    def __init__(self, title='Select mask file...', parent=None, action=gtk.FILE_CHOOSER_ACTION_OPEN, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.FileChooserDialog.__init__(title, parent, action, buttons)
        ff = gtk.FileFilter(); ff.set_name('MAT files'); ff.add_pattern('*.mat')
        self.add_filter(ff)
        ff = gtk.FileFilter(); ff.set_name('Numpy files'); ff.add_pattern('*.npy'); ff.add_pattern('*.npz')
        self.add_filter(ff)
        ff = gtk.FileFilter(); ff.set_name('BerSANS mask files'); ff.add_pattern('*.sma');
        self.add_filter(ff)
        ff = gtk.FileFilter(); ff.set_name('EDF files'); ff.add_pattern('*.edf')
        self.add_filter(ff)
        ff = gtk.FileFilter(); ff.set_name('All files'); ff.add_pattern('*')
        self.add_filter(ff)
        ff = gtk.FileFilter(); ff.set_name('All mask files'); ff.add_pattern('*.mat'); ff.add_pattern('*.npy'); ff.add_pattern('*.npz'); ff.add_pattern('*.sma'); ff.add_pattern('*.edf')
        self.add_filter(ff)
        self.set_filter(ff)

