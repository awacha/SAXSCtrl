#
# coding: utf-8
import gtk
import datetime
import dateutil.parser
from ..hardware import sample
import gobject
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


class SampleSetup(gtk.Dialog):
    def __init__(self, title='Define sample', parent=None, flags=gtk.DIALOG_DESTROY_WITH_PARENT, buttons=(gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        vb = self.get_content_area()
        tab = gtk.Table()
        vb.pack_start(tab, False)
        self.set_resizable(False)
        row = 0
        
        l = gtk.Label('Sample name:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.samplename_entry = gtk.Entry()
        self.samplename_entry.set_text('-- please fill --')
        tab.attach(self.samplename_entry, 1, 2, row, row + 1)
        self.samplename_entry.connect('changed', self.on_change_entry, 'title')
        row += 1

        l = gtk.Label('Thickness (cm):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.thickness_entry = gtk.SpinButton(gtk.Adjustment(0.1, 0, 100, 0.1, 1), digits=4)
        tab.attach(self.thickness_entry, 1, 2, row, row + 1)
        self.thickness_entry.connect('value-changed', self.on_change_entry, 'thickness')
        row += 1

        l = gtk.Label('Position:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.position_entry = gtk.SpinButton(gtk.Adjustment(0, -100, 100, 0.1, 1), digits=3)
        tab.attach(self.position_entry, 1, 2, row, row + 1)
        self.position_entry.connect('value-changed', self.on_change_entry, 'position')
        row += 1
        
        l = gtk.Label('Distance decrease:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.distminus_entry = gtk.SpinButton(gtk.Adjustment(0, -1000, 1000, 0.1, 1), digits=4)
        tab.attach(self.distminus_entry, 1, 2, row, row + 1)
        self.distminus_entry.connect('value-changed', self.on_change_entry, 'distminus')
        row += 1
        
        l = gtk.Label(u'Temperature (°C):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.temperature_entry = gtk.SpinButton(gtk.Adjustment(25, -273, 1000, 0.1, 1), digits=2)
        tab.attach(self.temperature_entry, 1, 2, row, row + 1)
        self.temperature_entry.connect('value-changed', self.on_change_entry, 'temperature')
        row += 1

        l = gtk.Label(u'Transmission:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.transmission_entry = gtk.SpinButton(gtk.Adjustment(0.5, 0, 1, 0.1, 1), digits=4)
        tab.attach(self.transmission_entry, 1, 2, row, row + 1)
        self.transmission_entry.connect('value-changed', self.on_change_entry, 'transmission')
        row += 1

        l = gtk.Label(u'Prepared by:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.preparedby_entry = gtk.Entry()
        tab.attach(self.preparedby_entry, 1, 2, row, row + 1)
        self.preparedby_entry.connect('changed', self.on_change_entry, 'preparedby')
        row += 1
        
        l = gtk.Label(u'Preparation time:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, gtk.FILL, gtk.FILL)
        self.preparetime_entry = gtk.Calendar()
        self.preparetime_entry.set_display_options(gtk.CALENDAR_SHOW_DAY_NAMES | gtk.CALENDAR_SHOW_HEADING | gtk.CALENDAR_SHOW_WEEK_NUMBERS | gtk.CALENDAR_WEEK_START_MONDAY)
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
        return gtk.Dialog.run(self, *args, **kwargs)
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
            if isinstance(widget, gtk.SpinButton):
                sam.__setattr__(attr, widget.get_value())
            elif isinstance(widget, gtk.Entry):
                sam.__setattr__(attr, widget.get_text())
            elif isinstance(widget, gtk.Calendar):
                sam.__setattr__(attr, datetime.datetime(widget.get_date()[0], widget.get_date()[1] + 1, widget.get_date()[2]))
        self._changelist = []
        return sam
        
class SampleListDialog(gtk.Dialog):
    def __init__(self, credo, title='Sample configuration', parent=None, flags=0, buttons=(
                                                                                           gtk.STOCK_SAVE, RESPONSE_SAVE,
                                                                                           gtk.STOCK_OPEN, RESPONSE_LOAD,
                                                                                           gtk.STOCK_CLEAR, RESPONSE_CLEAR,
                                                                                           gtk.STOCK_ADD, RESPONSE_ADD,
                                                                                           gtk.STOCK_EDIT, RESPONSE_EDIT,
                                                                                           gtk.STOCK_REMOVE, RESPONSE_REMOVE,
                                                                                           gtk.STOCK_COPY, RESPONSE_DUPLICATE,
                                                                                           gtk.STOCK_REFRESH, RESPONSE_REFRESH,
                                                                                           gtk.STOCK_CLOSE, RESPONSE_CLOSE,
                                                                                           )):
        gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(gtk.RESPONSE_OK)
        self.credo = credo
        vb = self.get_content_area()
        sw = gtk.ScrolledWindow()
        sw.set_size_request(400, 300)
        vb.pack_start(sw, False)
        # title, preparedby, preparetime, thickness, temperature, position, transmission
        self.sampleliststore = gtk.ListStore(gobject.TYPE_STRING,  # title 
                                             gobject.TYPE_STRING,  # prepared by
                                             gobject.TYPE_STRING,  # preparation time
                                             gobject.TYPE_DOUBLE,  # thickness
                                             gobject.TYPE_DOUBLE,  # temperature
                                             gobject.TYPE_DOUBLE,  # position
                                             gobject.TYPE_DOUBLE,  # distminus
                                             gobject.TYPE_STRING,  # transmission (string, because +/- error can be given)
                                             gobject.TYPE_PYOBJECT,  # the Sample object itself
                                             )
        self.sampletreeview = gtk.TreeView(self.sampleliststore)
        sw.add(self.sampletreeview)
        cr = gtk.CellRendererText()
        self.sampletreeview.append_column(gtk.TreeViewColumn('Sample title', cr, text=0))
        cr = gtk.CellRendererText()
        self.sampletreeview.append_column(gtk.TreeViewColumn('Prepared by', cr, text=1))
        cr = gtk.CellRendererText()
        self.sampletreeview.append_column(gtk.TreeViewColumn('Date of preparation', cr, text=2))
        cr = gtk.CellRendererText()
        self.sampletreeview.append_column(gtk.TreeViewColumn('Thickness (cm)', cr, text=3))
        cr = gtk.CellRendererText()
        self.sampletreeview.append_column(gtk.TreeViewColumn(u'Temperature (°C)', cr, text=4))
        cr = gtk.CellRendererText()
        self.sampletreeview.append_column(gtk.TreeViewColumn(u'Position', cr, text=5))
        cr = gtk.CellRendererText()
        self.sampletreeview.append_column(gtk.TreeViewColumn(u'Dist.decr.', cr, text=6))
        cr = gtk.CellRendererText()
        self.sampletreeview.append_column(gtk.TreeViewColumn(u'Transmission', cr, text=7))
        self.sampletreeview.get_selection().set_mode(gtk.SELECTION_SINGLE)
        self.sampletreeview.set_headers_visible(True)
        self.sampletreeview.set_rules_hint(True)
        
        self.from_credo()
        self.connect('response', self.on_response)
    def add_sample(self, sam=None, index=None):
        if sam is None:
            sam = sample.SAXSSample('-- no title --', preparedby=self.credo.username)
        if index is not None:
            self.sampleliststore.insert_after(index, ('', '', '', 0, 0, 0, 0, 0, sam))
        else:
            self.sampleliststore.append(('', '', '', 0, 0, 0, 0, 0, sam))
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
            cp = ConfigParser.ConfigParser()
            for i, sam in enumerate(self.sampleliststore):
                sam[-1].save_to_ConfigParser(cp, 'Sample_%03d' % i)
            with open(os.path.expanduser('~/.config/credo/samplerc'), 'w+') as f:
                cp.write(f)
        elif respid == RESPONSE_LOAD:
            for sam in sample.SAXSSample.new_from_cfg(os.path.expanduser('~/.config/credo/samplerc')):
                self.add_sample(sam)
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
                ssd = SampleSetup('Edit sample', self, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
                ssd.set_sample(sel[0][sel[1]][-1])
                resp = ssd.run()
                if resp == gtk.RESPONSE_OK:
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
            
