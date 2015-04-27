# encoding: utf-8

from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GLib
from .widgets import ToolDialog
from ..hardware.subsystems.datareduction import DataReductionError
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DataReduction(ToolDialog):

    def __init__(self, credo, title='Data reduction'):
        ToolDialog.__init__(self, credo, title, buttons=(
            'Execute', Gtk.ResponseType.APPLY, 'Close',
            Gtk.ResponseType.CLOSE, 'Refresh', Gtk.ResponseType.ACCEPT))
        vb = self.get_content_area()
        f = Gtk.Frame(label='Filesystem parameters')
        vb.pack_start(f, False, False, 0)
        grid = Gtk.Grid()
        f.add(grid)
        row = 0

        l = Gtk.Label(label='Starting FSN:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._startfsn_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(0, 0, 1e6, 1, 10), digits=0)
        grid.attach(self._startfsn_spin, 1, row, 1, 1)
        row += 1

        l = Gtk.Label(label='Ending FSN:')
        l.set_halign(Gtk.Align.START)
        l.set_valign(Gtk.Align.CENTER)
        grid.attach(l, 0, row, 1, 1)
        self._endfsn_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(0, 0, 1e6, 1, 10), digits=0)
        grid.attach(self._endfsn_spin, 1, row, 1, 1)
        row += 1

        b = Gtk.Button(label='Load headers')
        grid.attach(b, 2, 0, 1, row)
        b.connect('clicked', lambda btn: self.reload_list())

        self._headerlist = Gtk.ListStore(GObject.TYPE_PYOBJECT,  # the header instance
                                         # spinner active
                                         GObject.TYPE_BOOLEAN,
                                         GObject.TYPE_INT,  # FSN
                                         GObject.TYPE_STRING,  # title
                                         GObject.TYPE_STRING,  # meastime
                                         GObject.TYPE_STRING,  # energy
                                         GObject.TYPE_STRING,  # distance
                                         # beam position X
                                         GObject.TYPE_STRING,
                                         # beam position y
                                         GObject.TYPE_STRING,
                                         GObject.TYPE_STRING,  # transmission
                                         GObject.TYPE_STRING,  # thickness
                                         GObject.TYPE_UINT,  # spinner pulse
                                         )
        self._overlay = Gtk.Overlay()
        vb.pack_start(self._overlay, True, True, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(700, 300)

        self._overlay.add(sw)
        self._headerview = Gtk.TreeView(self._headerlist)
        sw.add(self._headerview)
        self._headerview.set_rules_hint(True)
        self._headerview.set_headers_visible(True)
        self._headerview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        cr = Gtk.CellRendererSpinner()
        self._headerview.append_column(
            Gtk.TreeViewColumn('', cr, active=1, pulse=11))
        self._headerview.append_column(
            Gtk.TreeViewColumn('FSN', Gtk.CellRendererText(), text=2))
        self._headerview.append_column(
            Gtk.TreeViewColumn('Title', Gtk.CellRendererText(), text=3))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(
            path, newtext, colnum, fieldname), 4, 'MeasTime')
        self._headerview.append_column(
            Gtk.TreeViewColumn('Counting time (sec)', cr, text=4))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(
            path, newtext, colnum, fieldname), 5, 'Temperature')
        self._headerview.append_column(
            Gtk.TreeViewColumn(u'Temperature (°C)', cr, text=5))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(
            path, newtext, colnum, fieldname), 6, 'DistCalibrated')
        self._headerview.append_column(
            Gtk.TreeViewColumn('Distance (mm)', Gtk.CellRendererText(), text=6))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(
            path, newtext, colnum, fieldname), 7, 'BeamPosX')
        self._headerview.append_column(
            Gtk.TreeViewColumn('Beam X (vert)', Gtk.CellRendererText(), text=7))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(
            path, newtext, colnum, fieldname), 8, 'BeamPosY')
        self._headerview.append_column(
            Gtk.TreeViewColumn('Beam Y (horiz)', Gtk.CellRendererText(), text=8))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(
            path, newtext, colnum, fieldname), 9, 'Transm')
        self._headerview.append_column(
            Gtk.TreeViewColumn('Transmission', Gtk.CellRendererText(), text=9))
        cr = Gtk.CellRendererText()
        cr.set_property('editable', True)
        cr.connect('edited', lambda renderer, path, newtext, colnum, fieldname: self._cell_edited(
            path, newtext, colnum, fieldname), 10, 'Thickness')
        self._headerview.append_column(
            Gtk.TreeViewColumn('Thickness (cm)', Gtk.CellRendererText(), text=10))
        self._headerview.grab_focus()

        self._resultsfrm = Gtk.Frame(label='Data reduction running...')
        self._resultsfrm.set_no_show_all(True)
        vb.pack_start(self._resultsfrm, False, False, 0)

        self._resultsprogress = Gtk.ProgressBar(
            orientation=Gtk.Orientation.HORIZONTAL)
        self._resultsfrm.add(self._resultsprogress)
        self._resultsprogress.show()

    def _reload_headers(self):
        logger.debug('Reloading headers')
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        spinner = Gtk.Spinner()
        vb.pack_start(spinner, True, True, 0)
        l = Gtk.Label(label='Reloading, please wait...')
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
        self.reload_list(callback=_reloading_spinner)
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
            md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT |
                                   Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Invalid number: ' + newtext)
            md.run()
            md.destroy()
            del md
            return False
        self._headerlist[path][0][fieldname] = float(newtext)
        self.refresh_view(self._headerlist[path])
        return True

    def _set_line_active(self, path):
        self._headerlist[path][1] ^= 1

    def reload_list(self, callback=None):
        self._headerlist.clear()
        ssdr = self.credo.subsystems['DataReduction']
        for fsn in range(self._startfsn_spin.get_value_as_int(),
                         self._endfsn_spin.get_value_as_int() + 1):
            try:
                self._headerlist.append(
                    [ssdr.load_header(fsn), False, 0, '', '', '', '', '', '', '', '', 0])
            except IOError:
                continue

        self.refresh_view()

    def refresh_view(self, row=None):
        if row is None:
            rows = iter(self._headerlist)
        else:
            rows = [row]
        for row in rows:
            for i, field, formatstring in [(2, 'FSN', None), (3, 'Title', '%s'), (4, 'MeasTime', '%.2f'), (5, 'Temperature', '%.2f'),
                                           (6, 'DistCalibrated', '%.3f'), (7,
                                                                           'BeamPosX', '%.3f'), (8, 'BeamPosY', '%.3f'),
                                           (9, 'Transm', '%.4f'), (10, 'Thickness', '%.4f')]:
                try:
                    if formatstring is None:
                        row[i] = row[0][field]
                    else:
                        row[i] = formatstring % (row[0][field])
                except (KeyError, TypeError):
                    row[i] = '--not defined--'

    def _on_message(self, datareduction, fsn, text):
        self._resultsprogress.set_text('#%d: %s' % (fsn, text))
        return True

    def do_response(self, response):
        if response == Gtk.ResponseType.ACCEPT:
            self._reload_headers()
            return
        elif response == Gtk.ResponseType.APPLY:
            if self.get_widget_for_response(Gtk.ResponseType.APPLY).get_label() == 'Stop':
                self.credo.subsystems['DataReduction'].stop()
                return True
            selectedpath = self._headerview.get_selection().get_selected_rows()[
                1]
            selected = [self._headerlist[path][0]['FSN']
                        for path in selectedpath]
            if not selected:
                md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                                       Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'No measurement selected for data reduction!')
                md.run()
                md.destroy()
                del md
                return True
            try:
                self._pulser_handle = GLib.timeout_add(400, self._pulser)
                self._headerview.set_sensitive(False)
                self._resultsfrm.show_all()
                self._resultsfrm.show_now()
                self._reducer_conn = [self.credo.subsystems['DataReduction'].connect('message', self._on_message),
                                      self.credo.subsystems['DataReduction'].connect(
                                          'idle', self._on_idle),
                                      self.credo.subsystems['DataReduction'].connect('done', self._on_done)]
                self._todo_number = len(selected)
                self._done_number = 0
                self._resultsprogress.set_fraction(0)
                for sel in selected:
                    self.credo.subsystems['DataReduction'].reduce(sel)
