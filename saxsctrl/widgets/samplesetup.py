#
# coding: utf-8
from gi.repository import Gtk
import datetime
import dateutil.parser
from ..hardware import sample
from gi.repository import GObject
# import cPickle as pickle
import os
import ConfigParser
from .widgets import ToolDialog


class SampleSetup(Gtk.Dialog):
    def __init__(self, title='Edit sample', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        vb = self.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        self.set_resizable(False)
        row = 0
        
        l = Gtk.Label(label='Sample name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.samplename_entry = Gtk.Entry()
        self.samplename_entry.set_text('-- please fill --')
        tab.attach(self.samplename_entry, 1, 2, row, row + 1)
        self.samplename_entry.connect('changed', self.on_change_entry, 'title')
        row += 1

        l = Gtk.Label(label='Thickness (cm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.thickness_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0.1, 0, 100, 0.1, 1), digits=4)
        tab.attach(self.thickness_entry, 1, 2, row, row + 1)
        self.thickness_entry.connect('value-changed', self.on_change_entry, 'thickness')
        row += 1

        l = Gtk.Label(label='X position:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.positionx_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -100, 100, 0.1, 1), digits=3)
        tab.attach(self.positionx_entry, 1, 2, row, row + 1)
        self.positionx_entry.connect('value-changed', self.on_change_entry, 'positionx')
        row += 1

        l = Gtk.Label(label='Y position:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.positiony_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -100, 100, 0.1, 1), digits=3)
        tab.attach(self.positiony_entry, 1, 2, row, row + 1)
        self.positiony_entry.connect('value-changed', self.on_change_entry, 'positiony')
        row += 1
        
        l = Gtk.Label(label='Distance decrease:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.distminus_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1000, 1000, 0.1, 1), digits=4)
        tab.attach(self.distminus_entry, 1, 2, row, row + 1)
        self.distminus_entry.connect('value-changed', self.on_change_entry, 'distminus')
        row += 1
        
        l = Gtk.Label(label=u'Transmission:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.transmission_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0.5, 0, 1, 0.1, 1), digits=4)
        tab.attach(self.transmission_entry, 1, 2, row, row + 1)
        self.transmission_entry.connect('value-changed', self.on_change_entry, 'transmission')
        row += 1

        l = Gtk.Label(label=u'Prepared by:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.preparedby_entry = Gtk.Entry()
        tab.attach(self.preparedby_entry, 1, 2, row, row + 1)
        self.preparedby_entry.connect('changed', self.on_change_entry, 'preparedby')
        row += 1
        
        l = Gtk.Label(label=u'Preparation time:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.preparetime_entry = Gtk.Calendar()
        self.preparetime_entry.set_display_options(Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES | Gtk.CalendarDisplayOptions.SHOW_HEADING | Gtk.CalendarDisplayOptions.SHOW_WEEK_NUMBERS)
        n = datetime.date.today()
        self.preparetime_entry.select_month(n.month - 1, n.year)
        self.preparetime_entry.select_day(n.day)
        self.preparetime_entry.connect('day-selected', self.on_change_entry, 'preparetime')
        self.preparetime_entry.connect('day-selected-double-click', self.on_change_entry, 'preparetime')
        self.preparetime_entry.connect('month-changed', self.on_change_entry, 'preparetime')
        tab.attach(self.preparetime_entry, 1, 2, row, row + 1)
        row += 1
        
        
        self.connect('delete-event', self.hide_on_delete)
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
        return sample.SAXSSample(title, positionx, positiony, thickness, transmission, preparedby, datetime.datetime(preparetime[0], preparetime[1] + 1, preparetime[2]), distminus)
    def set_sample(self, sam):
        self.samplename_entry.set_text(sam.title)
        self.thickness_entry.set_value(sam.thickness)
        self.positionx_entry.set_value(sam.positionx)
        self.positiony_entry.set_value(sam.positiony)
        self.transmission_entry.set_value(sam.transmission)
        self.preparedby_entry.set_text(sam.preparedby)
        self.preparetime_entry.select_month(sam.preparetime.month - 1, sam.preparetime.year)
        self.preparetime_entry.select_day(sam.preparetime.day)
        self.distminus_entry.set_value(sam.distminus)
        return True
    def update_sample(self, sam):
        for widget, attr in self._changelist:
            if isinstance(widget, Gtk.SpinButton):
                sam.__setattr__(attr, widget.get_value())
            elif isinstance(widget, Gtk.Entry):
                sam.__setattr__(attr, widget.get_text())
            elif isinstance(widget, Gtk.Calendar):
                sam.__setattr__(attr, datetime.datetime(widget.get_date()[0], widget.get_date()[1] + 1, widget.get_date()[2]))
        self._changelist = []
        return sam
        
class SampleListDialog(ToolDialog):
    __gsignals__ = {'response':'override'}
    def __init__(self, credo, title='Sample configuration'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY))
        self.set_default_response(Gtk.ResponseType.CLOSE)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        vb = self.get_content_area()
        
        tbar = Gtk.Toolbar()
        vb.pack_start(tbar, False, True, 0)
        
        tb = Gtk.ToolButton(stock_id=Gtk.STOCK_NEW)
        tbar.add(tb)
        tb.connect('clicked', lambda tb:self.add_sample())
        tb = Gtk.ToolButton(stock_id=Gtk.STOCK_SAVE)
        tbar.add(tb)
        tb.connect('clicked', lambda tb:self._tool_save())
        tb = Gtk.ToolButton(stock_id=Gtk.STOCK_OPEN)
        tbar.add(tb)
        tb.connect('clicked', lambda tb:self._tool_load())
        tb = Gtk.ToolButton(stock_id=Gtk.STOCK_EDIT)
        tbar.add(tb)
        tb.connect('clicked', lambda tb:self._tool_edit())
        tb = Gtk.ToolButton(stock_id=Gtk.STOCK_REMOVE)
        tbar.add(tb)
        tb.connect('clicked', lambda tb:self._tool_remove())
        tb = Gtk.ToolButton(stock_id=Gtk.STOCK_CLEAR)
        tbar.add(tb)
        tb.connect('clicked', lambda tb:self._tool_clear())
        tb = Gtk.ToolButton(stock_id=Gtk.STOCK_COPY)
        tbar.add(tb)
        tb.connect('clicked', lambda tb:self._tool_duplicate())
        tb = Gtk.ToolButton(stock_id=Gtk.STOCK_REFRESH)
        tbar.add(tb)
        tb.connect('clicked', lambda tb:self._tool_refresh())
        
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(400, 300)
        vb.pack_start(sw, False, True, 0)
        self.sampleliststore = Gtk.ListStore(GObject.TYPE_STRING,  # title 
                                             GObject.TYPE_STRING,  # prepared by
                                             GObject.TYPE_STRING,  # preparation time
                                             GObject.TYPE_DOUBLE,  # thickness
                                             GObject.TYPE_DOUBLE,  # positionX
                                             GObject.TYPE_DOUBLE,  # positionY
                                             GObject.TYPE_DOUBLE,  # distminus
                                             GObject.TYPE_STRING,  # transmission (string, because +/- error can be given)
                                             GObject.TYPE_PYOBJECT,  # the Sample object itself
                                             )
        self.sampletreeview = Gtk.TreeView(self.sampleliststore)
        sw.add(self.sampletreeview)
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn('Sample title', cr, text=0))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn('Prepared by', cr, text=1))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn('Date of preparation', cr, text=2))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn('Thickness (cm)', cr, text=3))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn(u'X Position', cr, text=4))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn(u'Y Position', cr, text=5))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn(u'Dist.decr.', cr, text=6))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn(u'Transmission', cr, text=7))
        self.sampletreeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.sampletreeview.set_headers_visible(True)
        self.sampletreeview.set_rules_hint(True)
        
        self.from_credo()
    def _changed(self):
        self.set_response_sensitive(Gtk.ResponseType.APPLY, True)
    def add_sample(self, sam=None, index=None):
        if sam is None:
            sam = sample.SAXSSample('-- no title --', preparedby=self.credo.username)
        if index is not None:
            self.sampleliststore.insert_after(index, ('', '', '', 0.0, 0.0, 0.0, 0.0, '', sam))
        else:
            self.sampleliststore.append(('', '', '', 0.0, 0.0, 0.0, 0.0, '', sam))
        self.update_liststore()
        self._changed()
    def update_liststore(self):
        for row in self.sampleliststore:
            row[0] = row[-1].title
            row[1] = row[-1].preparedby
            row[2] = str(row[-1].preparetime.date())
            row[3] = row[-1].thickness
            row[4] = row[-1].positionx
            row[5] = row[-1].positiony
            row[6] = row[-1].distminus
            row[7] = unicode(row[-1].transmission)
    def _tool_remove(self):
        model, it = self.sampletreeview.get_selection().get_selected()
        if it is not None:
            model.remove(it)
            self._changed()
    def _tool_duplicate(self):
        model, it = self.sampletreeview.get_selection().get_selected()
        if it is not None:
            sam = model[it][-1]
            sam = sample.SAXSSample(sam)
            sam.title = 'Copy of ' + sam.title
            self.add_sample(sam, it)
    def _tool_load(self):                
        self.credo.subsystems['Samples'].load()
        self.from_credo()
    def _tool_save(self):
        self.to_credo()
        self.credo.subsystems['Samples'].save()
        md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, 'Samples saved to file: ' + self.credo.subsystems['Samples'].configfile)
        md.run()
        md.destroy()
        del md
        
    def _tool_clear(self):
        self.sampleliststore.clear()
        self._changed()
    def _tool_refresh(self):
        self.from_credo()
    def _tool_edit(self):
        sel = self.sampletreeview.get_selection().get_selected()
        if sel[1] is not None:
            ssd = SampleSetup('Edit sample', self, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
            ssd.set_sample(sel[0][sel[1]][-1])
            resp = ssd.run()
            if resp == Gtk.ResponseType.OK:
                sel[0][sel[1]][-1] = ssd.update_sample(sel[0][sel[1]][-1])
                self.update_liststore()
            ssd.destroy()
            self._changed()
        
    def do_response(self, respid):
        if respid in(Gtk.ResponseType.CLOSE, Gtk.ResponseType.DELETE_EVENT):
            if self.get_widget_for_response(Gtk.ResponseType.APPLY).get_sensitive():
                md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.YES_NO, 'You have unsaved modifications. Do you want to apply them?')
                if md.run() == Gtk.ResponseType.YES:
                    self.to_credo()
                md.destroy()
                del md
            self.hide()
        if respid == Gtk.ResponseType.APPLY:
            self.to_credo()
    def to_credo(self):
        self.credo.subsystems['Samples'].clear()
        for row in self.sampleliststore:
            self.credo.subsystems['Samples'].add(row[-1])
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
    def from_credo(self):
        self.sampleliststore.clear()
        for sam in self.credo.subsystems['Samples']:
            self.add_sample(sam)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
            
