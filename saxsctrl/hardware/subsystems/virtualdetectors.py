import logging
import weakref
import ConfigParser
import os

from gi.repository import Gtk
from gi.repository import GObject
from ..virtualpointdetector import VirtualPointDetector, virtualpointdetector_new_from_configparser, VirtualPointDetectorExposure, VirtualPointDetectorGenix, VirtualPointDetectorEpoch, VirtualPointDetectorHeader
from .subsystem import SubSystem, SubSystemError
from ...utils import objwithgui

__all__ = ['SubSystemVirtualDetectors']

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class AddDetectorDialog(Gtk.Dialog):
    _filechooserdialogs = None
    def __init__(self, credo, title='Add detector', parent=None):
        Gtk.Dialog.__init__(self, title, parent,
                            flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                            buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        vb = self.get_content_area()
        self.set_default_response(Gtk.ResponseType.CANCEL)
        self.credo = credo

        tab = Gtk.Table()
        vb.pack_start(tab, False, True, 0)
        self.set_resizable(False)
        row = 0
        
        l = Gtk.Label(label='Detector type:'); l.set_alignment(0, 0.5)
        tab.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL, Gtk.AttachOptions.FILL)
        self.type_entry = Gtk.ComboBoxText()
        for t in VirtualPointDetector.__subclasses__():
            self.type_entry.append_text(t.__name__.replace('VirtualPointDetector', ''))
        self.type_entry.set_active(0)
        self.type_entry.connect('changed', lambda combo: self.on_type_entry_change())
        tab.attach(self.type_entry, 1, 2, row, row + 1)
        row += 1

        self._table = None
        
        self.on_type_entry_change()
        vb.show_all()
    def on_type_entry_change(self):
        if self._table is not None:
            vb = self.get_content_area()
            vb.remove(self._table)
            self._table.destroy()
            del self._table
            del self._detector
        cls = [c for c in VirtualPointDetector.__subclasses__() if c.__name__.replace('VirtualPointDetector', '') == self.type_entry.get_active_text()][0]
        self._detector = cls()
        self._table = self._detector.create_setup_table()
    def get_detector(self):
        if self._table is not None:
            self._table.apply_changes()
            return self._detector

