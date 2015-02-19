from ..hardware.instruments.tmcl_motor import MotorError
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk
from gi.repository import GLib

from .widgets import ToolDialog
import datetime
import os
import ConfigParser

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class MotorMonitorFrame(Gtk.Frame):
    def __init__(self, credo):
        Gtk.Frame.__init__(self)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vb)
        vb.pack_start(Gtk.Label(label='To move a motor, double-click on the corresponding row.'), False, False, 0)

        self.credo = credo
        self.credo.subsystems['Motors'].connect('motor-report', self.on_motor_move)
        self.credo.subsystems['Motors'].connect('motors-changed', self.on_motors_changed)
        self.credo.subsystems['Motors'].connect('motor-settings-changed', self.on_motor_settings_changed)
        self.credo.subsystems['Motors'].connect('motor-limit', self.on_motor_limit)
        self.motorlist = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_BOOLEAN, GObject.TYPE_BOOLEAN, GObject.TYPE_INT)
        self.motorview = Gtk.TreeView(self.motorlist)
        self.motorview.append_column(Gtk.TreeViewColumn('Name', Gtk.CellRendererText(), text=0))
        self.motorview.append_column(Gtk.TreeViewColumn('Alias', Gtk.CellRendererText(), text=1))
        self.motorview.append_column(Gtk.TreeViewColumn('Position', Gtk.CellRendererText(), text=2))
        self.motorview.append_column(Gtk.TreeViewColumn('Speed', Gtk.CellRendererText(), text=3))
        self.motorview.connect('row-activated', self.on_row_activated)
        self.motorview.get_selection().set_mode(Gtk.SelectionMode.NONE)
        crt = Gtk.CellRendererToggle()
        crt.set_activatable(False)
        self.motorview.append_column(Gtk.TreeViewColumn('Left limit', crt, active=4))
        crt = Gtk.CellRendererToggle()
        crt.set_activatable(False)
        self.motorview.append_column(Gtk.TreeViewColumn('Right limit', crt, active=5))
        self.motorview.append_column(Gtk.TreeViewColumn('Load', Gtk.CellRendererText(), text=6))
        vb.pack_start(self.motorview, True, True, 0)
        self.on_motors_changed(self.credo.subsystems['Motors'])
        self.show_all()
    def on_row_activated(self, treeview, path, column):
        dd = MotorDriver(self.credo, self.motorlist[path][0])
        dd.show_all()
    def on_motor_move(self, ssmot, mot, pos, speed, load):
        for row in self.motorlist:
            if row[0] == mot.name:
                row[2] = '%.3f' % pos
                row[3] = '%.2f' % speed
                row[6] = mot.get_parameter('Current_load')
    def on_motor_settings_changed(self, ssmot, mot):
        for row in self.motorlist:
            if row[0] == mot.name:
                row[1] = mot.alias
                row[2] = '%.3f' % (mot.get_parameter('Current_position'))
                row[3] = '%.2f' % (mot.get_parameter('Current_speed'))
                row[4] = mot.get_parameter('Left_limit_status')
                row[5] = mot.get_parameter('Right_limit_status')
                row[6] = mot.get_parameter('Current_load')
    def on_motors_changed(self, ssmot):
        self.motorlist.clear()
        for mot in ssmot.get_motors():
            self.motorlist.append((mot.name, mot.alias, '', '', False, False, 0))
            self.on_motor_settings_changed(ssmot, mot)
    def on_motor_limit(self, ssmot, mot, left, right):
        for row in self.motorlist:
            if row[0] == mot.name:
                row[4] = left
                row[5] = right
    def reload(self):
        self.on_motors_changed(self.credo.subsystems['Motors'])

