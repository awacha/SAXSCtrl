from ..hardware import tmcl_motor
from gi.repository import Gtk
from gi.repository import GObject

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class MotorMonitorFrame(Gtk.Frame):
    def __init__(self, credo):
        Gtk.Frame.__init__(self)
        self.credo = credo
        self.credo.tmcm.connect('motor-report', self.on_motor_move)
        self.credo.tmcm.connect('motors-changed', self.on_motors_changed)
        self.credo.tmcm.connect('motor-limit', self.on_motor_limit)
        self.motorlist = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_FLOAT, GObject.TYPE_BOOLEAN, GObject.TYPE_BOOLEAN)
        self.motorview = Gtk.TreeView(self.motorlist)
        self.motorview.append_column(Gtk.TreeViewColumn('Name', Gtk.CellRendererText(), text=0))
        self.motorview.append_column(Gtk.TreeViewColumn('Alias', Gtk.CellRendererText(), text=1))
        self.motorview.append_column(Gtk.TreeViewColumn('Position', Gtk.CellRendererText(), text=2))
        self.motorview.connect('row-activated', self.on_row_activated)
        self.motorview.get_selection().set_mode(Gtk.SelectionMode.NONE)
        crt = Gtk.CellRendererToggle()
        crt.set_activatable(False)
        self.motorview.append_column(Gtk.TreeViewColumn('Left limit', crt, active=3))
        crt = Gtk.CellRendererToggle()
        crt.set_activatable(False)
        self.motorview.append_column(Gtk.TreeViewColumn('Right limit', crt, active=4))
        self.add(self.motorview)
        self.on_motors_changed(self.credo.tmcm)
        self.show_all()
    def on_row_activated(self, treeview, path, column):
        dd = MotorDriver(self.credo, self.motorlist[path][0], 'Move motor ' + self.motorlist[path][0], parent=self.get_toplevel(), buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        dd.run()
        dd.destroy()
    def on_motor_move(self, tmcm, mot, pos):
        for row in self.motorlist:
            if row[0] == mot.name:
                row[2] = pos
    def on_motors_changed(self, tmcm):
        self.motorlist.clear()
        for m in sorted(tmcm.motors):
            self.motorlist.append((m, tmcm.motors[m].alias, tmcm.motors[m].get_pos(), tmcm.motors[m].get_left_limit(), tmcm.motors[m].get_right_limit()))
    def on_motor_limit(self, tmcm, mot, left, right):
        for row in self.motorlist:
            if row[0] == mot.name:
                row[3] = left
                row[4] = right

class MotorMonitor(Gtk.Dialog):
    def __init__(self, credo, title='Motor positions', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=None):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_resizable(False)
        self.credo = credo
        self.mmframe = MotorMonitorFrame(self.credo)
        self.get_content_area().pack_start(self.mmframe, True, True, 0)
        self.show_all()
        
class MotorDriver(Gtk.Dialog):
    def __init__(self, credo, motorname, title='Move motor', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=None):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_resizable(False)
        self.credo = credo
        self.motorname = motorname
        vbox = self.get_content_area()
        tab = Gtk.Table()
        vbox.pack_start(tab, True, True, 0)
        l = Gtk.Label('Move ' + motorname + ' to:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.posentry = Gtk.Entry()
        self.posentry.set_text('0')
        self.posentry.connect('activate', self.on_move)
        tab.attach(self.posentry, 1, 2, 0, 1)
        b = Gtk.Button(label='Move')
        tab.attach(b, 2, 3, 0, 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', self.on_move)
        self.show_all()
    def on_move(self, widget):
        self.credo.tmcm.motors[self.motorname].moveto(float(self.posentry.get_text()))
        
