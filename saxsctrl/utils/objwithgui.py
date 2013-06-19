from gi.repository import GObject
from gi.repository import Gtk
from .fileentry import FileEntryWithButton
import logging

logger = logging.getLogger(__name__)

class OWG_Param_Type(object):
    Integer = 'int'
    Float = 'float'
    Bool = 'bool'
    String = 'string'
    Folder = 'folder'
    File = 'file'
    
class OWG_Hint_Type(object):
    Digits = 'digits'
    OrderPriority = 'orderpriority'

class ObjSetupDialog(Gtk.Dialog):
    __gsignals__ = {'response':'override'}
    def __init__(self, objwithgui, title, parent=None, flags=0):
        Gtk.Dialog.__init__(self, title, parent, flags, buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_REFRESH, Gtk.ResponseType.REJECT))
        self._tab = objwithgui.create_setup_table()
        vb = self.get_content_area()
        vb.pack_start(self._tab, True, True, 0)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        self._tab.connect('changed', lambda t, parname:self.set_response_sensitive(Gtk.ResponseType.APPLY, True))
        self._tab.connect('apply', lambda t:self.set_response_sensitive(Gtk.ResponseType.APPLY, False))
        self._tab.connect('revert', lambda t:self.set_response_sensitive(Gtk.ResponseType.APPLY, False))
        vb.show_all()
    def do_response(self, respid):
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            self._tab.apply_changes()
        if respid in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.REJECT):
            self._tab.revert_changes()
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.REJECT):
            self.stop_emission('response')
    

class ObjSetupTable(Gtk.Table):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'apply':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'revert':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    }
    def __init__(self, objwithgui, rows=0, columns=0, homogeneous=False):
        Gtk.Table.__init__(self, rows, columns, homogeneous)
        self.objwithgui = objwithgui
        self._entries = {}
        row = 0
        self._changed = set()
        for p in sorted(list(self.objwithgui.props), key=lambda p:self.objwithgui._get_priority(p.name)):
            if p.name in self.objwithgui._OWG_nogui_props:
                continue
            if self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.Bool:
                self._entries[p.name] = Gtk.CheckButton(label=p.blurb)
                self._entries[p.name].set_alignment(0, 0.5)
                self._entries[p.name].set_active(self.objwithgui.get_property(p.name))
                self._entries[p.name].connect('toggled', lambda cb: self.emit('changed', p.name))
                self.attach(self._entries[p.name], 0, 2, row, row + 1)
            else:
                l = Gtk.Label(label=p.blurb + ':')
                l.set_alignment(0, 0.5)
                self.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
                if self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.String:
                    self._entries[p.name] = Gtk.Entry()
                    self._entries[p.name].set_text(self.objwithgui.get_property(p.name))
                    self._entries[p.name].connect('changed', lambda ent: self.emit('changed', p.name))
                elif self.objwithgui._OWG_entrytypes[p.name] in (OWG_Param_Type.Integer, OWG_Param_Type.Float):
                    self._entries[p.name] = Gtk.SpinButton(adjustment=Gtk.Adjustment(self.objwithgui.get_property(p.name), p.minimum, p.maximum))
                    self._entries[p.name].set_width_chars(20)
                    if self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.Integer:
                        self._entries[p.name].set_digits(0)
                    else:
                        self._entries[p.name].set_digits(self.objwithgui._get_OWG_hint(p.name, OWG_Hint_Type.Digits))
                    self._entries[p.name].connect('value-changed', lambda sb: self.emit('changed', p.name))
                elif self.objwithgui._OWG_entrytypes[p.name] in (OWG_Param_Type.File, OWG_Param_Type.Folder):
                    if self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.File:
                        self._entries[p.name] = FileEntryWithButton(dialogtitle='Select file', dialogaction=Gtk.FileChooserAction.OPEN)
                    elif self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.Folder:
                        self._entries[p.name] = FileEntryWithButton(dialogtitle='Select folder', dialogaction=Gtk.FileChooserAction.SELECT_FOLDER)
                    else:
                        raise NotImplementedError
                    self._entries[p.name].connect('changed', lambda ent: self.emit('changed', p.name))
                    self._entries[p.name].set_filename(self.objwithgui.get_property(p.name))
                else:
                    self._entries[p.name] = Gtk.Entry()
                    self._entries[p.name].set_text(self.objwithgui.get_property(p.name))
                    self._entries[p.name].connect('changed', lambda ent: self.emit('changed', p.name))
                    logger.warning('ToDo: the type of this entry (%s) is not yet supported, using simple Gtk.Entry()' % self.objwithgui._OWG_entrytypes[p.name])
                self.attach(self._entries[p.name], 1, 2, row, row + 1)
            row += 1
        self.objwithgui.connect('notify', self._objwithgui_notify)
    def _objwithgui_notify(self, owg, prop):
        if prop.name in self._entries:
            self.revert_changes(keep_changed=True)
    def do_changed(self, propname):
        self._changed.add(propname)
    def revert_changes(self, keep_changed=False):
        for pname in self._entries:
            if keep_changed and (pname in self._changed):
                continue
            if isinstance(self._entries[pname], Gtk.CheckButton):
                self._entries[pname].set_active(self.objwithgui.get_property(pname))
            elif isinstance(self._entries[pname], Gtk.SpinButton):
                self._entries[pname].set_value(self.objwithgui.get_property(pname))
            elif isinstance(self._entries[pname], Gtk.Entry):
                self._entries[pname].set_text(self.objwithgui.get_property(pname))
            elif isinstance(self._entries[pname], FileEntryWithButton):
                self._entries[pname].set_filename(self.objwithgui.get_property(pname))
            else:
                raise NotImplementedError
        self._changed = set()
        self.emit('revert')
    def apply_changes(self):
        for pname in self._entries:
            if isinstance(self._entries[pname], Gtk.CheckButton):
                value = self._entries[pname].get_active()
            elif isinstance(self._entries[pname], Gtk.SpinButton):
                value = self._entries[pname].get_value()
            elif isinstance(self._entries[pname], Gtk.Entry):
                value = self._entries[pname].get_text()
            elif isinstance(self._entries[pname], FileEntryWithButton):
                value = self._entries[pname].get_filename()
            else:
                raise NotImplementedError
            if self.objwithgui.get_property(pname) != value:
                self.objwithgui.set_property(pname, value)
        self._changed = set()
        self.emit('apply')
            