class SaveMotorsDialog(Gtk.Dialog):
    def __init__(self, title='Save motor configuration', parent=None):
        Gtk.Dialog.__init__(self, title, parent, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, (Gtk.STOCK_SAVE, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.get_content_area().pack_start(hb, False, False, 0)
        l = Gtk.Label(label='Name of configuration:'); l.set_alignment(0, 0.5)
        hb.pack_start(l, False, False, 0)
        self._name_entry = Gtk.Entry()
        hb.pack_start(self._name_entry, True, True, 0)
        self._name_entry.set_text('Motor state at ' + str(datetime.datetime.now()))
        self._treemodel = Gtk.ListStore(GObject.TYPE_BOOLEAN, GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_FLOAT, GObject.TYPE_OBJECT)
        self._treeview = Gtk.TreeView(self._treemodel)
        cr = Gtk.CellRendererToggle()
        self._treeview.append_column(Gtk.TreeViewColumn('Include?', cr, active=0))
        cr.set_property('activatable', True)
        cr.connect('toggled', self._tobeincluded_toggled)
        self._treeview.append_column(Gtk.TreeViewColumn('Motor name', Gtk.CellRendererText(), text=1))
        self._treeview.append_column(Gtk.TreeViewColumn('Motor alias', Gtk.CellRendererText(), text=2))
        cr = Gtk.CellRendererSpin()
        tvc = Gtk.TreeViewColumn('Position', cr, text=3, adjustment=4)
        tvc.set_min_width(50)
        tvc.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        self._treeview.append_column(tvc)
        cr.set_property('editable', True)
        cr.connect('edited', self._position_changed)
        self._treeview.set_rules_hint(True)
        self._treeview.set_headers_visible(True)
        self._treeview.set_size_request(-1, 100)
        self.get_content_area().pack_start(self._treeview, True, True, 0)
        self.show_all()
    def _tobeincluded_toggled(self, cr, path):
        self._treemodel[path][0] ^= 1
        return True
    def _position_changed(self, cr, path, newtext):
        self._treemodel[path][3] = float(newtext)
        return True
    def _load_from_credo(self, credo):
        self._treemodel.clear()
        for m in credo.subsystems['Motors'].get_motors():
            pos = m.get_parameter('Current_position')
            self._treemodel.append([True, m.name, m.alias, pos, Gtk.Adjustment(pos, m.get_parameter('soft_left'), m.get_parameter('soft_right'), 1, 10)])
        return True
    def save_state(self, configparser):
        name = self._name_entry.get_text()
        if configparser.has_section(name):
            configparser.remove_section(name)
        configparser.add_section(name)
        for row in self._treemodel:
            if row[0]:
                configparser.set(name, row[1], row[3])
        return True

class MotorMonitor(ToolDialog):
    def __init__(self, credo, title='Motor positions'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, Gtk.STOCK_REFRESH, 1))
        self.mmframe = MotorMonitorFrame(self.credo)
        self.get_content_area().pack_start(self.mmframe, False, True, 0)
        f = Gtk.Frame(label='Stored motor configurations')
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.get_content_area().pack_start(f, True, True, 0)
        f.add(hb)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        hb.pack_start(sw, True, True, 0)
        vbb = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL)
        hb.pack_start(vbb, False, False, 0)
        self._motorstates_list = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_BOOLEAN, GObject.TYPE_UINT)  # name, motornames list, spinner enable, spinner pulse
        self._savedmotorstates_view = Gtk.TreeView(self._motorstates_list)
        sw.add(self._savedmotorstates_view)
        self._savedmotorstates_view.append_column(Gtk.TreeViewColumn('Name', Gtk.CellRendererText(), text=0))
        self._savedmotorstates_view.append_column(Gtk.TreeViewColumn('Motors saved', Gtk.CellRendererText(), text=1))
        cr = Gtk.CellRendererSpinner()
        self._savedmotorstates_view.append_column(Gtk.TreeViewColumn('', cr, active=2, pulse=3))

        self._savedmotorstates_view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self._savedmotorstates_view.set_rules_hint(True)
        self._savedmotorstates_view.set_headers_visible(True)
        self._savedmotorstates_view.connect('row-activated', self._on_row_activated)
        b = Gtk.Button('Add')
        b.set_image(Gtk.Image.new_from_icon_name('list-add',Gtk.IconSize.BUTTON))
        vbb.pack_start(b, True, True, 0)
        b.connect('clicked', self._on_add)
        b = Gtk.Button('Remove')
        b.set_image(Gtk.Image.new_from_icon_name('list-remove',Gtk.IconSize.BUTTON))
        vbb.pack_start(b, True, True, 0)
        b.connect('clicked', self._on_remove)
        b = Gtk.Button('Clear')
        b.set_image(Gtk.Image.new_from_icon_name('edit-clear',Gtk.IconSize.BUTTON))
        vbb.pack_start(b, True, True, 0)
        b.connect('clicked', self._on_clear)
        b = Gtk.Button('Execute')
        b.set_image(Gtk.Image.new_from_icon_name('system-run',Gtk.IconSize.BUTTON))
        vbb.pack_start(b, True, True, 0)
        b.connect('clicked', self._on_execute)
        b = Gtk.Button('Redefine')
        b.set_image(Gtk.Image.new_from_icon_name('document-save-as',Gtk.IconSize.BUTTON))
        vbb.pack_start(b, True, True, 0)
        b.connect('clicked', self._on_redefine)
        self._reload_from_file()
        self.show_all()
    def _reload_from_file(self):
        self._motorstates_list.clear()
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'))
        for s in sorted(cp.sections()):
            self._motorstates_list.append([s, ', '.join(cp.options(s)), False, 0])
        del cp
    def _on_row_activated(self, treeview, path, treeviewcolumn):
        if not isinstance(path, Gtk.TreeIter):
            path = self._motorstates_list.get_iter(path)
        row = self._motorstates_list[path]
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'))
        if not cp.has_section(row[0]):
            return
        ssm = self.credo.subsystems['Motors']
        self._movetostoredconfig_conn = ssm.connect('idle', self._movement_finished, path)
        self._movetostoredconfig_pulser = GLib.timeout_add(100, self._movement_pulse_spinner, path)
        row[2] = True
        for mname in cp.options(row[0]):
            position = cp.getfloat(row[0], mname)
            motor = ssm.get(mname, casesensitive=False)
            motor.moveto(position)
        treeview.set_sensitive(False)
        del cp
        return True
    def _on_execute(self, button):
        it = self._savedmotorstates_view.get_selection().get_selected()[1]
        return self._on_row_activated(self._savedmotorstates_view, it, None)
    def _on_redefine(self, button):
        it = self._savedmotorstates_view.get_selection().get_selected()[1]
        row=self._motorstates_list[it]
        ssm=self.credo.subsystems['Motors']
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'))
        if not cp.has_section(row[0]):
            return
        motors=cp.options(row[0])[:]
        cp.remove_section(row[0])
        cp.add_section(row[0])
        for mname in motors:
            motor=ssm.get(mname,casesensitive=False)
            cp.set(row[0],mname,motor.get_parameter('Current_position'))

        with open(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'), 'wt') as f:
            cp.write(f)
        del cp
        self._reload_from_file()



    def _movement_finished(self, ssm, it):
        ssm.disconnect(self._movetostoredconfig_conn)
        del self._movetostoredconfig_conn
        self._savedmotorstates_view.set_sensitive(True)
        GLib.source_remove(self._movetostoredconfig_pulser)
        del self._movetostoredconfig_pulser
        self._motorstates_list[it][2] = False
    def _movement_pulse_spinner(self, it):
        self._motorstates_list[it][3] += 1
        return True
    def _on_add(self, button):
        dialog = SaveMotorsDialog(parent=self)
        dialog._load_from_credo(self.credo)
        if dialog.run() == Gtk.ResponseType.OK:
            cp = ConfigParser.ConfigParser()
            cp.read(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'))
            dialog.save_state(cp)
            with open(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'), 'wt') as f:
                cp.write(f)
            del cp
            self._reload_from_file()
        dialog.destroy()
        del dialog
        return True
    def _on_remove(self, button):
        model, it = self._savedmotorstates_view.get_selection().get_selected()
        if it is not None:
            cp = ConfigParser.ConfigParser()
            cp.read(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'))
            if cp.has_section(model[it][0]):
                cp.remove_section(model[it][0])
            with open(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'), 'wt') as f:
                cp.write(f)
            del cp
            self._reload_from_file()
        return True
    def _on_clear(self, button):
        cp = ConfigParser.ConfigParser()
        with open(os.path.join(self.credo.subsystems['Files'].configpath, 'motorconfigs.conf'), 'wt') as f:
            cp.write(f)
        del cp
        self._reload_from_file()
        self.do_res
        return True
    def do_response(self, respid):
        if respid == 1:
            self.mmframe.reload()
        else:
            ToolDialog.do_response(self, respid)

class EntryPair(GObject.GObject):
    __gtype_name__ = 'SAXSCtrl_MotorParamEntryPair'
    __gsignals__ = {'motparentry-changed':(GObject.SignalFlags.RUN_FIRST, None, (object,)), }
    def __init__(self, stateholder, motpar):
        GObject.GObject.__init__(self)
        self._stateholder = stateholder
        self._motpar = motpar
        if self._motpar.rawminimum is None:
            min_ = -1e12
        else:
            min_ = self._motpar.rawminimum
        if self._motpar.rawmaximum is None:
            max_ = 1e12
        else:
            max_ = self._motpar.rawmaximum

        self.rawentry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, min_, max_, 1, 10), digits=[4, 0][self._motpar.isinteger])
        self.rawentry.set_numeric(True)
        self.physentry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e6, 1e6, 1, 10), digits=[4, 0][self._motpar.isinteger])
        self.physentry.set_numeric(True)
        self.rawentry.connect('value-changed', self._raw_changed)
        self.physentry.connect('value-changed', self._phys_changed)
        self.rawentry.connect('activate', lambda sb: sb.update())
        self.physentry.connect('activate', lambda sb:sb.update())
        self.rawentry.set_hexpand(True)
        self.physentry.set_hexpand(True)
    def _raw_changed(self, rawentry):
        logger.debug('_raw_changed: ' + self._motpar.name)
        physval = self._motpar.to_phys(self.rawentry.get_value(), self._stateholder._stateparams)
        if not self._motpar.validate(physval, self._stateholder._stateparams):
            self.rawentry.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(*Gdk.color_parse('red').to_floats()))
        else:
            self.rawentry.override_background_color(Gtk.StateType.NORMAL, None)
        if hasattr(self, 'setting_raw_because_phys_changed'):
            del self.setting_raw_because_phys_changed
            return
        if physval != self.physentry.get_value():
            self.setting_phys_because_raw_changed = True
            self.physentry.set_value(physval)
            self.emit('motparentry-changed', self._motpar)
    def _phys_changed(self, physentry):
        logger.debug('_phys_changed: ' + self._motpar.name)
        if not self._motpar.validate(self.physentry.get_value(), self._stateholder._stateparams):
            self.physentry.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(*Gdk.color_parse('red').to_floats()))
        else:
            self.physentry.override_background_color(Gtk.StateType.NORMAL, None)
        if hasattr(self, 'setting_phys_because_raw_changed'):
            del self.setting_phys_because_raw_changed
            return
        rawval = self._motpar.to_raw(self.physentry.get_value(), self._stateholder._stateparams)
        if rawval != self.rawentry.get_value():
            self.setting_raw_because_phys_changed = True
            self.rawentry.set_value(rawval)
            self.emit('motparentry-changed', self._motpar)
    def fromdevice(self):
        val = self._stateholder.get_parameter(self._motpar.name, raw=True)
        logger.debug('Fromdevice: ' + self._motpar.name + ' = ' + str(val))
        self.rawentry.set_value(val)
        self.rawentry.update()
    def todevice(self):
        logger.debug('Todevice: ' + self._motpar.name)
        self._stateholder.set_parameter(self._motpar.name, self.rawentry.get_value(), raw=True)

