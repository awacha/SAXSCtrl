from ..hardware import tmcl_motor
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class MotorMonitorFrame(Gtk.Frame):
    def __init__(self, credo):
        Gtk.Frame.__init__(self)
        self.credo = credo
        self.credo.tmcm.connect('motor-report', self.on_motor_move)
        self.credo.tmcm.connect('motors-changed', self.on_motors_changed)
        self.credo.tmcm.connect('motor-settings-changed', self.on_motor_settings_changed)
        self.credo.tmcm.connect('motor-limit', self.on_motor_limit)
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
        self.add(self.motorview)
        self.on_motors_changed(self.credo.tmcm)
        self.show_all()
    def on_row_activated(self, treeview, path, column):
        dd = MotorDriver(self.credo, self.motorlist[path][0], 'Move motor ' + self.motorlist[path][0], parent=self.get_toplevel(), buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE))
        dd.connect('response', lambda dialog, response:dd.destroy())
        dd.show_all()
    def on_motor_move(self, tmcm, mot, pos, speed, load):
        for row in self.motorlist:
            if row[0] == mot.name:
                row[2] = '%.3f' % pos
                row[3] = '%.2f' % speed
                row[6] = mot.get_load()
    def on_motor_settings_changed(self, tmcm, mot):
        for row in self.motorlist:
            if row[0] == mot.name:
                row[1] = mot.alias
                row[2] = '%.3f' % (mot.get_pos())
                row[3] = '%.2f' % (mot.get_speed())
                row[4] = mot.get_left_limit()
                row[5] = mot.get_right_limit()
                row[6] = mot.get_load()
    def on_motors_changed(self, tmcm=None):
        self.motorlist.clear()
        print tmcm.motors
        for m in sorted(tmcm.motors):
            self.motorlist.append((m, tmcm.motors[m].alias, '%.2f' % (tmcm.motors[m].get_pos()), '%.2f' % (tmcm.motors[m].get_speed()), tmcm.motors[m].get_left_limit(), tmcm.motors[m].get_right_limit(), tmcm.motors[m].get_load()))
    def on_motor_limit(self, tmcm, mot, left, right):
        for row in self.motorlist:
            if row[0] == mot.name:
                row[4] = left
                row[5] = right

