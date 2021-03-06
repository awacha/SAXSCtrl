from gi.repository import Gtk
from ..hardware import subsystems
from .widgets import ToolDialog

class InstrumentConnections(ToolDialog):
    _filechooserdialogs = None
    def __init__(self, credo, title='Connections'):
        ToolDialog.__init__(self, credo, title, buttons=('OK', Gtk.ResponseType.OK, 'Apply', Gtk.ResponseType.APPLY, 'Cancel', Gtk.ResponseType.CANCEL))
        self.connect('response', lambda dialog, response_id:self.hide())
        self.credo.subsystems['Equipments'].connect('equipment-connection', self._on_connect_equipment)

        vb = self.get_content_area()
        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        row = 0

        self.addressentries = {}
        self.connectbuttons = {}
        for row, equipment in enumerate(self.credo.subsystems['Equipments'].known_equipments()):
            l = Gtk.Label(label=equipment.capitalize() + ' address'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
            tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
            self.addressentries[equipment] = Gtk.Entry()
            self.addressentries[equipment].set_text(self.credo.get_equipment(equipment).address)
            tab.attach(self.addressentries[equipment], 1, 2, row, row + 1)
            self.connectbuttons[equipment] = Gtk.Button(label='Connect')
            tab.attach(self.connectbuttons[equipment], 2, 3, row, row + 1, Gtk.AttachOptions.FILL)
            self.connectbuttons[equipment].connect('clicked', self._equipment_connect, equipment)

        row += 1

        l = Gtk.Label(label='Root path:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.filepath_entry = Gtk.Entry()
        self.filepath_entry.set_text(self.credo.subsystems['Files'].rootpath)
        self.filepath_entry.connect('changed', self.on_entry_changed, 'rootpath', self.credo.subsystems['Files'])
        tab.attach(self.filepath_entry, 1, 2, row, row + 1)
        self.filepath_button = Gtk.Button(label='Open')
        tab.attach(self.filepath_button, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.filepath_button.connect('clicked', self.on_pathbutton, self.filepath_entry, Gtk.FileChooserAction.SELECT_FOLDER)
        self.credo.subsystems['Files'].connect('notify::rootpath', lambda ssf, par:self.filepath_entry.set_text(ssf.rootpath))
        row += 1

#         l = Gtk.Label(label='Scan file:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
#         tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
#         self.scanfile_entry = Gtk.Entry()
#         self.scanfile_entry.set_text(self.credo.subsystems['Scan'].scanfilename)
#         self.scanfile_entry.connect('changed', self.on_entry_changed, 'scanfilename', self.credo.subsystems['Scan'])
#         tab.attach(self.scanfile_entry, 1, 3, row, row + 1)
#         self.credo.subsystems['Scan'].connect('notify::scanfilename', lambda sss, par:self.scanfile_entry.set_text(sss.scanfilename))
#         row += 1

        self.set_button_images()
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        self.show_all()

    def set_button_images(self):
        for equipment in self.connectbuttons:
            if self.credo.get_equipment(equipment).connected():
                self.connectbuttons[equipment].set_label('Disconnect')
            else:
                self.connectbuttons[equipment].set_label('Connect')

    def _equipment_connect(self, button, equipment):
        if self.credo.subsystems['Equipments'].is_connected(equipment):
            self.credo.subsystems['Equipments'].disconnect_equipment(equipment)
        else:
            try:
                self.credo.subsystems['Equipments'].connect_equipment(equipment, address=self.addressentries[equipment].get_text())
            except subsystems.SubSystemError as sse:
                md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message_format='Cannot connect to equipment %s!' % equipment)
                md.format_secondary_text('Error message: ' + str(sse))
                md.run()
                md.destroy()

    def _on_connect_equipment(self, subsys, equipment, conn_or_disconn, normal_or_abnormal):
        self.set_button_images()

    def on_pathbutton(self, button, entry, action):
        if self._filechooserdialogs is None:
            self._filechooserdialogs = {}
        if entry not in self._filechooserdialogs:
            self._filechooserdialogs[entry] = Gtk.FileChooserDialog('Select a folder...', None, action, buttons=('OK', Gtk.ResponseType.OK, 'Cancel', Gtk.ResponseType.CANCEL))
        self._filechooserdialogs[entry].set_filename(entry.get_text())
        response = self._filechooserdialogs[entry].run()
        if response == Gtk.ResponseType.OK:
            entry.set_text(self._filechooserdialogs[entry].get_filename())
            self.set_response_sensitive(Gtk.ResponseType.APPLY, True)
        self._filechooserdialogs[entry].hide()
        return True

    def on_entry_changed(self, entry, propname, propobject):
        if propobject.get_property(propname) != entry.get_text():
            self.set_response_sensitive(Gtk.ResponseType.APPLY, True)

    def do_response(self, response):
        if response in (Gtk.ResponseType.OK, Gtk.ResponseType.APPLY):
            if self.credo.subsystems['Files'].rootpath != self.filepath_entry.get_text():
                self.credo.subsystems['Files'].rootpath = self.filepath_entry.get_text()
#             if self.credo.subsystems['Scan'].scanfilename != self.scanfile_entry.get_text():
#                 self.credo.subsystems['Scan'].scanfilename = self.scanfile_entry.get_text()
            self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        if response not in (Gtk.ResponseType.APPLY,):
            self.destroy()
        return True