class MotorParamCheckButton(Gtk.CheckButton):
    __gsignals__ = {'motparentry-changed':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'toggled':'override'}
    __gtype_name__ = 'SAXSCtrl_MotorParamCheckButton'
    def __init__(self, stateholder, motpar, *args, **kwargs):
        Gtk.CheckButton.__init__(self, *args, **kwargs)
        self._stateholder = stateholder
        self._motpar = motpar
        self.set_hexpand(True)
    def do_toggled(self):
        self.emit('motparentry-changed', self._motpar)
    def fromdevice(self):
        self.set_active(self._stateholder.get_parameter(self._motpar.name))
    def todevice(self):
        self._stateholder.set_parameter(self._motpar.name, self.get_active())

class MotorParamSpinButton(Gtk.SpinButton):
    __gsignals__ = {'motparentry-changed':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'value-changed':'override'}
    __gtype_name__ = 'SAXSCtrl_MotorParamSpinButton'
    def __init__(self, stateholder, motpar):
        self._stateholder = stateholder
        self._motpar = motpar
        if motpar.rawminimum is not None:
            min_ = motpar.rawminimum
        else:
            min_ = -1e12
        if motpar.rawmaximum is not None:
            max_ = motpar.rawmaximum
        else:
            max_ = 1e12
        Gtk.SpinButton.__init__(self, adjustment=Gtk.Adjustment(0, min_, max_, 1, 10), digits=[3, 0][motpar.isinteger])
        self.set_hexpand(True)
    def do_value_changed(self):
        # ret = Gtk.SpinButton.do_value_changed(self)
        self.emit('motparentry-changed', self._motpar)
        # return ret
    def fromdevice(self):
        self.set_value(self._stateholder.get_parameter(self._motpar.name, raw=True))
        self.update()
    def todevice(self):
        self._stateholder.set_parameter(self._motpar.name, self.get_value(), raw=True)


