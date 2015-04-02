from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import GObject
from .spec_filechoosers import MaskEntryWithButton
import sastool
DEFAULT_PREFIX = 'crd'



class ExposureBrowserDialog(Gtk.Dialog):
    __gsignals__ = {'selected':(GObject.SignalFlags.RUN_FIRST, None, (int,)),
                   }

    def __init__(self, credo, fileprefix, ndigits, title='Open exposure...', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons=('Cancel', Gtk.ResponseType.CANCEL, 'Refresh', Gtk.ResponseType.APPLY, 'Open', Gtk.ResponseType.OK))
        self.credo = credo
        self.fileprefix = fileprefix
        self.ndigits = ndigits

        vb = self.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        row = 0

        self.fsn_start_cb = Gtk.CheckButton('Starting FSN:'); self.fsn_start_cb.set_halign(Gtk.Align.START); self.fsn_start_cb.set_valign(Gtk.Align.CENTER)
        tab.attach(self.fsn_start_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.fsn_start_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 0, 9999999999, 1, 10), digits=0)
        tab.attach(self.fsn_start_entry, 1, 2, row, row + 1)
        self.fsn_start_cb.connect('toggled', self._checkbutton_with_entry, self.fsn_start_entry)
        self._checkbutton_with_entry(self.fsn_start_cb, self.fsn_start_entry)
        row += 1

        self.fsn_end_cb = Gtk.CheckButton('Ending FSN:'); self.fsn_end_cb.set_halign(Gtk.Align.START); self.fsn_end_cb.set_valign(Gtk.Align.CENTER)
        tab.attach(self.fsn_end_cb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.fsn_end_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 0, 9999999999, 1, 10), digits=0)
        tab.attach(self.fsn_end_entry, 1, 2, row, row + 1)
        self.fsn_end_cb.connect('toggled', self._checkbutton_with_entry, self.fsn_end_entry)
        self._checkbutton_with_entry(self.fsn_end_cb, self.fsn_end_entry)
        row += 1

        self.liststore = Gtk.ListStore(GObject.TYPE_PYOBJECT,  # the SASHeader instance
                                       GObject.TYPE_INT,  # FSN
                                       GObject.TYPE_STRING,  # Title
                                       GObject.TYPE_STRING,  # Owner
                                       GObject.TYPE_DOUBLE,  # Dist
                                       GObject.TYPE_DOUBLE,  # ExpTime
                                       )
        self.treeview = Gtk.TreeView(self.liststore)
        self.treeview.set_rules_hint(True)
        self.treeview.set_headers_visible(True)
        for i, coltitle in enumerate(['FSN', 'Title', 'Owner', 'Distance', 'Exp. time']):
            cr = Gtk.CellRendererText()
            tvc = Gtk.TreeViewColumn(coltitle, cr, text=i + 1)
            tvc.connect('clicked', self._tvc_column_clicked, tvc.get_title(), i + 1)
            self.treeview.append_column(tvc)
            tvc.set_sort_indicator(True)
        sw = Gtk.ScrolledWindow()
        sw.add(self.treeview)
        sw.set_size_request(-1, 300)
        vb.pack_start(sw, True, True, 0)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.treeview.set_headers_clickable(True)
        self.treeview.connect('row-activated', lambda tv, path, column: self.response(Gtk.ResponseType.OK))
        def _sortfunc(a, b):
            if a < b:
                return -1
            elif a > b:
                return 1
            else:
                return 0
        self.liststore.set_default_sort_func(_sortfunc)

        self.connect('response', self._response)
        self.reload()
        vb.show_all()
    def _tvc_column_clicked(self, col, title, idx):
        id_, direct = self.liststore.get_sort_column_id()
        if id_ == idx:
            self.liststore.set_sort_column_id(idx, 1 - direct)
            col.set_sort_order(1 - direct)
        else:
            self.liststore.set_sort_column_id(idx, Gtk.SortType.ASCENDING)
            col.set_sort_order(Gtk.SortType.ASCENDING)
    def _checkbutton_with_entry(self, cb, entry):
        entry.set_sensitive(cb.get_active())
        return True
    def populate_liststore(self):
        for row in self.liststore:
            for i, field in enumerate(['FSN', 'Title', 'Owner', 'Dist', 'MeasTime'], 1):
                try:
                    row[i] = row[0][field]
                except KeyError:
                    row[i] = '<no %s>' % field
    def reload(self, *args, **kwargs):
        datadirs = self.credo.subsystems['Files'].exposureloadpath
        if self.fsn_start_cb.get_active():
            minfsn = self.fsn_start_entry.get_value_as_int()
        else:
            minfsn = self.credo.subsystems['Files'].get_first_fsn(self.credo.subsystems['Files'].get_format_re(self.fileprefix, self.ndigits))
        if self.fsn_end_cb.get_active():
            maxfsn = self.fsn_end_entry.get_value_as_int()
        else:
            maxfsn = self.credo.subsystems['Files'].get_next_fsn(self.credo.subsystems['Files'].get_format_re(self.fileprefix, self.ndigits)) - 1
        if minfsn is None or maxfsn is None:
            return
        headers = sastool.classes.SASHeader(self.credo.subsystems['Files'].get_headerformat(self.fileprefix, self.ndigits), range(minfsn, maxfsn + 1), dirs=datadirs, error_on_not_found=False)
        self.liststore.clear()
        for h in headers:
            self.liststore.append((h, 0, '', '', 0.0, 0.0))
        self.populate_liststore()
        self.treeview.get_selection().select_iter(self.liststore.get_iter_first())
    def _response(self, dialog, respid):
        if respid == Gtk.ResponseType.APPLY:
            self.reload()
        elif respid == (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            self.hide()
        elif respid == Gtk.ResponseType.OK:
            model, it = self.treeview.get_selection().get_selected()
            if it is not None:
                self.emit('selected', model[it][1])
    def get_fsn(self):
        model, it = self.treeview.get_selection().get_selected()
        if it is not None:
            return model[it][1]
        else:
            return None

class ExposureSelector(Gtk.Frame):
    __gsignals__ = {'open':(GObject.SignalFlags.RUN_FIRST, None, (object,))}
    loadtype = GObject.property(type=int, minimum=0, maximum=2, default=0)
    def __init__(self, credo, filebegin='crd', ndigits=5, loadtype='All'):
        Gtk.Frame.__init__(self, label='Select exposure to load')
        self.credo = credo
        self.loadtype = ['ALL', 'RAW', 'EVAL'].index(loadtype.upper())

        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(hb)
        grid = Gtk.Grid()
        hb.pack_start(grid, True, True, 0)
        row = 0

        l = Gtk.Label(label='Filename prefix:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._fileprefix_combo = Gtk.ComboBoxText.new_with_entry()
        for i, pf in enumerate(self.credo.subsystems['Files'].formats()):
            self._fileprefix_combo.append_text(pf)
            if pf == DEFAULT_PREFIX:
                self._fileprefix_combo.set_active(i)
        if self._fileprefix_combo.get_active_text() is None:
            self._fileprefix_combo.set_active(0)
        grid.attach(self._fileprefix_combo, 1, row, 1, 1)
        self._fileprefix_combo.set_hexpand(True)
        row += 1

        l = Gtk.Label(label='Digits in filename:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._digits_sb = Gtk.SpinButton(adjustment=Gtk.Adjustment(5, 1, 10, 1, 10), digits=0)
        self._digits_sb.set_value(self.credo.subsystems['Files'].ndigits)
        grid.attach(self._digits_sb, 1, row, 1, 1)
        self._digits_sb.set_hexpand(True)
        row += 1

        l = Gtk.Label(label='File sequence number:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._fsn_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(1, 0, 9999999999, 1, 10), digits=0)
        self._fsn_entry.set_value(1)
        self._fsn_entry.connect('value-changed', self._on_fsn_changed)
        self._fsn_entry.connect('activate', self._on_fsn_changed)
        hb1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        grid.attach(hb1, 1, row, 1, 1)
        hb1.set_hexpand(True)
        hb1.pack_start(self._fsn_entry, True, True, 0)
        b = Gtk.Button()
        b.set_image(Gtk.Image.new_from_icon_name('go-first', Gtk.IconSize.BUTTON))
        hb1.pack_start(b, False, False, 0)
        b.connect('clicked', lambda b:self._load_first())
        b = Gtk.Button()
        b.set_image(Gtk.Image.new_from_icon_name('go-last', Gtk.IconSize.BUTTON))
        hb1.pack_start(b, False, False, 0)
        b.connect('clicked', lambda b:self._load_last())
        b = Gtk.Button()
        b.set_image(Gtk.Image.new_from_icon_name('edit-find', Gtk.IconSize.BUTTON))
        hb1.pack_start(b, False, False, 0)
        b.connect('clicked', lambda b:self._browse())
        row += 1

        self._mask_override_cb = Gtk.CheckButton('Override mask with:'); self._mask_override_cb.set_halign(Gtk.Align.START)
        grid.attach(self._mask_override_cb, 0, row, 1, 1)
        self._maskentry = MaskEntryWithButton(self.credo)
        grid.attach(self._maskentry, 1, row, 1, 1)
        self._maskentry.set_hexpand(True)
        self._mask_override_cb.connect('toggled', lambda cb: self._maskentry.set_sensitive(cb.get_active()))
        self._mask_override_cb.set_active(False)
        self._maskentry.set_sensitive(False)


        self.show_all()

    def _on_fsn_changed(self, fsnentry):
        GLib.idle_add(lambda :self._load_current() and False)
    def _load_first(self):
        self._fsn_entry.set_value(self.credo.subsystems['Files'].get_first_fsn(self.credo.subsystems['Files'].get_format_re(self._fileprefix_combo.get_active_text(), self._digits_sb.get_value_as_int())) - 1)
        # self._load_current()
    def _load_prev(self):
        self._fsn_entry.set_value(self._fsn_entry.get_value() - 1)
        # self._load_current()
    def _load_current(self):
        try:
            if self.loadtype == 0:  # All
                dirs = self.credo.subsystems['Files'].exposureloadpath
            elif self.loadtype == 1:  # Raw
                dirs = self.credo.subsystems['Files'].rawloadpath
            elif self.loadtype == 2:  # Eval
                dirs = self.credo.subsystems['Files'].reducedloadpath
            else:
                raise NotImplementedError('Unknown loadtype: ' + str(self.loadtype))
            if self._mask_override_cb.get_active():
                ex = sastool.classes.SASExposure(self.credo.subsystems['Files'].get_exposureformat(self._fileprefix_combo.get_active_text(), self._digits_sb.get_value_as_int()),
                                                 self._fsn_entry.get_value_as_int(), dirs=dirs, maskfile=self._maskentry.get_filename())
            else:
                ex = sastool.classes.SASExposure(self.credo.subsystems['Files'].get_exposureformat(self._fileprefix_combo.get_active_text(), self._digits_sb.get_value_as_int()),
                                                 self._fsn_entry.get_value_as_int(), dirs=dirs)
            self.emit('open', ex)
        except IOError as ioe:
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Error reading file: ' + str(ioe))
            md.run()
            md.destroy()
            del md
    def _load_next(self):
        self._fsn_entry.set_value(self._fsn_entry.get_value() + 1)
        # self._load_current()
    def _load_last(self):
        self._fsn_entry.set_value(self.credo.subsystems['Files'].get_next_fsn(self.credo.subsystems['Files'].get_format_re(self._fileprefix_combo.get_active_text(), self._digits_sb.get_value_as_int())) - 1)
        # self._load_current()
    def _browse(self):
        dlg = ExposureBrowserDialog(self.credo, self._fileprefix_combo.get_active_text(), self._digits_sb.get_value_as_int(), parent=self.get_toplevel())
        while True:
            resp = dlg.run()
            if resp == Gtk.ResponseType.OK:
                self._fsn_entry.set_value(dlg.get_fsn())
                # self._load_current()
            if resp != Gtk.ResponseType.APPLY:
                dlg.destroy()
                break
        del dlg
    def get_fileprefix(self):
        return self._fileprefix_combo.get_active_text()
    def get_ndigits(self):
        return self._digits_sb.get_value_as_int()