class DetectorTypeSelector(Gtk.Dialog):
    def __init__(self, parent):
        Gtk.Dialog.__init__(self, 'Select detector type to add', parent, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        self._typeselector = Gtk.ComboBoxText()
        self.get_content_area().pack_start(self._typeselector, True, True, 0)
        self.get_content_area().show_all()
        for c in VirtualPointDetector.__subclasses__():
            self._typeselector.append_text(c.__name__.replace('VirtualPointDetector', ''))
        self._typeselector.set_active(0)
    def get_detectorclass(self):
        return [c for c in VirtualPointDetector.__subclasses__() if c.__name__.replace('VirtualPointDetector', '') == self._typeselector.get_active_text()][0]
        

class DetectorListTable(Gtk.Frame):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ())}
    def __init__(self, subsys):
        Gtk.Frame.__init__(self, label='Detectors:')
        self.subsys = subsys
        self.subsys.connect('changed', lambda ss: self._fromsubsys())
        self._detlist = Gtk.ListStore(GObject.TYPE_PYOBJECT,  # vpd object (stored for reference) 
                                      GObject.TYPE_STRING,  # name
                                      GObject.TYPE_STRING,  # type 
                                      GObject.TYPE_DOUBLE,  # scaling
                                      GObject.TYPE_BOOLEAN,  # visible 
                                      GObject.TYPE_STRING)  # args
        self._detview = Gtk.TreeView(self._detlist)
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(hb)
        hb.pack_start(self._detview, True, True, 0)
        self._detview.set_rules_hint(True)
        sel = self._detview.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self._detview.append_column(Gtk.TreeViewColumn('Name', Gtk.CellRendererText(), text=1))
        self._detview.append_column(Gtk.TreeViewColumn('Type', Gtk.CellRendererText(), text=2))
        self._detview.append_column(Gtk.TreeViewColumn('Scaling', Gtk.CellRendererText(), text=3))
        self._detview.append_column(Gtk.TreeViewColumn('Visibility', Gtk.CellRendererToggle(), active=4))
        self._detview.append_column(Gtk.TreeViewColumn('Arguments', Gtk.CellRendererText(), text=5))
        
        vbb = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL)
        hb.pack_start(vbb, False, False, 0)
        b = Gtk.Button(stock=Gtk.STOCK_ADD); vbb.add(b)
        b.connect('clicked', lambda b:self._add())
        b = Gtk.Button(stock=Gtk.STOCK_REMOVE); vbb.add(b)
        b.connect('clicked', lambda b:self._remove())
        b = Gtk.Button(stock=Gtk.STOCK_CLEAR); vbb.add(b)
        b.connect('clicked', lambda b:self._detlist.clear())
        b = Gtk.Button(stock=Gtk.STOCK_EDIT); vbb.add(b)
        b.connect('clicked', lambda b:self._edit())
        b = Gtk.Button(stock=Gtk.STOCK_GOTO_TOP); vbb.add(b)
        b.connect('clicked', lambda b:self._move_top())
        b = Gtk.Button(stock=Gtk.STOCK_GO_UP); vbb.add(b)
        b.connect('clicked', lambda b:self._move_up())
        b = Gtk.Button(stock=Gtk.STOCK_GO_DOWN); vbb.add(b)
        b.connect('clicked', lambda b:self._move_down())
        b = Gtk.Button(stock=Gtk.STOCK_GOTO_BOTTOM); vbb.add(b)
        b.connect('clicked', lambda b:self._move_bottom())
        self.show_all()
        
    def _update_model(self):
        for row in self._detlist:
            row[1] = row[0].name
            row[2] = row[0].__class__.__name__.replace('VirtualPointDetector', '')
            row[3] = row[0].scaler
            row[4] = row[0].visible
            row[5] = str(row[0])
    def _fromsubsys(self):
        self._detlist.clear()
        for d in self.subsys:
            self._detlist.append([d, '', '', 0.0, False, ''])
        self._update_model()
    def _tosubsys(self):
        self.subsys.clear()
        for row in self._detlist:
            self.subsys.add(row[0], noemit=True)
    def _add(self):
        dia = DetectorTypeSelector(self.get_toplevel())
        if dia.run() == Gtk.ResponseType.OK:
            self._detlist.prepend([dia.get_detectorclass()('--please name this detector--'), '', '', 0.0, False, ''])
            self._update_model()
        dia.destroy()
        del dia
        self._detview.get_selection().select_iter(self._detlist.get_iter_first())
        self._edit()
    def _remove(self):
        model, it = self._detview.get_selection().get_selected()
        if it is not None:
            model.remove(it)
    def _edit(self):
        model, it = self._detview.get_selection().get_selected()
        if it is not None:
            dia = model[it][0].create_setup_dialog(parent=self.get_toplevel(), flags=Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL)
            while dia.run() in (Gtk.ResponseType.APPLY, Gtk.ResponseType.REJECT):
                pass
            dia.destroy()
            del dia
        self._update_model()
    def _move_top(self):
        model, it = self._detview.get_selection().get_selected()
        if it is not None:
            model.move_after(it, None)
    def _move_up(self):
        model, it = self._detview.get_selection().get_selected()
        if it is not None:
            prev = model.iter_previous(it)
            if prev is not None:
                model.move_before(it, prev)
    def _move_down(self):
        model, it = self._detview.get_selection().get_selected()
        if it is not None:
            next = model.iter_next(it)
            if next is not None:
                model.move_after(it, next)
    def _move_bottom(self):
        model, it = self._detview.get_selection().get_selected()
        if it is not None:
            model.move_before(it, None)

