import gtk
import gobject
import sastool
import os
import re
from sasgui.PyGTKCallback import PyGTKCallback

class MaskChooserDialog(gtk.FileChooserDialog):
    def __init__(self, title='Select mask file...', parent=None, action=gtk.FILE_CHOOSER_ACTION_OPEN, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.FileChooserDialog.__init__(self, title, parent, action, buttons)
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

RESPONSE_REFRESH = 1
RESPONSE_OPEN = 2

class FileEntryWithButton(gtk.HBox):
    _filechooserdialogs = None
    def __init__(self, dialogtitle='Open file...', dialogaction=gtk.FILE_CHOOSER_ACTION_OPEN, currentfolder=None, *args):
        gtk.HBox.__init__(self, *args)
        self.entry = gtk.Entry()
        self.pack_start(self.entry, True)
        self.button = gtk.Button(stock=gtk.STOCK_OPEN)
        self.pack_start(self.button, False)
        self.dialogtitle = dialogtitle
        self.currentfolder = currentfolder
        self.button.connect('clicked', self.on_button, self.entry, dialogaction)
    def get_path(self):
        return self.entry.get_text()
    def on_button(self, button, entry, action):
        if self._filechooserdialogs is None:
            self._filechooserdialogs = {}
        if entry not in self._filechooserdialogs:
            self._filechooserdialogs[entry] = MaskChooserDialog(self.dialogtitle, self.get_toplevel(), action, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
            if self.currentfolder is not None:
                if callable(self.currentfolder):
                    self._filechooserdialogs[entry].set_current_folder(self.currentfolder())
                else:
                    self._filechooserdialogs[entry].set_current_folder(self.currentfolder)
        if entry.get_text():
            self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == gtk.RESPONSE_OK:
            entry.set_text(self._filechooserdialogs[entry].get_filename())
        self._filechooserdialogs[entry].hide()
        return True

@PyGTKCallback    
class ExposureOpenDialog(gtk.Dialog):
    def __init__(self, credo, title='Open exposure...', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE, gtk.STOCK_REFRESH, RESPONSE_REFRESH, gtk.STOCK_OPEN, RESPONSE_OPEN)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_CLOSE)
        self.credo = credo
        vb = self.get_content_area()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        row = 0
        
        l = gtk.Label(u'File prefix:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fileprefix_entry = gtk.combo_box_entry_new_text()
        self.fileprefix_entry.append_text('crd_%05d')
        self.fileprefix_entry.append_text('beamtest_%05d')
        self.fileprefix_entry.append_text('transmission_%05d')
        self.fileprefix_entry.append_text('timedscan_%05d')
        self.fileprefix_entry.set_active(0)
        self.fileprefix_entry.connect('changed', self.reload)
        tab.attach(self.fileprefix_entry, 1, 2, row, row + 1)
        row += 1
        
        self.fsn_start_cb = gtk.CheckButton('Starting FSN:'); self.fsn_start_cb.set_alignment(0, 0.5)
        tab.attach(self.fsn_start_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fsn_start_entry = gtk.SpinButton(gtk.Adjustment(1, 0, 1000000000000, 1, 10), digits=0)
        tab.attach(self.fsn_start_entry, 1, 2, row, row + 1)
        self.fsn_start_cb.connect('toggled', self.on_checkbutton_with_entry, self.fsn_start_entry)
        self.on_checkbutton_with_entry(self.fsn_start_cb, self.fsn_start_entry)
        row += 1
        
        self.fsn_end_cb = gtk.CheckButton('Ending FSN:'); self.fsn_start_cb.set_alignment(0, 0.5)
        tab.attach(self.fsn_end_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.fsn_end_entry = gtk.SpinButton(gtk.Adjustment(1, 0, 1000000000000, 1, 10), digits=0)
        tab.attach(self.fsn_end_entry, 1, 2, row, row + 1)
        self.fsn_end_cb.connect('toggled', self.on_checkbutton_with_entry, self.fsn_end_entry)
        self.on_checkbutton_with_entry(self.fsn_end_cb, self.fsn_end_entry)
        row += 1
        
        self.mask_cb = gtk.CheckButton('Mask:'); self.fsn_start_cb.set_alignment(0, 0.5)
        tab.attach(self.mask_cb, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        def func():
            return self.credo.maskpath
        self.mask_entry = FileEntryWithButton('Find mask file', currentfolder=func)
        tab.attach(self.mask_entry, 1, 2, row, row + 1)
        self.mask_cb.connect('toggled', self.on_checkbutton_with_entry, self.mask_entry)
        self.on_checkbutton_with_entry(self.mask_cb, self.mask_entry)
        row += 1
        
        self.liststore = gtk.ListStore(gobject.TYPE_PYOBJECT,  # the SASHeader instance 
                                     gobject.TYPE_INT,  # FSN
                                     gobject.TYPE_STRING,  # Title
                                     gobject.TYPE_STRING,  # Owner
                                     gobject.TYPE_DOUBLE,  # Dist
                                     gobject.TYPE_DOUBLE,  # ExpTime
                                     )
        self.treeview = gtk.TreeView(self.liststore)
        self.treeview.set_rules_hint(True)
        self.treeview.set_headers_visible(True)
        for i, coltitle in enumerate(['FSN', 'Title', 'Owner', 'Distance', 'Exp. time']):
            cr = gtk.CellRendererText()
            tvc = gtk.TreeViewColumn(coltitle, cr, text=i + 1)
            tvc.connect('clicked', self.on_tvc_column_clicked, tvc.get_title(), i + 1)
            self.treeview.append_column(tvc)
            tvc.set_sort_indicator(True)
        sw = gtk.ScrolledWindow()
        sw.add(self.treeview)
        self.treeview.set_size_request(-1, 300)
        vb.pack_start(sw, True)
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.treeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.treeview.set_headers_clickable(True)
        def func(*args):
            self.response(RESPONSE_OPEN)
        self.treeview.connect('row-activated', func)
        def _sortfunc(a, b):
            if a < b:
                return -1
            elif a > b:
                return 1
            else:
                return 0
        self.liststore.set_default_sort_func(_sortfunc)
        
        self.connect('response', self.on_response)
        self.reload()
        vb.show_all()
    def on_tvc_column_clicked(self, col, title, idx):
        id, direct = self.liststore.get_sort_column_id()
        if id == idx:
            self.liststore.set_sort_column_id(idx, 1 - direct)
            col.set_sort_order(1 - direct)
        else:
            self.liststore.set_sort_column_id(idx, gtk.SORT_ASCENDING)
            col.set_sort_order(gtk.SORT_ASCENDING)
    def on_checkbutton_with_entry(self, cb, entry):
        entry.set_sensitive(cb.get_active())
        return True
    def populate_liststore(self):
        for row in self.liststore:
            row[1] = row[0]['FSN']
            row[2] = row[0]['Title']
            row[3] = row[0]['Owner']
            row[4] = row[0]['Dist']
            row[5] = row[0]['MeasTime']
    def reload(self, *args, **kwargs):
        datadirs = self.credo.get_exploaddirs()
        pattern = re.compile(sastool.misc.utils.re_from_Cformatstring_numbers(self.fileprefix_entry.get_active_text())[:-1])
        minfsn = None
        maxfsn = None
        for d in datadirs:
            files = [int(pattern.match(f).group(1)) for f in [f for f in os.listdir(d) if pattern.match(f) is not None]]
            if files:
                if minfsn is None:
                    minfsn = min(files)
                else:
                    minfsn = min(min(files), minfsn)
                if maxfsn is None:
                    maxfsn = max(files)
                else:
                    maxfsn = max(max(files), maxfsn)
        if self.fsn_start_cb.get_active():
            minfsn = self.fsn_start_entry.get_value_as_int()
        if self.fsn_end_cb.get_active():
            maxfsn = self.fsn_end_entry.get_value_as_int()
        if minfsn is None or maxfsn is None:
            return
        headers = sastool.classes.SASHeader(self.fileprefix_entry.get_active_text() + '.param', range(minfsn, maxfsn + 1), dirs=datadirs, error_on_not_found=False)
        self.liststore.clear()
        for h in headers:
            self.liststore.append((h, 0, '', '', 0, 0))
        self.populate_liststore()
    def on_load_exposure(self, tview, path, column):
        header = self.liststore[path][0]
        datadirs = self.credo.get_exploaddirs()
        if self.mask_cb.get_active():
            ex = sastool.classes.SASExposure((self.fileprefix_entry.get_active_text() % header['FSN']) + '.cbf', dirs=datadirs, maskfile=self.mask_entry.get_path())
        else:
            ex = sastool.classes.SASExposure((self.fileprefix_entry.get_active_text() % header['FSN']) + '.cbf', dirs=datadirs)
        self.emit('exposure-loaded', ex)
    def on_response(self, dialog, respid):
        if respid == RESPONSE_REFRESH:
            self.reload()
        elif respid == gtk.RESPONSE_CLOSE:
            self.hide()
        elif respid == RESPONSE_OPEN:
            sel = self.treeview.get_selection().get_selected()
            if sel[1] is not None:
                return self.on_load_exposure(None, sel[1], 0)
            # self.on_load_exposure()

@PyGTKCallback
class ExposureLoader(gtk.HBox):
    def __init__(self, credo, *args, **kwargs):
        gtk.HBox.__init__(self, *args, **kwargs)
        self.label = gtk.Label()
        self.pack_start(self.label, True)
        self.label.set_alignment(0, 0.5)
        self.button = gtk.Button(stock=gtk.STOCK_OPEN)
        self.pack_start(self.button, False)
        self.button.connect('clicked', self.on_openbutton)
        self.credo = credo
        self._eod = None
        self._exposure = None
    def on_openbutton(self, button):
        if self._eod is None:
            self._eod = ExposureOpenDialog(self.credo, 'Open exposure', self.get_toplevel(), gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
            self._eod.connect('exposure-loaded', self.on_load_exposure)
        while self._eod.run() not in (gtk.RESPONSE_CLOSE , RESPONSE_OPEN, gtk.RESPONSE_DELETE_EVENT):
            pass
        self._eod.hide()
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
