from gi.repository import Gtk
from ..hardware import pilatus, genix, credo, tmcl_motor

class InstrumentConnections(Gtk.Dialog):
    _filechooserdialogs = None
    def __init__(self, credo, title='Connections', parent=None, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_resizable(False)
        self.connect('response', lambda dialog, response_id:self.hide())
        self.credo = credo
        self.credo.connect('equipment-connection', self.on_credo_connect_equipment)

        vb = self.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        row = 0

        l = Gtk.Label(label='Pilatus host:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.camserverhost_entry = Gtk.Entry()
        self.camserverhost_entry.set_text('pilatus300k.saxs:41234')
        tab.attach(self.camserverhost_entry, 1, 2, row, row + 1)
        self.camserverconnect_button = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        tab.attach(self.camserverconnect_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.camserverconnect_button.connect('clicked', self.on_camserver_connect)
        row += 1
        
        l = Gtk.Label(label='GeniX host:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.genixhost_entry = Gtk.Entry()
        self.genixhost_entry.set_text('genix.saxs:502')
        tab.attach(self.genixhost_entry, 1, 2, row, row + 1)
        self.genixconnect_button = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        tab.attach(self.genixconnect_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.genixconnect_button.connect('clicked', self.on_genix_connect)
        row += 1

        l = Gtk.Label(label='Motor controller host:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.motorhost_entry = Gtk.Entry()
        self.motorhost_entry.set_text('pilatus300k.saxs:2001')
        tab.attach(self.motorhost_entry, 1, 2, row, row + 1)
        self.motorconnect_button = Gtk.Button(stock=Gtk.STOCK_CONNECT)
        tab.attach(self.motorconnect_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.motorconnect_button.connect('clicked', self.on_motor_connect)
        row += 1

        l = Gtk.Label(label='Image path:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.imagepath_entry = Gtk.Entry()
        self.imagepath_entry.set_text(self.credo.imagepath)
        self.imagepath_entry.connect('changed', self.on_entry_changed, 'imagepath')
        tab.attach(self.imagepath_entry, 1, 2, row, row + 1)
        self.imagepath_button = Gtk.Button(stock=Gtk.STOCK_OPEN)
        tab.attach(self.imagepath_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.imagepath_button.connect('clicked', self.on_pathbutton, self.imagepath_entry, Gtk.FileChooserAction.SELECT_FOLDER)
        self.credo.connect('notify::imagepath', lambda crd, par:self.imagepath_entry.set_text(crd.imagepath))
        row += 1

        l = Gtk.Label(label='File path:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.filepath_entry = Gtk.Entry()
        self.filepath_entry.set_text(self.credo.filepath)
        self.filepath_entry.connect('changed', self.on_entry_changed, 'filepath')
        tab.attach(self.filepath_entry, 1, 2, row, row + 1)
        self.filepath_button = Gtk.Button(stock=Gtk.STOCK_OPEN)
        tab.attach(self.filepath_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.filepath_button.connect('clicked', self.on_pathbutton, self.filepath_entry, Gtk.FileChooserAction.SELECT_FOLDER)
        self.credo.connect('notify::filepath', lambda crd, par:self.filepath_entry.set_text(crd.filepath))
        row += 1

        l = Gtk.Label(label='Scan file:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.scanfile_entry = Gtk.Entry()
        self.scanfile_entry.set_text(self.credo.scanfile)
        self.scanfile_entry.connect('changed', self.on_entry_changed, 'scanfile')
        tab.attach(self.scanfile_entry, 1, 3, row, row + 1)
        self.credo.connect('notify::scanfile', lambda crd, par:self.scanfile_entry.set_text(crd.scanfile))
        row += 1
        self.set_button_images()
        self.show_all()
    def set_button_images(self):
        for btn, equipment in [(self.camserverconnect_button, 'pilatus'), (self.genixconnect_button, 'genix'), (self.motorconnect_button, 'tmcm')]:
            if getattr(self.credo, equipment).connected():
                btn.set_label(Gtk.STOCK_DISCONNECT)
            else:
                btn.set_label(Gtk.STOCK_CONNECT)
    def on_credo_connect_equipment(self, credo, equipment, state, eqobject):
        self.set_button_images()
    def on_camserver_connect(self, button):
        if self.credo.pilatus.connected():
            self.credo.disconnect_equipment('Pilatus')
        else:
            try:
                self.credo.connect_equipment(self.camserverhost_entry.get_text(), 'Pilatus')
                self.credo.pilatus.setthreshold(4024, 'highG', blocking=False)
            except pilatus.PilatusError as pe:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message_format='Cannot connect to the Pilatus camserver!')
                md.format_secondary_text('Message: ' + pe.message)
                md.run()
                md.destroy()
                return
            
    def on_genix_connect(self, button):
        if self.credo.genix.connected():
            self.credo.disconnect_equipment('GeniX')
        else:
            try:
                self.credo.connect_equipment(self.genixhost_entry.get_text(), 'GeniX')
            except genix.GenixError as ge:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message_format='Cannot connect to genix controller!')
                md.format_secondary_text('Message: ' + ge.message)
                md.run()
                md.destroy()
                return
    def on_motor_connect(self, button):
        if self.credo.tmcm.connected():
            self.credo.disconnect_equipment('TMCM')
        else:
            try:
                self.credo.connect_equipment(self.motorhost_entry.get_text(), 'TMCM')
            except tmcl_motor.MotorError as me:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message_format='Cannot connect to motor controller!')
                md.format_secondary_text('Message: ' + me.message)
                md.run()
                md.destroy()
                return
    def on_pathbutton(self, button, entry, action):
        if self._filechooserdialogs is None:
            self._filechooserdialogs = {}
        if entry not in self._filechooserdialogs:
            self._filechooserdialogs[entry] = Gtk.FileChooserDialog('Select a folder...', None, action, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == Gtk.ResponseType.OK:
            entry.set_text(self._filechooserdialogs[entry].get_filename())
        self._filechooserdialogs[entry].hide()
        return True
    def on_entry_changed(self, entry, entrytext):
        with self.credo.freeze_notify():
            self.credo.__setattr__(entrytext, entry.get_text())