class ObjWithGUI(GObject.GObject):
    _OWG_nogui_props = []
    _OWG_nosave_props = []
    _OWG_entrytypes = {}
    _OWG_hints = {'__default__':{OWG_Hint_Type.Digits:4}}
    def __init__(self):
        GObject.GObject.__init__(self)
        self._OWG_entrytypes = self._OWG_entrytypes.copy()
        self._OWG_nogui_props = self._OWG_nogui_props[:]
        self._OWG_nosave_props = self._OWG_nosave_props[:]
        self._update_entrytypes()
    def _update_entrytypes(self):
        for p in self.props:
            if p.name not in self._OWG_entrytypes:
                if p.value_type.name == 'gboolean':
                    self._OWG_entrytypes[p.name] = OWG_Param_Type.Bool
                elif p.value_type.name in ['gint', 'guint', 'glong', 'gulong',
                                           'gshort', 'gushort', 'gint8', 'guint8',
                                           'gint16', 'guint16', 'gint32', 'guint32',
                                           'gint64', 'guint64']:
                    self._OWG_entrytypes[p.name] = OWG_Param_Type.Integer
                elif p.value_type.name in ['gfloat', 'gdouble']:
                    self._OWG_entrytypes[p.name] = OWG_Param_Type.Float
                else:
                    self._OWG_entrytypes[p.name] = OWG_Param_Type.String
    def _get_priority(self, propname):
        try:
            return self._OWG_hints[propname][OWG_Hint_Type.OrderPriority]
        except KeyError:
            return 0
    def _get_OWG_hint(self, propname, hintname):
        if propname in self._OWG_hints and hintname in self._OWG_hints[propname]:
            val = self._OWG_hints[propname][hintname]
        elif '__default__' in self._OWG_hints and hintname in self._OWG_hints['__default__']:
            val = self._OWG_hints['__default__'][hintname]
        else:
            val = None
        return val
    def create_setup_table(self, homogeneous=False):
        return ObjSetupTable(self, len([p for p in self.props if p.name not in self._OWG_nogui_props]), homogeneous=homogeneous)
    def create_setup_dialog(self, title=None, parent=None, flags=0):
        if title is None:
            title = 'Set up ' + self.__class__.__name__
        return ObjSetupDialog(self, title, parent, flags)
    def loadstate(self, configparser):
        if not configparser.has_section(self._get_classname()):
            return
        for p in self.props:
            if p.name in self._OWG_nosave_props:
                continue
            if not configparser.has_option(self._get_classname(), p.name):
                continue
            if p.value_type.name == 'gboolean':
                val = configparser.getboolean(self._get_classname(), p.name)
            elif p.value_type.name in ['gint', 'guint', 'glong', 'gulong',
                                       'gshort', 'gushort', 'gint8', 'guint8',
                                       'gint16', 'guint16', 'gint32', 'guint32',
                                       'gint64', 'guint64']:
                val = configparser.getint(self._get_classname(), p.name)
            elif p.value_type.name in ['gfloat', 'gdouble']:
                val = configparser.getfloat(self._get_classname(), p.name)
            else:
                val = configparser.get(self._get_classname(), p.name)
            if self.get_property(p.name) != val:
                self.set_property(p.name, val)
    def savestate(self, configparser):
        if configparser.has_section(self._get_classname()):
            configparser.remove_section(self._get_classname())
        configparser.add_section(self._get_classname())
        for p in self.props:
            if p.name in self._OWG_nosave_props:
                continue
            configparser.set(self._get_classname(), p.name, self.get_property(p.name))
        
