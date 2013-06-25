from gi.repository import Gtk
from gi.repository import GObject
import os
import re
import dateutil.parser
import sastool
import numpy as np
import matplotlib.pyplot as plt
from .moviemaker import MovieMaker
from . import scangraph
from ..fileformats.scan import Scan
from .spec_filechoosers import FileEntryWithButton
    
class ScanViewer(Gtk.Dialog):
    def __init__(self, credo, title='Scan viewer', parent=None, flags=0, buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons)
        self.set_default_response(Gtk.ResponseType.CLOSE)
        self.credo = credo
        vb = self.get_content_area()
        self.entrytable = Gtk.Table()
        vb.pack_start(self.entrytable, False, True, 0)
        row = 0
        
        l = Gtk.Label(label='Scan file:'); l.set_alignment(0, 0.5)
        self.entrytable.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.scanfile_entry = FileEntryWithButton()
        self.scanfile_entry.set_filename(self.credo.subsystems['Scan'].scanfilename)
        self.entrytable.attach(self.scanfile_entry, 1, 2, row, row + 1)
        b = Gtk.Button(stock=Gtk.STOCK_REFRESH)
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
        # Columns are: Scan number, Scan type, Sample name, Exit status, Number of points
        self.scan_liststore = Gtk.ListStore(GObject.TYPE_INT, GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_INT)
        self.scan_treeview = Gtk.TreeView(self.scan_liststore)
        sw.add(self.scan_treeview)
        self.scan_treeview.set_headers_visible(True)
        self.scan_treeview.set_rules_hint(True)
        self.scan_treeview.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
        cellrenderer = Gtk.CellRendererText()
        self.scan_treeview.append_column(Gtk.TreeViewColumn('FSN', cellrenderer, text=0))
        cellrenderer = Gtk.CellRendererText()
        self.scan_treeview.append_column(Gtk.TreeViewColumn('Device', cellrenderer, text=1))
        cellrenderer = Gtk.CellRendererText()
        self.scan_treeview.append_column(Gtk.TreeViewColumn('Sample', cellrenderer, text=2))
        cellrenderer = Gtk.CellRendererText()
        self.scan_treeview.append_column(Gtk.TreeViewColumn('Command', cellrenderer, text=3))
        cellrenderer = Gtk.CellRendererText()
        self.scan_treeview.append_column(Gtk.TreeViewColumn('# of points', cellrenderer, text=4))
        self.scan_treeview.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
        # self.scan_treeview.connect('row-activated', self.on_row_activated)
        self.scan_treeview.get_selection().connect('changed', self.on_scan_selection_changed)
        sw.set_size_request(-1, 300)
        
#         f = Gtk.Frame(label='Columns in scan:')
#         vp.add2(f)
#         sw = Gtk.ScrolledWindow()
#         sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
#         f.add(sw)
#         self.cols_liststore = Gtk.ListStore(GObject.TYPE_INT, GObject.TYPE_STRING, GObject.TYPE_BOOLEAN, GObject.TYPE_BOOLEAN, GObject.TYPE_BOOLEAN)
#         self.cols_treeview = Gtk.TreeView(self.cols_liststore)
#         sw.add(self.cols_treeview)
#         self.cols_treeview.set_headers_visible(True)
#         self.cols_treeview.set_rules_hint(True)
#         self.cols_treeview.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
#         sw.set_size_request(-1, 200)
#         cr = Gtk.CellRendererText()
#         self.cols_treeview.append_column(Gtk.TreeViewColumn('Index', cr, text=0))
#         cr = Gtk.CellRendererText()
#         self.cols_treeview.append_column(Gtk.TreeViewColumn('Name', cr, text=1))
#         cr = Gtk.CellRendererToggle()
#         cr.set_radio(True)
#         cr.set_activatable(True)
#         cr.connect('toggled', self.on_cellrenderer_toggled, 'X', 2)
#         self.cols_treeview.append_column(Gtk.TreeViewColumn('X', cr, active=2))
#         cr = Gtk.CellRendererToggle()
#         cr.set_radio(True)
#         cr.set_activatable(True)
#         cr.connect('toggled', self.on_cellrenderer_toggled, 'Y', 3)
#         self.cols_treeview.append_column(Gtk.TreeViewColumn('Y', cr, active=3))
#         cr = Gtk.CellRendererToggle()
#         # cr.set_radio()
#         cr.set_activatable(True)
#         cr.connect('toggled', self.on_cellrenderer_toggled, 'Norming', 4)
#         self.cols_treeview.append_column(Gtk.TreeViewColumn('Norming', cr, active=4))
        hbb = Gtk.HButtonBox()
        vb.pack_start(hbb, False, True, 0)
        b = Gtk.Button('Plot selected curve')
        b.connect('clicked', self.on_plot_button)
        hbb.add(b)
        b = Gtk.Button('Make movie')
        b.connect('clicked', self.on_movie_button)
        hbb.add(b)
        
        vb.show_all()
        self.reload_list()
        self.connect('response', self.on_response)
    def on_scan_selection_changed(self, treeselection):
#         self.cols_liststore.clear()
#         model, paths = treeselection.get_selected_rows()
#         if not paths:
#             # no selection
#             return True
#         row = self.scan_liststore[paths[0]]
#         scan = self.spec[row[0]]
#         for i, c in enumerate(scan.columns()):
#             self.cols_liststore.append((i, c, False, False, False))
#         if len(self.cols_liststore) > 0:
#             self.cols_liststore[0][2] = True
#         if len(self.cols_liststore) > 1:
#             self.cols_liststore[1][3] = True
        return True
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
            self.scan_liststore.append((scan.fsn, scan.columns()[0], scan.comment, scan.command, len(scan)))
            
    def on_plot_button(self, button):
        model, paths = self.scan_treeview.get_selection().get_selected_rows()
        row = model[paths[0]]
        scan = self.spec[row[0]]
#         Xcol = [i for i, c in enumerate(self.cols_liststore) if c[2]][0]
#         Ycol = [i for i, c in enumerate(self.cols_liststore) if c[3]][0]
#         Ncols = [i for i, c in enumerate(self.cols_liststore) if c[4]]
#         x = scan.get_column(Xcol)
#         y = scan.get_column(Ycol)
#         if Ncols:
#             y = y / scan.get_column(Ncols[0])
        
        sg = scangraph.ScanGraph(scan, 'Scan #' + str(scan.fsn) + ' -- ' + str(scan.comment))
        # sg.datacols = scan.columns()[Ycol]
        sg.redraw_scan()
        sg.show_all()
    def on_response(self, dialog, respid):
        self.hide()
        return True

