from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Pango
import sastool
from .moviemaker import MovieMaker
from . import scangraph
from sasgui.fileentry import FileEntryWithButton
from .widgets import ToolDialog
import datetime

class ScanViewer(ToolDialog):
    def __init__(self, credo, title='Scan viewer'):
        ToolDialog.__init__(self, credo, title)
        vb = self.get_content_area()
        self.entrytable = Gtk.Table()
        vb.pack_start(self.entrytable, False, True, 0)
        row = 0

        l = Gtk.Label(label='Scan file:'); l.set_halign(Gtk.Align.START); l.set_valign(Gtk.Align.CENTER)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.scanfile_entry = FileEntryWithButton()
        self.scanfile_entry.set_filename(self.credo.subsystems['Files'].scanfilename)
        self.entrytable.attach(self.scanfile_entry, 1, 2, row, row + 1)
        b = Gtk.Button(label='Refresh')
        self.entrytable.attach(b, 2, 3, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        b.connect('clicked', lambda b: self.reload_list())
        vp = Gtk.VPaned()
        vb.pack_start(vp, True, True, 0)
        f = Gtk.Frame(label='Scans:')
        vp.add1(f)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        f.add(sw)
        # the liststore containing the information of the scans.
        # Columns are: Scan number, Scan type, Sample name, Exit status, Number of points, date
        self.scan_liststore = Gtk.ListStore(GObject.TYPE_INT, GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_INT, GObject.TYPE_STRING)
        self.scan_treeview = Gtk.TreeView(self.scan_liststore)
        sw.add(self.scan_treeview)
        self.scan_treeview.set_headers_visible(True)
        self.scan_treeview.set_rules_hint(True)
        self.scan_treeview.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
        cellrenderer = Gtk.CellRendererText()
        tvc = Gtk.TreeViewColumn('FSN', cellrenderer, text=0)
        tvc.set_resizable(True)
        tvc.set_expand(False)
        self.scan_treeview.append_column(tvc)
        tvc = Gtk.TreeViewColumn('Date', cellrenderer, text=5)
        tvc.set_resizable(True)
        tvc.set_expand(False)
        self.scan_treeview.append_column(tvc)
        cellrenderer = Gtk.CellRendererText()
        cellrenderer.set_property('ellipsize', Pango.EllipsizeMode.END)
        tvc = Gtk.TreeViewColumn('Device', cellrenderer, text=1)
        tvc.set_resizable(True)
        tvc.set_expand(False)
        self.scan_treeview.append_column(tvc)
        cellrenderer = Gtk.CellRendererText()
        cellrenderer.set_property('ellipsize', Pango.EllipsizeMode.END)
        tvc = Gtk.TreeViewColumn('Sample', cellrenderer, text=2)
        tvc.set_resizable(True)
        tvc.set_expand(False)
        self.scan_treeview.append_column(tvc)
        cellrenderer = Gtk.CellRendererText()
        tvc = Gtk.TreeViewColumn('Command', cellrenderer, text=3)
        tvc.set_resizable(True)
        tvc.set_expand(True)
        cellrenderer.set_property('ellipsize', Pango.EllipsizeMode.END)
        self.scan_treeview.append_column(tvc)
        cellrenderer = Gtk.CellRendererText()
        tvc = Gtk.TreeViewColumn('# of points', cellrenderer, text=4)
        tvc.set_expand(False)
        tvc.set_resizable(True)
        self.scan_treeview.append_column(tvc)
        self.scan_treeview.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
        self.scan_treeview.connect('row-activated', lambda tv, path, column: self._plot())
        sw.set_size_request(-1, 300)
        hbb = Gtk.HButtonBox()
        vb.pack_start(hbb, False, True, 0)
        b = Gtk.Button('Plot selected curve')
        b.connect('clicked', lambda b:self._plot())
        hbb.add(b)
        b = Gtk.Button('Make movie')
        b.connect('clicked', self.on_movie_button)
        hbb.add(b)

        vb.show_all()
        self.reload_list()
    def on_cellrenderer_toggled(self, crtoggle, path, what, colidx):
        if what == 'X' or what == 'Y':
            for l in self.cols_liststore:
                l[colidx] = False
            self.cols_liststore[path][colidx] = True
        elif what == 'Norming':
            prevval = self.cols_liststore[path][colidx]
            for l in self.cols_liststore:
                l[colidx] = False
            self.cols_liststore[path][colidx] = not prevval
        return True
    def on_movie_button(self, button):
        model, paths = self.scan_treeview.get_selection().get_selected_rows()
        row = model[paths[0]]
        scan = self.spec[row[0]]
        mmd = MovieMaker(self.credo, scan, parent=self, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL)
        mmd.run()
        mmd.destroy()
        return True
    def reload_list(self):
        self.scan_liststore.clear()
        self.spec = sastool.classes.SASScanStore(self.scanfile_entry.get_filename())
        for scan in [s for s in self.spec if len(s)]:
            self.scan_liststore.append((scan.fsn, scan.columns()[0], scan.comment, scan.command, len(scan), datetime.datetime.fromtimestamp(scan.timestamp).strftime('%F %R')))

    def _plot(self):
        model, paths = self.scan_treeview.get_selection().get_selected_rows()
        row = model[paths[0]]
        scan = self.spec[row[0]]

        if isinstance(scan._N, tuple):
            sg = scangraph.ImagingGraph(scan, 'Imaging #' + str(scan.fsn) + ' -- ' + str(scan.comment))
        else:
            sg = scangraph.ScanGraph(scan, self.credo, 'Scan #' + str(scan.fsn) + ' -- ' + str(scan.comment))
        sg.redraw_scan()
        sg.show_all()

