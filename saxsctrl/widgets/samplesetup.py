#
# coding: utf-8
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango
import datetime
from ..hardware import sample
from gi.repository import GObject
# import cPickle as pickle
from .widgets import ToolDialog, ErrorValueEntry
import sastool


class SampleSetup(Gtk.Dialog):

    def __init__(self, title='Edit sample', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT,
                 buttons=('OK', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        vb = self.get_content_area()
        grid = Gtk.Grid()
        vb.pack_start(grid, False, True, 0)
        self.set_resizable(False)
        row = 0

        l = Gtk.Label(label='Sample name:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.samplename_entry = Gtk.Entry()
        self.samplename_entry.set_placeholder_text('-- please fill --')
        grid.attach(self.samplename_entry, 1, row, 1, 1)
        self.samplename_entry.connect('changed', self.on_change_entry, 'title')
        row += 1

        l = Gtk.Label(label='Description:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.description_entry = Gtk.Entry()
        self.description_entry.set_placeholder_text('-- please fill --')
        grid.attach(self.description_entry, 1, row, 1, 1)
        self.description_entry.connect(
            'changed', self.on_change_entry, 'description')
        row += 1

        l = Gtk.Label(label='Thickness (cm):')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.thickness_entry = ErrorValueEntry(
            adjustment_nominal=Gtk.Adjustment(
                value=0.1, lower=0, upper=100, step_increment=0.1, page_increment=1),
            adjustment_error=Gtk.Adjustment(
                value=0, lower=0, upper=100, step_increment=0.1, page_increment=1),
            digits=4)
        grid.attach(self.thickness_entry, 1, row, 1, 1)
        self.thickness_entry.connect(
            'value-changed', self.on_change_entry, 'thickness')
        row += 1

        l = Gtk.Label(label='X position:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.positionx_entry = ErrorValueEntry(adjustment_nominal=Gtk.Adjustment(value=0, lower=-100, upper=100, step_increment=0.1, page_increment=1),
                                               adjustment_error=Gtk.Adjustment(
                                                   value=0, lower=0, upper=100000, step_increment=0.1, page_increment=1),
                                               digits=3)
        grid.attach(self.positionx_entry, 1, row, 1, 1)
        self.positionx_entry.connect(
            'value-changed', self.on_change_entry, 'positionx')
        row += 1

        l = Gtk.Label(label='Y position:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.positiony_entry = ErrorValueEntry(adjustment_nominal=Gtk.Adjustment(value=0, lower=-100, upper=100, step_increment=0.1, page_increment=1),
                                               adjustment_error=Gtk.Adjustment(
                                                   value=0, lower=0, upper=100000, step_increment=0.1, page_increment=1),
                                               digits=3)
        grid.attach(self.positiony_entry, 1, row, 1, 1)
        self.positiony_entry.connect(
            'value-changed', self.on_change_entry, 'positiony')
        row += 1

        l = Gtk.Label(label='Distance decrease:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.distminus_entry = ErrorValueEntry(adjustment_nominal=Gtk.Adjustment(value=0, lower=-1000, upper=1000, step_increment=0.1, page_increment=1),
                                               adjustment_error=Gtk.Adjustment(
                                                   value=0, lower=0, upper=100000, step_increment=0.1, page_increment=1),
                                               digits=4)
        grid.attach(self.distminus_entry, 1, row, 1, 1)
        self.distminus_entry.connect(
            'value-changed', self.on_change_entry, 'distminus')
        row += 1

        l = Gtk.Label(label='Transmission:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.transmission_entry = ErrorValueEntry(adjustment_nominal=Gtk.Adjustment(value=0.5, lower=0, upper=1, step_increment=0.1, page_increment=1),
                                                  adjustment_error=Gtk.Adjustment(
                                                      value=0, lower=0, upper=100, step_increment=0.1, page_increment=1),
                                                  digits=4)
        grid.attach(self.transmission_entry, 1, row, 1, 1)
        self.transmission_entry.connect(
            'value-changed', self.on_change_entry, 'transmission')
        row += 1

        l = Gtk.Label(label='Category:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.category_combo = Gtk.ComboBoxText()
        for cat in sample.VALID_CATEGORIES:
            self.category_combo.append_text(cat)
        self.category_combo.set_active(0)
        grid.attach(self.category_combo, 1, row, 1, 1)
        self.category_combo.connect(
            'changed', self.on_change_entry, 'category')
        row += 1

        l = Gtk.Label(label='Situation:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.situation_combo = Gtk.ComboBoxText()
        for sit in sample.VALID_SITUATIONS:
            self.situation_combo.append_text(sit)
        self.situation_combo.set_active(0)
        grid.attach(self.situation_combo, 1, row, 1, 1)
        self.situation_combo.connect(
            'changed', self.on_change_entry, 'situation')
        row += 1

        l = Gtk.Label(label='Prepared by:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.preparedby_entry = Gtk.Entry()
        self.preparedby_entry.set_placeholder_text('-- please fill --')
        grid.attach(self.preparedby_entry, 1, row, 1, 1)
        self.preparedby_entry.connect(
            'changed', self.on_change_entry, 'preparedby')
        row += 1

        l = Gtk.Label(label='Preparation time:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self.preparetime_entry = Gtk.Calendar()
        self.preparetime_entry.set_display_options(
            Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES | Gtk.CalendarDisplayOptions.SHOW_HEADING | Gtk.CalendarDisplayOptions.SHOW_WEEK_NUMBERS)
        n = datetime.date.today()
        self.preparetime_entry.select_month(n.month - 1, n.year)
        self.preparetime_entry.select_day(n.day)
        self.preparetime_entry.connect(
            'day-selected', self.on_change_entry, 'preparetime')
        self.preparetime_entry.connect(
            'day-selected-double-click', self.on_change_entry, 'preparetime')
        self.preparetime_entry.connect(
            'month-changed', self.on_change_entry, 'preparetime')
        grid.attach(self.preparetime_entry, 1, row, 1, 1)
        row += 1

#        self.connect('delete-event', self.hide_on_delete)
        vb.show_all()
        self._changelist = []

    def run(self, *args, **kwargs):
        self._changelist = []
        return Gtk.Dialog.run(self, *args, **kwargs)

    def on_change_entry(self, entry, attr):
        if entry not in [x[0] for x in self._changelist]:
            self._changelist.append((entry, attr))

    def get_sample(self):
        title = self.samplename_entry.get_text()
        thickness = self.thickness_entry.get_value()
        positionx = self.positionx_entry.get_value()
        positiony = self.positiony_entry.get_value()
        transmission = self.transmission_entry.get_value()
        preparedby = self.preparedby_entry.get_text()
        preparetime = self.preparetime_entry.get_date()
        distminus = self.distminus_entry.get_value()
        description = self.description_entry.get_text()
        category = self.category_combo.get_active_text()
        situation = self.situation_combo.get_active_text()
        return sample.SAXSSample(title, positionx, positiony, thickness, transmission, preparedby,
                                 datetime.datetime(
                                     preparetime[0], preparetime[1] + 1, preparetime[2]), distminus,
                                 description, category, situation)

    def set_sample(self, sam):
        self.samplename_entry.set_text(sam.title)
        self.thickness_entry.set_value(sam.thickness)
        self.positionx_entry.set_value(sam.positionx)
        self.positiony_entry.set_value(sam.positiony)
        self.transmission_entry.set_value(sam.transmission)
        self.preparedby_entry.set_text(sam.preparedby)
        self.preparetime_entry.select_month(
            sam.preparetime.month - 1, sam.preparetime.year)
        self.preparetime_entry.select_day(sam.preparetime.day)
        self.distminus_entry.set_value(sam.distminus)
        self.description_entry.set_text(sam.description)
        try:
            self.category_combo.set_active(
                sample.VALID_CATEGORIES.index(sam.category))
        except ValueError:
            self.category_combo.set_active(0)
        try:
            self.situation_combo.set_active(
                sample.VALID_SITUATIONS.index(sam.situation))
        except ValueError:
            self.situation_combo.set_active(0)
        return True

    def update_sample(self, sam):
        for widget, attr in self._changelist:
            if isinstance(widget, Gtk.SpinButton):
                sam.__setattr__(attr, widget.get_value())
            elif isinstance(widget, Gtk.Entry):
                sam.__setattr__(attr, widget.get_text())
            elif isinstance(widget, Gtk.Calendar):
                sam.__setattr__(attr,
                                datetime.datetime(widget.get_date()[0], widget.get_date()[1] + 1, widget.get_date()[2]))
            elif isinstance(widget, ErrorValueEntry):
                sam.__setattr__(attr, widget.get_value())
            elif isinstance(widget, Gtk.ComboBoxText):
                sam.__setattr__(attr, widget.get_active_text())
            else:
                raise NotImplementedError('Unexpected widget: ' + repr(widget))
        self._changelist = []
        return sam


class SampleListDialog(ToolDialog):
    __gsignals__ = {'response': 'override'}

    def __init__(self, credo, title='Sample configuration'):
        ToolDialog.__init__(self, credo, title)
        vb = self.get_content_area()

        tbar = Gtk.Toolbar()
        vb.pack_start(tbar, False, True, 0)
        tbar.set_style(Gtk.ToolbarStyle.BOTH)
        tb = Gtk.ToolButton(label='New')
        tb.set_icon_name('list-add')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self.add_sample())
        tb = Gtk.ToolButton(label='Save')
        tb.set_icon_name('document-save')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self._tool_save())
        tb = Gtk.ToolButton(label='Open')
        tb.set_icon_name('document-open')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self._tool_load())
        tb = Gtk.ToolButton(label='Edit')
        tb.set_icon_name('document-properties')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self._tool_edit())
        tb = Gtk.ToolButton(label='Remove')
        tb.set_icon_name('list-remove')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self._tool_remove())
        tb = Gtk.ToolButton(label='Clear')
        tb.set_icon_name('edit-clear')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self._tool_clear())
        tb = Gtk.ToolButton(label='Copy')
        tb.set_icon_name('edit-copy')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self._tool_duplicate())
        tb = Gtk.ToolButton(label='Refresh')
        tb.set_icon_name('view-refresh')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self._tool_refresh())
        tb = Gtk.ToolButton(label='Export to HTML')
        tb.set_icon_name('text-html')
        tbar.add(tb)
        tb.connect('clicked', lambda tb: self._tool_export_to_html())
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(400, 300)
        vb.pack_start(sw, True, True, 0)
        self.sampleliststore = Gtk.ListStore(GObject.TYPE_STRING,  # title
                                             # description
                                             GObject.TYPE_STRING,
                                             # prepared by
                                             GObject.TYPE_STRING,
                                             # preparation time
                                             GObject.TYPE_STRING,
                                             GObject.TYPE_STRING,  # thickness
                                             GObject.TYPE_STRING,  # positionX
                                             GObject.TYPE_STRING,  # positionY
                                             GObject.TYPE_STRING,  # distminus
                                             GObject.TYPE_STRING,
                                             # transmission (string, because
                                             # +/- error can be given)
                                             # the Sample object itself
                                             GObject.TYPE_STRING,  # category
                                             GObject.TYPE_STRING,  # situation
                                             GObject.TYPE_PYOBJECT,
                                             )
        self.sampletreeview = Gtk.TreeView(model=self.sampleliststore)
        sw.add(self.sampletreeview)
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn('Title', cr, text=0))
        cr = Gtk.CellRendererText(
            wrap_width=100, wrap_mode=Pango.WrapMode.WORD)
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn('Description', cr, text=1))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn('Prepared by', cr, text=2))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn('Date', cr, text=3))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn('Thickness (cm)', cr, text=4))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn(u'X Position', cr, text=5))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn(u'Y Position', cr, text=6))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn(u'Distance decrease', cr, text=7))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn(u'Transmission', cr, text=8))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn(u'Category', cr, text=9))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(
            Gtk.TreeViewColumn(u'Situation', cr, text=10))
        self.sampletreeview.get_selection().set_mode(
            Gtk.SelectionMode.MULTIPLE)
        self.sampletreeview.set_headers_visible(True)
        self.sampletreeview.set_rules_hint(True)
        self.sampletreeview.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
        self.sampletreeview.connect(
            'row-activated', lambda tv, path, column: self._tool_edit())

        self.from_credo()

    def _changed(self):
        self._changes_present = True

    def add_sample(self, sam=None, index=None):
        if sam is None:
            sam = sample.SAXSSample(
                '-- no title --', preparedby=self.credo.username)
        if index is not None:
            self.sampleliststore.insert_after(
                index, ('', '', '', '', '', '', '', '', '', '', '', sam))
        else:
            self.sampleliststore.append(
                ('', '', '', '', '', '', '', '', '', '', '', sam))
        self.update_liststore()
        self._changed()

    def update_liststore(self):
        for row in self.sampleliststore:
            for i, attr in enumerate(['title', 'description', 'preparedby', 'preparetime', 'thickness', 'positionx', 'positiony', 'distminus', 'transmission', 'category', 'situation']):
                value = getattr(row[-1], attr)
                if isinstance(value, basestring):
                    row[i] = value
                elif isinstance(value, datetime.datetime):
                    row[i] = str(value.date())
                elif isinstance(value, float):
                    row[i] = unicode(value)
                elif isinstance(value, sastool.ErrorValue):
                    row[i] = value.tostring(extra_digits=1)

    def _tool_remove(self):
        model, rows = self.sampletreeview.get_selection().get_selected_rows()
        iters = [model.get_iter(row) for row in rows]
        for it in iters:
            model.remove(it)
        if iters:
            self._changed()

    def _tool_duplicate(self):
        model, rows = self.sampletreeview.get_selection().get_selected_rows()
        if not rows:
            return

        if rows[0] is not None:
            sam = model[rows[0]][-1]
            sam = sample.SAXSSample(sam)
            sam.title = sam.title + '_copy'
            self.add_sample(sam, model.get_iter(rows[0]))

    def _tool_load(self):
        self.credo.subsystems['Samples'].load()
        self.from_credo()

    def _tool_save(self):
        self.to_credo()
        self.credo.subsystems['Samples'].save()
        md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                               Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                               'Samples saved to file: ' + self.credo.subsystems['Samples'].configfile)
        md.run()
        md.destroy()
        del md
        if hasattr(self, '_changes_present'):
            del self._changes_present

    def _tool_clear(self):
        self.sampleliststore.clear()
        self._changed()

    def _tool_refresh(self):
        self.from_credo()

    def _tool_edit(self):
        model, rows = self.sampletreeview.get_selection().get_selected_rows()
        if not rows:
            return
        sam = model[rows[0]][-1]
        ssd = SampleSetup(
            'Edit sample', self, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
        ssd.set_sample(sam)
        resp = ssd.run()
        if resp == Gtk.ResponseType.OK:
            model[rows[0]][-1] = ssd.update_sample(sam)
            self.update_liststore()
        ssd.destroy()
        self._changed()

    def _tool_export_to_html(self):
        htmlout = '<table border="1" cellpadding="1" cellspacing="1" style="width:100%">\n'
        htmlout = htmlout + '  <tr>\n'
        htmlout = htmlout + '    <th>Sample name</th>\n'
        htmlout = htmlout + '    <th>Description</th>\n'
        htmlout = htmlout + '    <th>Category</th>\n'
        htmlout = htmlout + '    <th>Situation</th>\n'
        htmlout = htmlout + '    <th>Prepared by</th>\n'
        htmlout = htmlout + '    <th>Preparation date</th>\n'
        htmlout = htmlout + '    <th>Thickness (cm)</th>\n'
        htmlout = htmlout + '    <th>X position (mm)</th>\n'
        htmlout = htmlout + '    <th>Y position (mm)</th>\n'
        htmlout = htmlout + '    <th>Distance decrease (mm)</th>\n'
        htmlout = htmlout + '    <th>Transmission</th>\n'
        htmlout = htmlout + '  </tr>\n'
        model, rows = self.sampletreeview.get_selection().get_selected_rows()
        for row in rows:
            sam = model[row][-1]
            htmlout = htmlout + '  <tr>\n'
            htmlout = htmlout + """    <td>%s</td>\n    <td>%s</td>\n    <td>%s</td>\n
    <td>%s</td>\n    <td>%s</td>\n    <td>%s</td>\n
    <td>%s</td>\n    <td>%s</td>\n    <td>%s</td>\n
    <td>%s</td>\n    <td>%s</td>\n""" % (sam.title, sam.description, sam.category, sam.situation,
                                         sam.preparedby, sam.preparetime.date(),
                                         sastool.ErrorValue(sam.thickness).tostring(
                                             extra_digits=3),
                                         sastool.ErrorValue(sam.positionx).tostring(
                                             extra_digits=2),
                                         sastool.ErrorValue(sam.positiony).tostring(
                                             extra_digits=2),
                                         sastool.ErrorValue(sam.distminus).tostring(
                                             extra_digits=3),
                                         sastool.ErrorValue(sam.transmission).tostring(extra_digits=3))
            htmlout = htmlout + '  </tr>\n'
        htmlout = htmlout + '</table>\n'
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(htmlout, -1)

    def do_response(self, respid):
        if respid in (Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            if hasattr(self, '_changes_present'):
                md = Gtk.MessageDialog(transient_for=self.get_toplevel(),
                                       destroy_with_parent=True, modal=True,
                                       type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.YES_NO,
                                       message_format='You have unsaved modifications. Do you want to apply them?')
                if md.run() == Gtk.ResponseType.YES:
                    self._tool_save()  # this also deletes _changes_present
                else:
                    del self._changes_present
                md.destroy()
                del md
            self.hide()

    def to_credo(self):
        self.credo.subsystems['Samples'].clear()
        for row in self.sampleliststore:
            self.credo.subsystems['Samples'].add(row[-1])

    def from_credo(self):
        self.sampleliststore.clear()
        for sam in self.credo.subsystems['Samples']:
            self.add_sample(sam)
        if hasattr(self, '_changes_present'):
            del self._changes_present


class SampleSelector(Gtk.ComboBoxText):
    __gsignals__ = {'sample-changed': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    }
    autorefresh = GObject.property(type=bool, default=True)

    def __init__(self, credo, autorefresh=True, shortnames=False):
        Gtk.ComboBox.__init__(self)
        self.credo = credo
        self.credo.subsystems['Samples'].connect(
            'changed', lambda sss: self.reload_samples())
        self.autorefresh = autorefresh
        self.shortnames = shortnames
        self.credo.subsystems['Samples'].connect('selected',
                                                 lambda sss, sam: (self.autorefresh) and self.set_sample(sam))
        self.samplelist = Gtk.ListStore(
            GObject.TYPE_STRING, GObject.TYPE_PYOBJECT)
        self.set_model(self.samplelist)
        self.set_entry_text_column(0)
        self.reload_samples()
        if self.autorefresh:
            self.set_sample(self.credo.subsystems['Samples'].get())
        self.show_all()

    def reload_samples(self):
        if self.get_active() >= 0 and self.get_active() < len(self.samplelist):
            sam_before = self.samplelist[self.get_active()][-1]['Title']
        else:
            sam_before = None
        self.samplelist.clear()
        self.samplelist.append(('-- UNKNOWN --', None))
        for i, sam in enumerate(self.credo.subsystems['Samples']):
            if sam_before is not None:
                if sam.title == sam_before:
                    self.set_active(i + 1)
            if self.shortnames:
                self.samplelist.append((sam.title, sam))
            else:
                self.samplelist.append((str(sam), sam))
        if self.samplelist[self.get_active()][-1]['Title'] != sam_before:
            self.emit('sample-changed', self.samplelist[self.get_active()][-1])

    def set_sample(self, sam):
        if isinstance(sam, basestring) and sam == '':
            sam = None
        if isinstance(sam, sample.SAXSSample) or (sam is None):
            for i, row in enumerate(self.samplelist):
                if row[-1] == sam:
                    self.set_active(i)
                    self.emit('sample-changed', sam)
                    return
        elif isinstance(sam, basestring):
            for i, row in enumerate(self.samplelist):
                if ((str(row[-1]) == sam) or (row[0] == sam) or
                        (isinstance(row[-1], sample.SAXSSample) and row[-1].title == sam)):
                    self.set_active(i)
                    self.emit('sample-changed', row[-1])
                    return
        raise ValueError('Sample not in list: ' + str(sam))

    def get_sample(self):
        return self.samplelist[self.get_active()][-1]
