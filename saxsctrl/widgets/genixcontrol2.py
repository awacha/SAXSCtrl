from .widgets import ToolDialog
from .instrumentstatus import InstrumentStatus, InstrumentStatusLabel
from ..hardware.instruments.genix import GenixStatus, InstrumentError
from gi.repository import Gtk

class GenixControl(ToolDialog):
    __gtype_name__ = 'SAXSCtrl_GenixControlWindow'
    def __init__(self, credo, title='X-ray source control'):
        ToolDialog.__init__(self, credo, title)
        self._statusframe = InstrumentStatus(self.credo.get_equipment('genix'), ncolumns=6)
        self.get_content_area().pack_start(self._statusframe, True, True, 0)
        self._statusframe.add_label('status', 'Status')
        self._statusframe.add_label('remote_mode', 'Remote', lambda x:['NO', 'YES'][int(x) % 2])
        self._statusframe.add_label('xrays', 'X-rays', lambda x:['OFF', 'ON'][int(x) % 2])
        self._statusframe.add_label('shutter', 'Shutter', lambda x:['CLOSED', 'OPEN'][int(x) % 2], InstrumentStatusLabel._default_colourer_reversed)
        self._statusframe.add_label('interlock', 'Interlock', lambda x:['BROKEN', 'OK'][int(x) % 2])
        self._statusframe.add_label('overridden', 'Overridden', lambda x:['NO', 'YES'][int(x) % 2])
        self._statusframe.add_label('ht', 'Voltage', '%.2f kV')
        self._statusframe.add_label('current', 'Current', '%.2f mA')
        self._statusframe.add_label('power', 'Power', '%.2f W')
        self._statusframe.add_label('tubetime', 'Tube life', '%.2f h')
        self._statusframe.add_label('tube_warmup_needed', 'Warm-up', lambda x:['not needed', 'needed'][int(x) % 2])
        self._statusframe.add_label('xray_light_fault', 'X-ray lights', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('shutter_light_fault', 'Shutter lights', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('vacuum_fault', 'Optics vacuum', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('waterflow_fault', 'Water cooling', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('tube_position_fault', 'Tube position', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('safety_shutter_fault', 'Shutter mechanism', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('temperature_fault', 'Tube temperature', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('relay_interlock_fault', 'Interlock relay', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('door_fault', 'Door sensor', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('filament_fault', 'Filament', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('sensor1_fault', 'Sensor #1', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('sensor2_fault', 'Sensor #2', lambda x:['OK', 'ERROR'][int(x) % 2])
        self._statusframe.add_label('conditions_auto', 'Can ramp-up', lambda x:['NO', 'OK'][int(x) % 2])
        
        self._statusframe.refresh_statuslabels()
        
        buttonbar = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        self.get_content_area().pack_start(buttonbar, False, False, 10)
        self._buttons = {}

        self._buttons['xrays'] = Gtk.Button(label='Turn X-rays ON')
        buttonbar.add(self._buttons['xrays'])
        self._buttons['xrays'].connect('clicked', self._on_xrays_clicked)
        self._buttons['shutter'] = Gtk.Button(label='Open shutter')
        buttonbar.add(self._buttons['shutter'])
        self._buttons['shutter'].connect('clicked', self._on_shutter_clicked)
        self._buttons['resetfailures'] = Gtk.Button(label='Reset failures')
        buttonbar.add(self._buttons['resetfailures'])
        self._buttons['resetfailures'].connect('clicked', self._on_resetfailures_clicked)
        self._buttons['powerdown'] = Gtk.Button(label='Power down')
        buttonbar.add(self._buttons['powerdown'])
        self._buttons['powerdown'].connect('clicked', self._on_powerdown_clicked)
        self._buttons['warmup'] = Gtk.Button(label='Start warm-up')
        buttonbar.add(self._buttons['warmup'])
        self._buttons['warmup'].connect('clicked', self._on_warmup_clicked)
        self._buttons['standby'] = Gtk.Button(label='Stand by')
        buttonbar.add(self._buttons['standby'])
        self._buttons['standby'].connect('clicked', self._on_standby_clicked)
        self._buttons['fullpower'] = Gtk.Button(label='Full power')
        buttonbar.add(self._buttons['fullpower'])
        self._buttons['fullpower'].connect('clicked', self._on_fullpower_clicked)
        
        genix = self.credo.get_equipment('genix')
        self._genixconnections = [genix.connect('notify::status', self._on_genix_status),
                                  genix.connect('instrumentproperty-notify', self._on_instrumentproperty_notify)]
        self._on_instrumentproperty_notify(genix, 'xrays')
        self._on_instrumentproperty_notify(genix, 'shutter')
        self._on_genix_status(genix, None)
        self.show_all()
    def _on_instrumentproperty_notify(self, genix, propertyname):
        if propertyname == 'xrays':
            if genix.xrays:
                self._buttons['xrays'].set_label('Turn X-rays OFF')
            else:
                self._buttons['xrays'].set_label('Turn X-rays ON')
        elif propertyname == 'shutter':
            if genix.shutter:
                self._buttons['shutter'].set_label('Close shutter')
            else:
                self._buttons['shutter'].set_label('Open shutter')
        elif propertyname == 'faults':
            self._buttons['resetfailures'].set_sensitive(genix.faults)
        return False
    def _on_genix_status(self, genix, property):
        for b in self._buttons:
            self._buttons[b].set_sensitive(False)
        self._buttons['resetfailures'].set_sensitive(genix.faults)
        status = genix.status
        if status == GenixStatus.Disconnected:
            return
        elif status == GenixStatus.Idle:
            self._buttons['powerdown'].set_sensitive(True)
        elif status == GenixStatus.FullPower:
            self._buttons['standby'].set_sensitive(True)
            self._buttons['powerdown'].set_sensitive(True)
            self._buttons['shutter'].set_sensitive(True)
        elif status in [GenixStatus.GoFullPower, GenixStatus.GoPowerDown, GenixStatus.GoStandby]:
            pass
        elif status == GenixStatus.WarmUp:
            self._buttons['warmup'].set_sensitive(True)
            self._buttons['warmup'].set_label('Stop warm-up')
        elif status == GenixStatus.PowerDown:
            self._buttons['standby'].set_sensitive(True)
            self._buttons['warmup'].set_sensitive(True)
            self._buttons['warmup'].set_label('Start warm-up')
            self._buttons['shutter'].set_sensitive(True)
            self._buttons['xrays'].set_sensitive(True)
        elif status == GenixStatus.XRaysOff:
            self._buttons['xrays'].set_sensitive(True)
        elif status == GenixStatus.Standby:
            self._buttons['shutter'].set_sensitive(True)
            self._buttons['powerdown'].set_sensitive(True)
            self._buttons['fullpower'].set_sensitive(True)

    def _on_xrays_clicked(self, button):
        try:
            if button.get_label().endswith('ON'):
                self.credo.get_equipment('genix').xrays_on()
            else:
                self.credo.get_equipment('genix').xrays_off()
        except InstrumentError as ie:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot turn X-rays on or off')
            md.format_secondary_text('Reason: ' + str(ie))
            md.run()
            md.destroy()
            self._on_genix_status(self.credo.get_equipment('genix'), None)
            del md

    def _on_shutter_clicked(self, button):
        try:
            if button.get_label().startswith('Open'):
                self.credo.get_equipment('genix').shutter_open()
            else:
                self.credo.get_equipment('genix').shutter_close()
        except InstrumentError as ie:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot operate shutter')
            md.format_secondary_text('Reason: ' + str(ie))
            md.run()
            md.destroy()
            self._on_genix_status(self.credo.get_equipment('genix'), None)
            del md
            

    def _on_resetfailures_clicked(self, button):
        try:
            self.credo.get_equipment('genix').reset_faults()
        except InstrumentError as ie:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot reset failures')
            md.format_secondary_text('Reason: ' + str(ie))
            md.run()
            md.destroy()
            self._on_genix_status(self.credo.get_equipment('genix'), None)
            del md
    
    def _on_fullpower_clicked(self, button):
        try:
            for b in self._buttons:
                self._buttons[b].set_sensitive(False)
            self.credo.get_equipment('genix').do_rampup()
        except InstrumentError as ie:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot go to full power')
            md.format_secondary_text('Reason: ' + str(ie))
            md.run()
            md.destroy()
            self._on_genix_status(self.credo.get_equipment('genix'), None)
            del md
    
    def _on_standby_clicked(self, button):
        try:
            for b in self._buttons:
                self._buttons[b].set_sensitive(False)
            self.credo.get_equipment('genix').do_standby()
        except InstrumentError as ie:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot go to stand-by mode')
            md.format_secondary_text('Reason: ' + str(ie))
            md.run()
            md.destroy()
            self._on_genix_status(self.credo.get_equipment('genix'), None)
            del md
    
    def _on_warmup_clicked(self, button):
        try:
            for b in self._buttons:
                self._buttons[b].set_sensitive(False)
            if button.get_label().startswith('Start'):
                self.credo.get_equipment('genix').do_warmup()
            else:
                self.credo.get_equipment('genix').stop_warmup()
        except InstrumentError as ie:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot ' + button.get_label().split()[0].lower() + ' warm-up cycle.')
            md.format_secondary_text('Reason: ' + str(ie))
            md.run()
            md.destroy()
            self._on_genix_status(self.credo.get_equipment('genix'), None)
            del md

    def _on_powerdown_clicked(self, button):
        try:
            for b in self._buttons:
                self._buttons[b].set_sensitive(False)
            self.credo.get_equipment('genix').do_poweroff()
        except InstrumentError as ie:
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Cannot power down X-ray tube')
            md.format_secondary_text('Reason: ' + str(ie))
            md.run()
            md.destroy()
            self._on_genix_status(self.credo.get_equipment('genix'), None)
            del md
        