class MotorMonitor(Gtk.Dialog):
    def __init__(self, credo, title='Motor positions', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_resizable(False)
        self.credo = credo
        self.mmframe = MotorMonitorFrame(self.credo)
        self.get_content_area().pack_start(self.mmframe, True, True, 0)
        self.show_all()
        self.connect('response', self.on_response)
    def on_response(self, dlg, response):
        self.destroy()
        
class MotorDriver(Gtk.Dialog):
    def __init__(self, credo, motorname, title='Motor control', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=None):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_resizable(False)
        self.credo = credo
        self.motorname = motorname
        self.motorconns = []
        vbox = self.get_content_area()
        f = Gtk.Frame(label='Move motor')
        vbox.pack_start(f, False, True, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        l = Gtk.Label('Move ' + motorname + ' to:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.posentry = Gtk.Entry()
        self.posentry.set_text('0')
        self.posentry.connect('activate', self.on_move)
        tab.attach(self.posentry, 1, 2, row, row + 1)
        self.unitentry = Gtk.ComboBoxText()
        self.unitentry.append_text('physical units')
        self.unitentry.append_text('microsteps')
        self.unitentry.set_active(0)
        tab.attach(self.unitentry, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1

        self.relativecb = Gtk.CheckButton(label='Move relative to current position');
        self.relativecb.set_alignment(0, 0.5)
        tab.attach(self.relativecb, 0, 3, row, row + 1)
        row += 1
        
        hbb = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        tab.attach(hbb, 0, 3, row, row + 1)
        
        b = Gtk.Button(label='Move')
        hbb.add(b)
        b.connect('clicked', self.on_move)
        b = Gtk.Button(label='Stop')
        hbb.add(b)
        b.connect('clicked', self.on_stop)

        ex = Gtk.Expander(label='Advanced')
        vbox.pack_start(ex, False, False, 0)
        tab = Gtk.Table()
        ex.add(tab)
        row = 0
        eb = Gtk.EventBox()
        l = Gtk.Label('WARNING! Incorrect settings may destroy driver electronics, motor or both! Use with extreme care!')
        l.set_alignment(0, 0.5)
        l.set_line_wrap(True)
        eb.add(l)
        eb.modify_bg(Gtk.StateType.NORMAL, Gdk.Color.parse('red')[1])
        tab.attach(eb, 0, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        
        row += 1
        
        l = Gtk.Label('Physical units'); l.set_alignment(0.5, 0.5)
        tab.attach(l, 1, 2, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l = Gtk.Label('Driver units'); l.set_alignment(0.5, 0.5)
        tab.attach(l, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        row += 1
        
        l = Gtk.Button('Calibrate pos to:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        l.connect('clicked', lambda b:self.calibrate_pos())
        self.posentry_phys = Gtk.Entry()
        self.posentry_phys.set_text('0')
        tab.attach(self.posentry_phys, 1, 2, row, row + 1)
        self.posentry_raw = Gtk.Entry()
        tab.attach(self.posentry_raw, 2, 3, row, row + 1)
        self.posentry_phys.connect('key-press-event', self.on_edited, self.posentry_raw, self.conv_pos_raw)
        self.posentry_raw.connect('key-press-event', self.on_edited, self.posentry_phys, self.conv_pos_phys)
        row += 1

        l = Gtk.Label('Soft low limit:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.softlow_phys = Gtk.Entry()
        tab.attach(self.softlow_phys, 1, 2, row, row + 1)
        self.softlow_raw = Gtk.Entry()
        tab.attach(self.softlow_raw, 2, 3, row, row + 1)
        self.softlow_phys.connect('key-press-event', self.on_edited, self.softlow_raw, self.conv_pos_raw)
        self.softlow_raw.connect('key-press-event', self.on_edited, self.softlow_phys, self.conv_pos_phys)
        row += 1
        
        l = Gtk.Label('Soft high limit:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.softhigh_phys = Gtk.Entry()
        tab.attach(self.softhigh_phys, 1, 2, row, row + 1)
        self.softhigh_raw = Gtk.Entry()
        tab.attach(self.softhigh_raw, 2, 3, row, row + 1)
        self.softhigh_phys.connect('key-press-event', self.on_edited, self.softhigh_raw, self.conv_pos_raw)
        self.softhigh_raw.connect('key-press-event', self.on_edited, self.softhigh_phys, self.conv_pos_phys)
        row += 1
        
        l = Gtk.Label('Full step in physical units:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.step_to_physentry = Gtk.Entry()
        tab.attach(self.step_to_physentry, 1, 3, row, row + 1)
        row += 1
        
        l = Gtk.Label('Maximum speed:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.maxspeedentry_phys = Gtk.Entry()
        tab.attach(self.maxspeedentry_phys, 1, 2, row, row + 1)
        self.maxspeedentry_raw = Gtk.Entry()
        tab.attach(self.maxspeedentry_raw, 2, 3, row, row + 1)
        self.maxspeedentry_phys.connect('key-press-event', self.on_edited, self.maxspeedentry_raw, self.conv_speed_raw)
        self.maxspeedentry_raw.connect('key-press-event', self.on_edited, self.maxspeedentry_phys, self.conv_speed_phys)
        row += 1

        l = Gtk.Label('Maximum acceleration:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.maxaccelentry_phys = Gtk.Entry()
        tab.attach(self.maxaccelentry_phys, 1, 2, row, row + 1)
        self.maxaccelentry_raw = Gtk.Entry()
        tab.attach(self.maxaccelentry_raw, 2, 3, row, row + 1)
        self.maxaccelentry_phys.connect('key-press-event', self.on_edited, self.maxaccelentry_raw, self.conv_accel_raw)
        self.maxaccelentry_raw.connect('key-press-event', self.on_edited, self.maxaccelentry_phys, self.conv_accel_phys)
        row += 1

        l = Gtk.Label('Maximum current (RMS):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.maxcurrententry_phys = Gtk.Entry()
        tab.attach(self.maxcurrententry_phys, 1, 2, row, row + 1)
        self.maxcurrententry_raw = Gtk.Entry()
        tab.attach(self.maxcurrententry_raw, 2, 3, row, row + 1)
        self.maxcurrententry_phys.connect('key-press-event', self.on_edited, self.maxcurrententry_raw, lambda x:x * 255 / 2.8)
        self.maxcurrententry_raw.connect('key-press-event', self.on_edited, self.maxcurrententry_phys, lambda x:x * 2.8 / 255)
        row += 1

        l = Gtk.Label('Standby current (RMS):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.standbycurrententry_phys = Gtk.Entry()
        tab.attach(self.standbycurrententry_phys, 1, 2, row, row + 1)
        self.standbycurrententry_raw = Gtk.Entry()
        tab.attach(self.standbycurrententry_raw, 2, 3, row, row + 1)
        self.standbycurrententry_phys.connect('key-press-event', self.on_edited, self.standbycurrententry_raw, lambda x:x * 255 / 2.8)
        self.standbycurrententry_raw.connect('key-press-event', self.on_edited, self.standbycurrententry_phys, lambda x:x * 2.8 / 255)
        row += 1

        self.leftdisable_cb = Gtk.CheckButton('Disable left limit switch');
        self.leftdisable_cb.set_alignment(0, 0.5)
        tab.attach(self.leftdisable_cb, 0, 3, row, row + 1)
        row += 1
        
        self.rightdisable_cb = Gtk.CheckButton('Disable right limit switch');
        self.rightdisable_cb.set_alignment(0, 0.5)
        tab.attach(self.rightdisable_cb, 0, 3, row, row + 1)
        row += 1

        l = Gtk.Label('Microsteps / full step'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.ustepresol_combo = Gtk.ComboBoxText()
        for i in range(7):
            self.ustepresol_combo.append_text(str(2 ** i))
        tab.attach(self.ustepresol_combo, 1, 3, row, row + 1)
        row += 1
        
        l = Gtk.Label('Ramp divisor'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.rampdiventry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 13, 1, 1), digits=0)
        tab.attach(self.rampdiventry, 1, 3, row, row + 1)
        row += 1

        l = Gtk.Label('Pulse divisor'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.pulsediventry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 13, 1, 1), digits=0)
        tab.attach(self.pulsediventry, 1, 3, row, row + 1)
        row += 1

        self.mixeddecaycb = Gtk.CheckButton('Mixed decay threshold speed:')
        self.mixeddecaycb.set_alignment(0, 0.5)
        self.mixeddecaycb.connect('toggled', self.on_mixeddecaycb)
        tab.attach(self.mixeddecaycb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.mixeddecayentry_phys = Gtk.Entry()
        tab.attach(self.mixeddecayentry_phys, 1, 2, row, row + 1)
        self.mixeddecayentry_raw = Gtk.Entry()
        tab.attach(self.mixeddecayentry_raw, 2, 3, row, row + 1)
        self.mixeddecayentry_phys.connect('key-press-event', self.on_edited, self.mixeddecayentry_raw, self.conv_speed_raw)
        self.mixeddecayentry_raw.connect('key-press-event', self.on_edited, self.mixeddecayentry_phys, self.conv_speed_phys)
        self.on_mixeddecaycb(self.mixeddecaycb)
        row += 1

        self.fullstepcb = Gtk.CheckButton('Full step threshold speed:')
        self.fullstepcb.set_alignment(0, 0.5)
        self.fullstepcb.connect('toggled', self.on_fullstepcb)
        tab.attach(self.fullstepcb, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.fullstepentry_phys = Gtk.Entry()
        tab.attach(self.fullstepentry_phys, 1, 2, row, row + 1)
        self.fullstepentry_raw = Gtk.Entry()
        tab.attach(self.fullstepentry_raw, 2, 3, row, row + 1)
        self.fullstepentry_phys.connect('key-press-event', self.on_edited, self.fullstepentry_raw, self.conv_speed_raw)
        self.fullstepentry_raw.connect('key-press-event', self.on_edited, self.fullstepentry_phys, self.conv_speed_phys)
        self.on_fullstepcb(self.fullstepcb)
        row += 1
        
        l = Gtk.Label('Freewheeling delay (msec):'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.freewheelingdelayentry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 65535, 1, 10), digits=0)
        tab.attach(self.freewheelingdelayentry, 1, 3, row, row + 1)
        row += 1
        
        l = Gtk.Label('stallGuard (TM) level:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.stallguardthresholdentry = Gtk.SpinButton(adjustment=Gtk.Adjustment(0, 0, 7, 1, 1), digits=0)
        tab.attach(self.stallguardthresholdentry, 1, 3, row, row + 1)
        row += 1
        self.refresh_settings()

        self.on_edited(self.posentry_phys, None, self.posentry_raw, self.conv_pos_raw)

        hbb = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        tab.attach(hbb, 0, 3, row, row + 1)
        b = Gtk.Button('Refresh')
        hbb.add(b)
        b.connect('clicked', lambda b: self.refresh_settings())
        b = Gtk.Button('Apply')
        hbb.add(b)
        b.connect('clicked', lambda b: self.apply_settings())
        b = Gtk.Button('Apply to EEPROM')
        hbb.add(b)
        b.connect('clicked', lambda b: self.apply_settings(eeprom=True))
        
        self.credo.tmcm.connect('motor-settings-changed', self.on_motor_settings_changed)
        
        ex.connect('notify::expanded', lambda expander, paramspec:self.refresh_settings())
    
        self.show_all()
    def on_motor_report(self, motor, pos, speed, load):
        if self.unitentry.get_active():
            pos = motor.conv_pos_raw(pos)
        self.posentry.set_text(str(pos))
        return False
    def on_motor_stop(self, motor):
        for c in self.motorconns:
            motor.disconnect(c)
        self.motorconns = []
    def on_motor_settings_changed(self, tmcm, motor):
        if motor.name != self.motorname:
            return False
        else:
            self.refresh_settings()
            return False
    def on_mixeddecaycb(self, cb):
        self.mixeddecayentry_phys.set_sensitive(cb.get_active())
        self.mixeddecayentry_raw.set_sensitive(cb.get_active())
        if not self.mixeddecaycb.get_active():
            self.mixeddecayentry_phys.set_text('Always ON')
            self.mixeddecayentry_raw.set_text('Always ON')
        else:
            try:
                mdt = self.get_motor().get_mixed_decay_threshold()
                self.mixeddecayentry_raw.set_text(str(mdt))
                self.mixeddecayentry_phys.set_text(str(self.conv_speed_phys(mdt)))
            except tmcl_motor.MotorError as me:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, me.message)
                md.set_title('TMCM351 error')
                md.run()
                md.destroy()
                del md
            
    def on_fullstepcb(self, cb):
        self.fullstepentry_phys.set_sensitive(cb.get_active())
        self.fullstepentry_raw.set_sensitive(cb.get_active())
        if not cb.get_active():
            self.fullstepentry_phys.set_text('Disabled')
            self.fullstepentry_raw.set_text('Disabled')
        else:
            try:
                fst = self.get_motor().get_fullstep_threshold()
                self.fullstepentry_raw.set_text(str(fst))
                self.fullstepentry_phys.set_text(str(self.conv_speed_phys(fst)))
            except tmcl_motor.MotorError as me:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, me.message)
                md.set_title('TMCM351 error')
                md.run()
                md.destroy()
                del md
            
    def refresh_settings(self):
        try:
            motor = self.credo.tmcm.motors[self.motorname]
            softlim = motor.softlimits
            self.softlow_phys.set_text(str(min(softlim)))
            self.softhigh_phys.set_text(str(max(softlim)))
            self.softlow_raw.set_text(str(motor.conv_pos_raw(min(softlim))))
            self.softhigh_raw.set_text(str(motor.conv_pos_raw(max(softlim))))
            self.maxspeedentry_raw.set_text(str(motor.get_max_speed(True)))
            self.maxspeedentry_phys.set_text(str(motor.get_max_speed(False)))
            self.maxaccelentry_raw.set_text(str(motor.get_max_accel(True)))
            self.maxaccelentry_phys.set_text(str(motor.get_max_accel(False)))
            self.maxcurrententry_raw.set_text(str(motor.get_max_raw_current()))
            self.maxcurrententry_phys.set_text(str(motor.get_max_rms_current()))
            self.standbycurrententry_raw.set_text(str(motor.get_standby_raw_current()))
            self.standbycurrententry_phys.set_text(str(motor.get_standby_rms_current()))
            self.step_to_physentry.set_text(str(motor.step_to_cal))
            self.leftdisable_cb.set_active(motor.get_left_limit_disable())
            self.rightdisable_cb.set_active(motor.get_right_limit_disable())
            self.ustepresol_combo.set_active(motor.get_ustep_resolution())
            self.rampdiventry.set_value(motor.get_ramp_div())
            self.pulsediventry.set_value(motor.get_pulse_div())
            mdt = motor.get_mixed_decay_threshold()
            self.mixeddecayentry_raw.set_text(str(mdt))
            self.mixeddecayentry_phys.set_text(str(self.conv_speed_phys(mdt)))
            self.mixeddecaycb.set_active(mdt >= 0)
            self.on_mixeddecaycb(self.mixeddecaycb)
            fst = motor.get_fullstep_threshold()
            self.fullstepentry_raw.set_text(str(fst))
            self.fullstepentry_phys.set_text(str(self.conv_speed_phys(fst)))
            self.fullstepcb.set_active(fst not in [0, 2048])
            self.on_fullstepcb(self.fullstepcb)
            self.freewheelingdelayentry.set_value(motor.get_freewheeling_delay())
            self.stallguardthresholdentry.set_value(motor.get_stallguard_threshold())
        except tmcl_motor.MotorError as me:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, me.message)
            md.set_title('TMCM351 error')
            md.run()
            md.destroy()
            del md
        
    def apply_settings(self, eeprom=False):
        motor = self.get_motor()
        oldsettings = motor.get_settings()
        oldsettings['Soft_limits'] = motor.softlimits
        oldsettings['ustep_to_phys'] = motor.step_to_cal
        newsettings = {'Soft_limits':(float(self.softlow_phys.get_text()), float(self.softhigh_phys.get_text())),
                       'ustep_to_phys':float(self.step_to_physentry.get_text()),
                       'Max_speed':int(self.maxspeedentry_raw.get_text()),
                       'Max_accel':int(self.maxaccelentry_raw.get_text()),
                       'Max_current':int(self.maxcurrententry_raw.get_text()),
                       'Standby_current':int(self.standbycurrententry_raw.get_text()),
                       'Right_limit_disable':bool(self.rightdisable_cb.get_active()),
                       'Left_limit_disable':bool(self.leftdisable_cb.get_active()),
                       'Ustep_resol':self.ustepresol_combo.get_active(),
                       'Ramp_div':self.rampdiventry.get_value_as_int(),
                       'Pulse_div':self.pulsediventry.get_value_as_int(),
                       'Stallguard_threshold':self.stallguardthresholdentry.get_value_as_int(),
                       'Freewheeling_delay':self.freewheelingdelayentry.get_value_as_int(),
                     }
        
        if self.mixeddecaycb.get_active():
            newsettings['Mixed_decay_threshold'] = int(self.mixeddecayentry_raw.get_text())
        else:
            newsettings['Mixed_decay_threshold'] = -1
        if self.fullstepcb.get_active():
            newsettings['Fullstep_threshold'] = int(self.fullstepentry_raw.get_text())
        else:
            newsettings['Fullstep_threshold'] = 0

        possiblylethalsettings = ['Max_current', 'Standby_current', 'Right_limit_disable', 'Left_limit_disable']
        dangeroussettings = ['Max_speed', 'Max_accel', 'Ramp_div', 'Pulse_div', 'Stallguard_threshold', 'Soft_limits']
        
        tobechanged = [n for n in newsettings if newsettings[n] != oldsettings[n]]
        if tobechanged:
            if [n for n in tobechanged if n in possiblylethalsettings]:
                type_ = Gtk.MessageType.WARNING
                message = 'Warning! Adjusting coil currents and limit switch values may cause damage to motor, driver electronics or both. Are you really sure? Do you still want to continue?'
            elif [n for n in tobechanged if n in dangeroussettings]:
                type_ = Gtk.MessageType.QUESTION
                message = 'Warning! Setting speed, acceleration, divisors, soft limits or stallGuard(TM) threshold values might be dangerous. Are you really sure?'
            else:
                type_ = Gtk.MessageType.INFO
                message = 'Are you sure to update the following parameters?'
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, type_, Gtk.ButtonsType.OK_CANCEL, message)
            md.set_title('Confirm changes')
            
            md.format_secondary_text('Changes to be done:\n' + ', '.join(tobechanged))
            result = md.run()
            md.destroy()
            del md
            if result == Gtk.ResponseType.OK:
                try:
                    for n in tobechanged:
                        if n == 'Soft_limits': motor.softlimits = newsettings[n]
                        elif n == 'ustep_to_phys': motor.step_to_cal = newsettings[n]
                        elif n == 'Max_speed': motor.set_max_speed(newsettings[n], raw=True)
                        elif n == 'Max_accel': motor.set_max_accel(newsettings[n], raw=True)
                        elif n == 'Max_current': motor.set_max_raw_current(newsettings[n])
                        elif n == 'Standby_current': motor.set_standby_raw_current(newsettings[n])
                        elif n == 'Right_limit_disable': motor.set_right_limit_disable(newsettings[n])
                        elif n == 'Left_limit_disable': motor.set_left_limit_disable(newsettings[n])
                        elif n == 'Ustep_resol': motor.set_ustep_resolution(newsettings[n])
                        elif n == 'Ramp_div': motor.set_ramp_div(newsettings[n])
                        elif n == 'Pulse_div': motor.set_pulse_div(newsettings[n])
                        elif n == 'Stallguard_threshold': motor.set_stallguard_threshold(newsettings[n])
                        elif n == 'Freewheeling_delay': motor.set_freewheeling_delay(newsettings[n])
                        elif n == 'Mixed_decay_threshold': motor.set_mixed_decay_threshold(newsettings[n])
                        elif n == 'Fullstep_threshold': motor.set_fullstep_threshold(newsettings[n])
                        else:
                            raise NotImplementedError('Unknown parameter: ' + n)
                except tmcl_motor.MotorError as me:
                    md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, me.message)
                    md.set_title('TMCM351 error')
                    md.run()
                    md.destroy()
                    del md
        if eeprom:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK_CANCEL, 'Changes are going to be written to the permanent memory of the motor controller. They will be permanent after power-down of the module. IS THIS REALLY WHAT YOU WANT?')
            md.set_title('Confirm saving to EEPROM')
            result = md.run()
            md.destroy()
            del md
            if result == Gtk.ResponseType.OK:
                motor.store_to_EEPROM()
                
        self.refresh_settings()
    def on_move(self, widget):
        try:
            self.motorconns.append(self.get_motor().connect('motor-report', self.on_motor_report))
            self.motorconns.append(self.get_motor().connect('motor-stop', self.on_motor_stop))
            
            if self.relativecb.get_active():
                self.get_motor().moverel(float(self.posentry.get_text()), raw=bool(self.unitentry.get_active()))
            else:
                self.get_motor().moveto(float(self.posentry.get_text()), raw=bool(self.unitentry.get_active()))
        except tmcl_motor.MotorError as me:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, me.message)
            md.set_title('TMCM351 error')
            md.run()
            md.destroy()
            del md
    def get_motor(self):
        return self.credo.tmcm.motors[self.motorname]
    def on_stop(self, widget):
        self.credo.tmcm.motors[self.motorname].stop()
    def _on_edited_idle(self, widget, otherwidget, converter):
        if isinstance(converter, basestring):
            converter = getattr(self.credo.tmcm.motors[self.motorname], converter)
        try:
            otherwidget.set_text(str(converter(float(widget.get_text()))))
        except ValueError:
            otherwidget.set_text('')
        return False
    def on_edited(self, widget, event, otherwidget, converter):
        GObject.idle_add(self._on_edited_idle, widget, otherwidget, converter)
    def calibrate_pos(self):
        try:
            self.credo.tmcm.motors[self.motorname].calibrate_pos(int(float(self.posentry_raw.get_text())), raw=True)
        except tmcl_motor.MotorError as me:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, me.message)
            md.set_title('TMCM351 error')
            md.run()
            md.destroy()
            del md
    def get_settings(self):
        return {'Pulse_div':self.pulsediventry.get_value_as_int(), 'Ramp_div':self.rampdiventry.get_value_as_int(),
                'Ustep_resol':self.ustepresol_combo.get_active()}
    def conv_speed_raw(self, speed_phys):
        settings = self.get_settings()
        return int(speed_phys * 2 ** settings['Pulse_div'] * 2048.0 * 32 * 2 ** settings['Ustep_resol'] / (float(self.step_to_physentry.get_text()) * self.get_motor().f_clk))
    def conv_speed_phys(self, speed_raw):
        settings = self.get_settings()
        return float(self.step_to_physentry.get_text()) * speed_raw * self.get_motor().f_clk / (2 ** settings['Pulse_div'] * 2048.0 * 32 * 2 ** settings['Ustep_resol'])
    def conv_pos_raw(self, pos_phys):
        settings = self.get_settings()
        return int(pos_phys / float(self.step_to_physentry.get_text()) * 2 ** settings['Ustep_resol'])
    def conv_pos_phys(self, pos_raw):
        settings = self.get_settings()
        return pos_raw * float(self.step_to_physentry.get_text()) / 2 ** settings['Ustep_resol']
    def conv_accel_raw(self, accel_phys):
        settings = self.get_settings()
        return int(accel_phys / (self.get_motor().f_clk ** 2 * float(self.step_to_physentry.get_text())) * (2 ** (settings['Pulse_div'] + settings['Ramp_div'] + 29) * 2 ** settings['Ustep_resol'])) 
    def conv_accel_phys(self, accel_raw):
        settings = self.get_settings()
        return self.get_motor().f_clk ** 2 * accel_raw / (2 ** (settings['Pulse_div'] + settings['Ramp_div'] + 29)) * (float(self.step_to_physentry.get_text()) / 2 ** settings['Ustep_resol']) 
        