#                for path in self._headerview.get_selection().get_selected_rows()[1]:
#                    self._headerlist[path][1] = True
                self.get_widget_for_response(
                    Gtk.ResponseType.APPLY).set_label('Stop')
                logger.debug('Started data reduction sequence.')
            except DataReductionError as dre:
                md = Gtk.MessageDialog(self.get_toplevel(), Gtk.DialogFlags.DESTROY_WITH_PARENT |
                                       Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, 'Error during data reduction!')
                md.format_secondary_text(str(dre))
                md.run()
                md.destroy()
                del md
        else:
            return ToolDialog.do_response(self, response)
        return True

    def _on_done(self, datareduction, fsn, header):
        logger.info('Data reduction of FSN #%d (%s) done.' %
                    (fsn, str(header)))
        for row in [x for x in self._headerlist if x[0]['FSN'] == fsn]:
            row[1] = False
        self._done_number += 1
        self._resultsprogress.set_fraction(
            self._done_number * 1.0 / self._todo_number)

    def _pulser(self):
        for row in self._headerlist:
            if row[1]:
                row[11] += 1
        return True

    def _on_idle(self, datareduction):
        for c in self._reducer_conn:
            self.credo.subsystems['DataReduction'].disconnect(c)
        self._reducer_conn = []
        self._resultsfrm.hide()
        GLib.source_remove(self._pulser_handle)
        self._pulser_handle = None
        self._headerview.set_sensitive(True)
        self.get_widget_for_response(
            Gtk.ResponseType.APPLY).set_label('Execute')
        logger.info('Data reduction sequence finished.')