class SampleSelector(Gtk.ComboBoxText):
    __gsignals__ = {'sample-changed':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                  }
    autorefresh = GObject.property(type=bool, default=True)
    def __init__(self, credo, autorefresh=True):
        Gtk.ComboBox.__init__(self)
        self.credo = credo
        self.credo.connect('samples-changed', lambda credo:self.reload_samples())
        self.autorefresh = autorefresh
        def _ar_handler(credo, sam):
            if self.autorefresh:
                self.set_sample(sam)
        self.credo.connect('sample-changed', _ar_handler)
        self.samplelist = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_PYOBJECT)
        self.set_model(self.samplelist)
        self.set_entry_text_column(0)
        self.reload_samples()
        self.show_all()
    def reload_samples(self):
        if self.get_active() >= 0 and self.get_active() < len(self.samplelist):
            sam_before = self.samplelist[self.get_active()][-1]
        else:
            sam_before = None
        self.samplelist.clear()
        self.samplelist.append(('-- UNKNOWN --', None))
        idx = 0
        for i, sam in enumerate(self.credo.get_samples()):
            if sam == self.credo.sample:
                idx = i
            self.samplelist.append((str(sam), sam))
        self.set_active(idx)
        if self.samplelist[self.get_active()][-1] != sam_before:
            self.emit('sample-changed', self.samplelist[self.get_active()][-1])
    def set_sample(self, sam):
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
        raise ValueError('Sample not in list!')
    def get_sample(self):
        return self.samplelist[self.get_active()][-1]