class VDSetupDialog(objwithgui.ObjSetupDialog):
    def __init__(self, *args, **kwargs):
        objwithgui.ObjSetupDialog.__init__(self, *args, **kwargs)
        self.add_button(Gtk.STOCK_SAVE, 10)
        self.add_button(Gtk.STOCK_OPEN, 11)
    def do_response(self, respid):
        if respid == 10:
            self._tab.objwithgui.save()
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, 'Detectors saved to file ' + self._tab.objwithgui.configfile)
            md.set_title('Information')
            md.run()
            md.destroy()
            del md
            
        elif respid == 11:
            self._tab.objwithgui.load()
            md = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, 'Detectors loaded from file ' + self._tab.objwithgui.configfile)
            md.set_title('Information')
            md.run()
            md.destroy()
            del md
        else:
            return objwithgui.ObjSetupDialog.do_response(self, respid)

class SubSystemVirtualDetectors(SubSystem):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'notify':'override',
                   }
    _oldconfigfile = None
    def __init__(self, credo):
        self._list = []
        SubSystem.__init__(self, credo)
        self.load()
    def add(self, vd, noemit=False):
        if not [d for d in self._list if d == vd]:
            self._list.append(vd)
            if not noemit:
                self.emit('changed')
            return True
        else:
            logger.warning('Not adding duplicate detector: %s' % str(vd))
            return False
    def remove(self, vd):
        try:
            todelete = [d for d in self._list if d == vd][0]
            self._list.remove(todelete)
        except IndexError:
            raise ValueError('Virtual detector %s not in list!' % str(vd))
        else:
            self.emit('changed')
    def clear(self):
        self._list = []
    def load(self, filename=None, clear=True):
        if filename is None:
            filename = self.configfile
        cp = ConfigParser.ConfigParser()
        cp.read(filename)
        if clear:
            self.clear()
        changed = False
        for vpdname in [sec for sec in cp.sections() if sec.startswith('VPD_')]:
            vpd = virtualpointdetector_new_from_configparser(vpdname[4:], cp)
            changed |= self.add(vpd)
        if changed:
            self.emit('changed')
            if self.configfile != filename:
                self.configfile = filename
    def save(self, filename=None):
        if filename is None:
            filename = self.configfile
        cp = ConfigParser.ConfigParser()
        for vpd in self._list:
            vpd.savestate(cp)
        with open(filename, 'wt') as f:
            cp.write(f)
    def readout_all(self, exposure, genix):
        dic = {}
        for vd in self._list:
            if isinstance(vd, VirtualPointDetectorExposure):
                dic[vd.name] = vd.readout(exposure)
            elif isinstance(vd, VirtualPointDetectorEpoch):
                dic[vd.name] = vd.readout()
            elif isinstance(vd, VirtualPointDetectorGenix):
                dic[vd.name] = vd.readout(genix)
            elif isinstance(vd, VirtualPointDetectorHeader):
                dic[vd.name] = vd.readout(exposure.header)
        return dic
    def __iter__(self):
        return iter(self._list)
    def do_notify(self, prop):
        if prop.name == 'configfile':
            if not os.path.isabs(self.configfile):
                self.configfile = os.path.join(self.credo().subsystems['Files'].configpath, self.configfile)
            else:
                self.load()
    def create_setup_table(self, homogeneous=False):
        tab = SubSystem.create_setup_table(self, homogeneous)
        nrows, ncols = tab.get_size()
        _detlist = DetectorListTable(self)
        tab.attach(_detlist, 0, ncols, nrows, nrows + 1)
        tab.connect('apply', lambda t: _detlist._tosubsys())
        tab.connect('revert', lambda t:_detlist._fromsubsys())
        _detlist._fromsubsys()
        return tab
    def create_setup_dialog(self, title=None, parent=None, flags=0):
        if title is None:
            title = 'Set up Virtual Detectors'
        return VDSetupDialog(self, title, parent, flags)
