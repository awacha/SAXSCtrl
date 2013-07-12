from gi.repository import Gtk
from gi.repository import GObject
from .widgets import ToolDialog
from .spec_filechoosers import FileEntryWithButton
from ..hardware.subsystems.datareduction import DataReductionError
import sastool
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
DEFAULT_PREFIX = 'crd'

class DataReduction(ToolDialog):
    def __init__(self, credo, title='Data reduction'):
        ToolDialog.__init__(self, credo, title, buttons=(Gtk.STOCK_EXECUTE, Gtk.ResponseType.APPLY, Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE, Gtk.STOCK_REFRESH, Gtk.ResponseType.ACCEPT))
        vb = self.get_content_area()
        f = Gtk.Frame(label='Filesystem parameters')
        vb.pack_start(f, False, False, 0)
        tab = Gtk.Table()
        f.add(tab)
        row = 0
        
        self._raw_radio = Gtk.RadioButton(label='Load raw data')
        tab.attach(self._raw_radio, 0, 2, row, row + 1)
        row += 1
        self._reduced_radio = Gtk.RadioButton(label='Load reduced data')
        self._reduced_radio.join_group(self._raw_radio)
        self._raw_radio.set_active(True)
        tab.attach(self._reduced_radio, 0, 2, row, row + 1)
        row += 1

        self._headerlist = Gtk.ListStore(GObject.TYPE_PYOBJECT,  # the header instance 
                                         GObject.TYPE_BOOLEAN,  # selector
                                         GObject.TYPE_INT,  # FSN
                                         GObject.TYPE_STRING,  # title
                                         GObject.TYPE_STRING,  # meastime
                                         GObject.TYPE_STRING,  # energy
                                         GObject.TYPE_STRING,  # distance
                                         GObject.TYPE_STRING,  # beam position X
                                         GObject.TYPE_STRING,  # beam position y
                                         GObject.TYPE_STRING,  # transmission
                                         GObject.TYPE_STRING,  # thickness 
                                         )
        self._overlay = Gtk.Overlay()
        vb.pack_start(self._overlay, True, True, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(300, 300)
        self._overlay.add(sw)
        self._headerview = Gtk.TreeView(self._headerlist)
        sw.add(self._headerview)
        self._headerview.set_rules_hint(True)
        self._headerview.set_headers_visible(True)
        self._headerview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
#         cr = Gtk.CellRendererToggle()
#         cr.set_radio(False)
#         cr.connect('toggled', lambda renderer, path: self._set_line_active(path))
#         cr.set_property('activatable', True)
#         self._headerview.append_column(Gtk.TreeViewColumn('', cr, active=1))
        self._headerview.append_column(Gtk.TreeViewColumn('FSN', Gtk.CellRendererText(), text=2))
        self._headerview.append_column(Gtk.TreeViewColumn('Title', Gtk.CellRendererText(), text=3))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(path, newtext, colnum, fieldname), 4, 'MeasTime')
        self._headerview.append_column(Gtk.TreeViewColumn('Counting time (sec)', cr, text=4))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(path, newtext, colnum, fieldname), 5, 'EnergyCalibrated')
        self._headerview.append_column(Gtk.TreeViewColumn('Energy (eV)', cr, text=5))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(path, newtext, colnum, fieldname), 6, 'DistCalibrated')
        self._headerview.append_column(Gtk.TreeViewColumn('Distance (mm)', Gtk.CellRendererText(), text=6))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(path, newtext, colnum, fieldname), 7, 'BeamPosX')
        self._headerview.append_column(Gtk.TreeViewColumn('Beam X (vert)', Gtk.CellRendererText(), text=7))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(path, newtext, colnum, fieldname), 8, 'BeamPosY')
        self._headerview.append_column(Gtk.TreeViewColumn('Beam Y (horiz)', Gtk.CellRendererText(), text=8))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(path, newtext, colnum, fieldname), 9, 'Transm')
        self._headerview.append_column(Gtk.TreeViewColumn('Transmission', Gtk.CellRendererText(), text=9))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(path, newtext, colnum, fieldname), 10, 'Thickness')
        self._headerview.append_column(Gtk.TreeViewColumn('Thickness (cm)', Gtk.CellRendererText(), text=10))
        self._headerview.grab_focus()
        GObject.idle_add(lambda :self._reload_beamtimes() and False)
        
        self._resultsfrm = Gtk.Frame(label='Data reduction messages')
        self._resultsfrm.set_no_show_all(True)
        vb.pack_start(self._resultsfrm, False, False, 0)
        tab = Gtk.Table()
        self._resultsfrm.add(tab)
        row = 0
        l = Gtk.Label('FSN currently processed:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._currfsn_label = Gtk.Label('N/A'); self._currfsn_label.set_alignment(0, 0.5)
        tab.attach(self._currfsn_label, 1, 2, row, row + 1)
        row += 1
        
        l = Gtk.Label('Message:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
        self._currmessage_label = Gtk.Label('N/A'); self._currmessage_label.set_alignment(0, 0.5)
        tab.attach(self._currmessage_label, 1, 2, row, row + 1)
        row += 1
        tab.show_all()
        
    def _reload_beamtimes(self):
        logger.debug('Reloading beamtimes')
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        spinner = Gtk.Spinner()
        vb.pack_start(spinner, True, True, 0)
        l = Gtk.Label('Reloading, please wait...')
        vb.pack_start(l, False, False, 10)
        vb.set_property('halign', Gtk.Align.CENTER)
        vb.set_property('valign', Gtk.Align.CENTER)
        self._overlay.add_overlay(vb)
        self._headerview.set_sensitive(False)
        vb.show_all()
        vb.show_now()
        spinner.set_size_request(100, 100)
        spinner.start()
        def _reloading_spinner():
            i = 0
            while (Gtk.events_pending() and i < 20):
                i += 1
                Gtk.main_iteration()
        self.credo.subsystems['DataReduction'].beamtimeraw.callbackfunc = _reloading_spinner
        self.credo.subsystems['DataReduction'].beamtimeraw.refresh_cache()
        self.credo.subsystems['DataReduction'].beamtimeraw.callbackfunc = None
        self.credo.subsystems['DataReduction'].beamtimereduced.callbackfunc = _reloading_spinner
        self.credo.subsystems['DataReduction'].beamtimereduced.refresh_cache()
        self.credo.subsystems['DataReduction'].beamtimereduced.callbackfunc = None
        self.reload_list()
        spinner.stop()
        self._overlay.remove(vb)
        spinner.destroy()
        l.destroy()
        vb.destroy()
        self._headerview.set_sensitive(True)
    def _cell_edited(self, path, newtext, colnum, fieldname):
        try:
            float(newtext)
        except ValueError:
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Invalid number: ' + newtext)
            md.run()
            md.destroy()
            del md
            return False
        self._headerlist[path][0][fieldname] = float(newtext)
        self.refresh_view(self._headerlist[path])
        return True
    def _set_line_active(self, path):
        self._headerlist[path][1] ^= 1
    def reload_list(self):
        self._headerlist.clear()
        if self._raw_radio.get_active():
            bt = self.credo.subsystems['DataReduction'].beamtimeraw
        else:
            bt = self.credo.subsystems['DataReduction'].beamtimereduced
        for h in bt:
            self._headerlist.append([h, False, 0, '', '', '', '', '', '', '', ''])
        
        self.refresh_view()
    def refresh_view(self, row=None):
        if row is None:
            rows = iter(self._headerlist)
        else:
            rows = [row]
        for row in rows:
            for i, field, formatstring in [(2, 'FSN', None), (3, 'Title', '%s'), (4, 'MeasTime', '%.2f'), (5, 'EnergyCalibrated', '%.2f'),
                                           (6, 'DistCalibrated', '%.3f'), (7, 'BeamPosX', '%.3f'), (8, 'BeamPosY', '%.3f'),
                                           (9, 'Transm', '%.4f'), (10, 'Thickness', '%.4f')]:
                try:
                    if formatstring is None:
                        row[i] = row[0][field]
                    else:
                        row[i] = formatstring % (row[0][field])
                except KeyError:
                    row[i] = '--not defined--'
    def _on_message(self, datareduction, fsn, text):
        self._currfsn_label.set_text(str(fsn))
        self._currmessage_label.set_text(text)
        for i in range(100):
            if not Gtk.events_pending():
                break
            Gtk.main_iteration()
        return True
    def do_response(self, response):
        if response == Gtk.ResponseType.ACCEPT:
            self._reload_beamtimes()
            return
        elif response == Gtk.ResponseType.APPLY:
            selected = [self._headerlist[path][0] for path in self._headerview.get_selection().get_selected_rows()[1]]
            if not selected:
                md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'No measurement selected for data reduction!')
                md.run()
                md.destroy()
                del md
                return False
            try:
                _conn = self.credo.subsystems['DataReduction'].connect('message', self._on_message)
                self._resultsfrm.show_all()
                self._resultsfrm.show_now()
                for sel in selected:
                    self.credo.subsystems['DataReduction'].execute(self.credo.subsystems['DataReduction'].beamtimeraw.load_exposure(sel))
            except DataReductionError as dre:
                md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Error during data reduction!')
                md.format_secondary_text(dre.message)
                md.run()
                md.destroy()
                del md
            finally:
                self.credo.subsystems['DataReduction'].disconnect(_conn)
                self._resultsfrm.hide()
        else:
            ToolDialog.do_response(self, response)