class MotorDriver(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_MotorDriver'
    __gsignals__ = {'response':'override'}
    _noupdate_parameters = ['Target_position', 'Current_position']
    def __init__(self, credo, motorname, title=None):
        self.motor = credo.subsystems['Motors'].get(motorname)
        if title is None:
            title = 'Adjust motor %s' % str(self.motor)
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, Gtk.STOCK_REFRESH, 1, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_SAVE, 2))
        self.set_resizable(False)
        self.motorconns = []
        self._entries = []
        vbox = self.get_content_area()
        f = Gtk.Frame(label='Move motor')
        vbox.pack_start(f, False, True, 0)

        grid = Gtk.Grid()
        f.add(grid)
        row = 0
        l = Gtk.Label(label='Current position:'); l.set_alignment(0,0.5)
        grid.attach(l,0,row,1,1)

        self._poslabel=Gtk.Label(); self._poslabel.set_alignment(0,0.5)
        self._poslabel.set_label('%.03f'%self.motor.get_parameter('Current_position'))
        grid.attach(self._poslabel, 1, row, 1, 1)
        row +=1
        l = Gtk.Label(label='Move ' + motorname + ' to:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        grid.attach(hb, 1, row, 1, 1)
        hb.set_hexpand(True)
        self._moveto_entry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, -1e20, 1e20, 0.1, 1), digits=3)
        self._moveto_entry.connect('activate', self.on_moveto)
        hb.pack_start(self._moveto_entry, True, True, 0)
        self._motion_spinner = Gtk.Spinner()
        self._motion_spinner.set_no_show_all(True)
        hb.pack_start(self._motion_spinner, False, False, 0)
        row += 1

        self._relative_cb = Gtk.CheckButton(label='Relative move');
        self._relative_cb.set_alignment(0, 0.5)
        grid.attach(self._relative_cb, 0, row, 2, 1)
        row += 1

        hbb = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        grid.attach(hbb, 0, row, 2, 1)
        b = Gtk.Button(label='Move')
        hbb.add(b)
        b.connect('clicked', self.on_moveto)
        b = Gtk.Button(label='Stop')
        hbb.add(b)
        b.connect('clicked', self.on_stop)


        ex = Gtk.Expander(label='Advanced')
        vbox.pack_start(ex, False, False, 0)

        vbadvanced = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        ex.add(vbadvanced)

        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vbadvanced.pack_start(hb, False, False, 0)
        hb.set_hexpand(True)
        img = Gtk.Image(stock=Gtk.STOCK_DIALOG_WARNING, icon_size=Gtk.IconSize.DIALOG)
        hb.pack_start(img, False, False, 0)
        eb = Gtk.EventBox()
        l = Gtk.Label(label='<b>WARNING! Use with extreme care!</b>\nIncorrect settings may destroy driver electronics, motor or both!')
        l.set_use_markup(True)
        l.set_alignment(0, 0.5)
        eb.add(l)
        eb.set_border_width(5)
        eb.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(1, 0, 0, 1))
        hb.pack_start(eb, True, True, 0)



        # Expander to provide set-up interface to currents
        ex = Gtk.Expander()
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        ex.set_label_widget(hb)
        hb.pack_start(Gtk.Image(stock=Gtk.STOCK_DIALOG_WARNING, icon_size=Gtk.IconSize.MENU), False, False, 3)
        l = Gtk.Label(label='Currents')
        l.set_alignment(0, 0.5)
        hb.pack_start(l, True, True, 0)
        vbadvanced.pack_start(ex, False, False, 0)
        grid = Gtk.Grid()
        ex.add(grid)
        row = 0

        l = Gtk.Label(label='Driver units'); l.set_alignment(0.5, 0.5)
        grid.attach(l, 1, row, 1, 1)
        l = Gtk.Label(label='Physical units'); l.set_alignment(0.5, 0.5)
        grid.attach(l, 2, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Max RMS current (A):'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        ep = EntryPair(self, [m for m in self.motor.driver().motor_params if m.name == 'Max_RMS_current'][0])
        self._entries.append(ep)
        grid.attach(ep.rawentry, 1, row, 1, 1)
        grid.attach(ep.physentry, 2, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Standby RMS current (A):'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        ep = EntryPair(self, [m for m in self.motor.driver().motor_params if m.name == 'Standby_RMS_current'][0])
        self._entries.append(ep)
        grid.attach(ep.rawentry, 1, row, 1, 1)
        grid.attach(ep.physentry, 2, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Freewheeling delay (msec):'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        sb = MotorParamSpinButton(self, [m for m in self.motor.driver().motor_params if m.name == 'Freewheeling_delay'][0])
        self._entries.append(sb)
        grid.attach(sb, 1, row, 2, 1)

        # Expander to provide setup interface to position & limits

        ex = Gtk.Expander(label='Position & limits')
        vbadvanced.pack_start(ex, False, False, 0)
        grid = Gtk.Grid()
        ex.add(grid)
        l = Gtk.Label(label='Driver units'); l.set_alignment(0.5, 0.5)
        grid.attach(l, 1, row, 1, 1)
        l = Gtk.Label(label='Physical units'); l.set_alignment(0.5, 0.5)
        grid.attach(l, 2, row, 1, 1)
        row += 1

        l = Gtk.Button('Calibrate pos to:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        ep = EntryPair(self, [m for m in self.motor.driver().motor_params if m.name == 'Current_position'][0])
        grid.attach(ep.rawentry, 1, row, 1, 1)
        grid.attach(ep.physentry, 2, row, 1, 1)
        l.connect('clicked', lambda b, sb:self.calibrate_pos(sb), ep.rawentry)


        row += 1

        l = Gtk.Label(label='Left software limit:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        ep = EntryPair(self, [m for m in self.motor.driver().motor_params if m.name == 'soft_left'][0])
        self._entries.append(ep)
        grid.attach(ep.rawentry, 1, row, 1, 1)
        grid.attach(ep.physentry, 2, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Right software limit:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        ep = EntryPair(self, [m for m in self.motor.driver().motor_params if m.name == 'soft_right'][0])
        self._entries.append(ep)
        grid.attach(ep.rawentry, 1, row, 1, 1)
        grid.attach(ep.physentry, 2, row, 1, 1)
        row += 1

        cb = MotorParamCheckButton(self, [m for m in self.motor.driver().motor_params if m.name == 'Left_limit_disable'][0], label='Disable left limit switch')
        grid.attach(cb, 0, row, 3, 1)
        self._entries.append(cb)
        row += 1

        cb = MotorParamCheckButton(self, [m for m in self.motor.driver().motor_params if m.name == 'Right_limit_disable'][0], label='Disable right limit switch')
        grid.attach(cb, 0, row, 3, 1)
        self._entries.append(cb)
        row += 1

        ex = Gtk.Expander(label='Scales')
        vbadvanced.pack_start(ex, False, False, 0)
        grid = Gtk.Grid()
        ex.add(grid)
        row = 0
        l = Gtk.Label(label='Driver units'); l.set_alignment(0.5, 0.5)
        grid.attach(l, 1, row, 1, 1)
        l = Gtk.Label(label='Physical units'); l.set_alignment(0.5, 0.5)
        grid.attach(l, 2, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Full step physical size:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        sb = MotorParamSpinButton(self, [m for m in self.motor.driver().motor_params if m.name == 'step_to_cal'][0])
        self._entries.append(sb)
        grid.attach(sb, 1, row, 2, 1)
        row += 1

        l = Gtk.Label(label='Maximum speed:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        ep = EntryPair(self, [m for m in self.motor.driver().motor_params if m.name == 'Max_speed'][0])
        self._entries.append(ep)
        grid.attach(ep.rawentry, 1, row, 1, 1)
        grid.attach(ep.physentry, 2, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Maximum acceleration:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        ep = EntryPair(self, [m for m in self.motor.driver().motor_params if m.name == 'Max_accel'][0])
        self._entries.append(ep)
        grid.attach(ep.rawentry, 1, row, 1, 1)
        grid.attach(ep.physentry, 2, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Logarithmic microstep resolution:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        sb = MotorParamSpinButton(self, [m for m in self.motor.driver().motor_params if m.name == 'Ustep_resol'][0])
        self._entries.append(sb)
        grid.attach(sb, 1, row, 2, 1)
        row += 1

        l = Gtk.Label(label='Logarithmic pulse divisor:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        sb = MotorParamSpinButton(self, [m for m in self.motor.driver().motor_params if m.name == 'Pulse_div'][0])
        self._entries.append(sb)
        grid.attach(sb, 1, row, 2, 1)
        row += 1

        l = Gtk.Label(label='Logarithmic ramp divisor:'); l.set_alignment(0, 0.5)
        grid.attach(l, 0, row, 1, 1)
        sb = MotorParamSpinButton(self, [m for m in self.motor.driver().motor_params if m.name == 'Ramp_div'][0])
        self._entries.append(sb)
        grid.attach(sb, 1, row, 2, 1)
        row += 1

        for e in self._entries:
            e.connect('motparentry-changed', self.on_motparentry_changed)

        self.refresh_settings()
        self.show_all()
    def on_motparentry_changed(self, mpe, motpar):
        logger.debug('Motor parameter %s changed.' % motpar.name)
        mpe.todevice()
        for e in [e for e in self._entries if (motpar.name in e._motpar.depends) and (hasattr(e, '_raw_changed'))]:
            logger.debug('Recalculating %s because %s changed.' % (e._motpar.name, motpar.name))
            e._raw_changed(e.rawentry)
        logger.debug('Done recalculating.')

    def on_motor_report(self, motor, pos, speed, load):
        self._poslabel.set_label('%.03f'%pos)
        return False

    def on_motor_stop(self, motor):
        for c in self.motorconns:
            motor.disconnect(c)
        self.motorconns = []
        self._motion_spinner.stop()
        self._motion_spinner.hide()
        self._moveto_entry.set_sensitive(True)

    def on_motor_settings_changed(self, ssmot, motor):
        if motor != self.motor:
            return False
        else:
            self.refresh_settings()
            return False


    def refresh_settings(self):
        try:
            logger.debug("Refreshing settings of motor driver for %s" % str(self.motor))
            self.motor.reload_parameters()
            self._stateparams = self.motor._stateparams.copy()
            for e in self._entries:
                e.fromdevice()
        except MotorError as me:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, str(me))
            md.set_title('TMCM controller error')
            md.run()
            md.destroy()
            del md

    def get_parameter(self, name, raw=False):
        if raw:
            return self._stateparams[name]
        else:
            motpar = [m for m in self.motor.driver().motor_params if m.name == name][0]
            return motpar.to_phys(self._stateparams[name], self._stateparams)

    def set_parameter(self, name, value, raw=False):
        motpar = [m for m in self.motor.driver().motor_params if m.name == name][0]
        if motpar.readonly:
            raise MotorError('Attempted to set read-only parameter %s.' % name)
        if raw:
            physval = motpar.to_phys(value, self._stateparams)
            rawval = value
        else:
            physval = value
            rawval = motpar.to_raw(value, self._stateparams)

        if not motpar.validate(physval, self._stateparams):
            raise MotorError('Validation failed while setting parameter %s to %s.' % (motpar.name, str(value)))
        self._stateparams[name] = rawval

    def apply_settings(self, eeprom=False):

        self.refresh_settings()
    def on_moveto(self, widget):
        self._moveto_entry.update()
        self.motorconns.append(self.motor.connect('motor-report', self.on_motor_report))
        self.motorconns.append(self.motor.connect('motor-stop', self.on_motor_stop))
        try:
            self.motor.moveto(float(self._moveto_entry.get_value()), False, self._relative_cb.get_active())
            self._motion_spinner.start()
            self._motion_spinner.show_now()
            self._moveto_entry.set_sensitive(False)
        except MotorError as me:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, str(me))
            md.set_title('TMCM controller error')
            md.run()
            md.destroy()
            del md
            for mc in self.motorconns:
                self.motor.disconnect(mc)
            self.motorconns = []
    def on_stop(self, widget):
        self.motor.stop()
    def calibrate_pos(self, spinbutton):
        try:
            self.motor.calibrate_pos(spinbutton.get_value(), raw=True)
        except MotorError as me:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, str(me))
            md.set_title('TMCM controller error')
            md.run()
            md.destroy()
            del md
    def get_changes(self):
        return [k for k in self._stateparams if (self.motor._stateparams[k] != self._stateparams[k]) and not [mp for mp in self.motor.driver().motor_params if mp.name == k][0].readonly and (k not in self._noupdate_parameters)]

    def do_response(self, respid):
        if respid == 1:
            self.refresh_settings()
            return
        elif respid == 2:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, 'Do you really want to save the current motor state to the driver\'s EEPROM?')
            md.set_title('%s: save state to EEPROM' % str(self.motor))
            if md.run() == Gtk.ResponseType.YES:
                self.motor.store_to_EEPROM()
            md.destroy()
            del md
            return
        elif respid == Gtk.ResponseType.APPLY:
            changes = self.get_changes()
            if not changes: return
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, 'Do you really want to apply the following changes?')
            md.set_title('%s: apply changes' % str(self.motor))
            md.format_secondary_markup('Changed parameters:\n' + '\n'.join(['  - ' + k for k in changes]) + '\n\n<big><b>Please understand that wrong values can cause fatal damages to the driver, the motor or both.</b></big>')
            if md.run() == Gtk.ResponseType.YES:
                for k in changes:
                    self.motor.set_parameter(k, self._stateparams[k], raw=True)
            md.destroy()
            del md
            return
        else:
            return ToolDialog.do_response(self, respid)
