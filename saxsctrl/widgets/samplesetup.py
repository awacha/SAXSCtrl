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

RESPONSE_SAVE = 1
RESPONSE_CLEAR = 2
RESPONSE_LOAD = 3
RESPONSE_REFRESH = 4
RESPONSE_ADD = 5
RESPONSE_REMOVE = 6
RESPONSE_DUPLICATE = 7
RESPONSE_EDIT = 8
RESPONSE_CLOSE = 9


class SampleSetup(Gtk.Dialog):
    def __init__(self, title='Define sample', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)):
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

        l = Gtk.Label(label='Position:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.position_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -100, 100, 0.1, 1), digits=3)
        tab.attach(self.position_entry, 1, 2, row, row + 1)
        self.position_entry.connect('value-changed', self.on_change_entry, 'position')
        row += 1
        
        l = Gtk.Label(label='Distance decrease:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.distminus_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1000, 1000, 0.1, 1), digits=4)
        tab.attach(self.distminus_entry, 1, 2, row, row + 1)
        self.distminus_entry.connect('value-changed', self.on_change_entry, 'distminus')
        row += 1
        
        l = Gtk.Label(label=u'Temperature (°C):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.temperature_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(25, -273, 1000, 0.1, 1), digits=2)
        tab.attach(self.temperature_entry, 1, 2, row, row + 1)
        self.temperature_entry.connect('value-changed', self.on_change_entry, 'temperature')
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
        temperature = self.temperature_entry.get_value()
        thickness = self.thickness_entry.get_value()
        position = self.position_entry.get_value()
        transmission = self.transmission_entry.get_value()
        preparedby = self.preparedby_entry.get_text()
        preparetime = self.preparetime_entry.get_date()
        distminus = self.distminus_entry.get_value()
        return sample.SAXSSample(title, position, thickness, transmission, temperature, preparedby, datetime.datetime(preparetime[0], preparetime[1] + 1, preparetime[2]), distminus)
    def set_sample(self, sam):
        self.samplename_entry.set_text(sam.title)
        self.temperature_entry.set_value(sam.temperature)
        self.thickness_entry.set_value(sam.thickness)
        self.position_entry.set_value(sam.position)
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
        
class SampleListDialog(Gtk.Dialog):
    def __init__(self, credo, title='Sample configuration', parent=None, flags=0, buttons=(
                                                                                           Gtk.STOCK_SAVE, RESPONSE_SAVE,
                                                                                           Gtk.STOCK_OPEN, RESPONSE_LOAD,
                                                                                           Gtk.STOCK_CLEAR, RESPONSE_CLEAR,
                                                                                           Gtk.STOCK_ADD, RESPONSE_ADD,
                                                                                           Gtk.STOCK_EDIT, RESPONSE_EDIT,
                                                                                           Gtk.STOCK_REMOVE, RESPONSE_REMOVE,
                                                                                           Gtk.STOCK_COPY, RESPONSE_DUPLICATE,
                                                                                           Gtk.STOCK_REFRESH, RESPONSE_REFRESH,
                                                                                           Gtk.STOCK_CLOSE, RESPONSE_CLOSE,
                                                                                           )):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.OK)
        self.credo = credo
        vb = self.get_content_area()
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(400, 300)
        vb.pack_start(sw, False, True, 0)
        # title, preparedby, preparetime, thickness, temperature, position, transmission
        self.sampleliststore = Gtk.ListStore(GObject.TYPE_STRING,  # title 
                                             GObject.TYPE_STRING,  # prepared by
                                             GObject.TYPE_STRING,  # preparation time
                                             GObject.TYPE_DOUBLE,  # thickness
                                             GObject.TYPE_DOUBLE,  # temperature
                                             GObject.TYPE_DOUBLE,  # position
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
        self.sampletreeview.append_column(Gtk.TreeViewColumn(u'Temperature (°C)', cr, text=4))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn(u'Position', cr, text=5))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn(u'Dist.decr.', cr, text=6))
        cr = Gtk.CellRendererText()
        self.sampletreeview.append_column(Gtk.TreeViewColumn(u'Transmission', cr, text=7))
        self.sampletreeview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.sampletreeview.set_headers_visible(True)
        self.sampletreeview.set_rules_hint(True)
        
        self.from_credo()
        self.connect('response', self.on_response)
    def add_sample(self, sam=None, index=None):
        if sam is None:
            sam = sample.SAXSSample('-- no title --', preparedby=self.credo.username)
        if index is not None:
            self.sampleliststore.insert_after(index, ('', '', '', 0.0, 0.0, 0.0, 0.0, '', sam))
        else:
            self.sampleliststore.append(('', '', '', 0.0, 0.0, 0.0, 0.0, '', sam))
        self.update_liststore()
    def update_liststore(self):
        for row in self.sampleliststore:
            row[0] = row[-1].title
            row[1] = row[-1].preparedby
            row[2] = str(row[-1].preparetime.date())
            row[3] = row[-1].thickness
            row[4] = row[-1].temperature
            row[5] = row[-1].position
            row[6] = row[-1].distminus
            row[7] = unicode(row[-1].transmission)
    def on_response(self, dialog, respid):
        if respid == RESPONSE_CLOSE:
            self.hide()
        elif respid == RESPONSE_SAVE:
            self.to_credo()
            self.credo.save_samples()
        elif respid == RESPONSE_LOAD:
            self.credo.load_samples()
            self.from_credo()
        elif respid == RESPONSE_CLEAR:
            self.sampleliststore.clear()
        elif respid == RESPONSE_REFRESH:
            self.from_credo()
        elif respid == RESPONSE_ADD:
            self.add_sample()
        elif respid == RESPONSE_REMOVE:
            sel = self.sampletreeview.get_selection().get_selected()
            if sel[1] is not None:
                sel[0].remove(sel[1])
        elif respid == RESPONSE_DUPLICATE:
            sel = self.sampletreeview.get_selection().get_selected()
            if sel[1] is not None:
                sam = sel[0][sel[1]][-1]
                sam = sample.SAXSSample(sam)
                sam.title = 'Copy of ' + sam.title
                self.add_sample(sam, sel[1])
        elif respid == RESPONSE_EDIT:
            sel = self.sampletreeview.get_selection().get_selected()
            if sel[1] is not None:
                ssd = SampleSetup('Edit sample', self, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
                ssd.set_sample(sel[0][sel[1]][-1])
                resp = ssd.run()
                if resp == Gtk.ResponseType.OK:
                    sel[0][sel[1]][-1] = ssd.update_sample(sel[0][sel[1]][-1])
                    self.update_liststore()
                ssd.destroy()
            pass
        self.to_credo()
    def to_credo(self):
        self.credo.clear_samples()
        for row in self.sampleliststore:
            self.credo.add_sample(row[-1])
    def from_credo(self):
        self.sampleliststore.clear()
        for sam in self.credo.get_samples():
            self.add_sample(sam)
            
