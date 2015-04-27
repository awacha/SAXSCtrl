from gi.repository import GObject
from gi.repository import Gtk
from sasgui.fileentry import FileEntryWithButton
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class OWG_Param_Type(object):
    Integer = 'int'
    Float = 'float'
    Bool = 'bool'
    String = 'string'
    Folder = 'folder'
    File = 'file'
    ListOfStrings = 'listofstrings'


class OWG_Hint_Type(object):
    Digits = 'digits'
    OrderPriority = 'orderpriority'
    Editable = 'editable'
    ChoicesList = 'choiceslist'


class ObjSetupDialog(Gtk.Dialog):
    __gsignals__ = {'response': 'override',
                    'destroy': 'override',
                    }

    def __init__(self, objwithgui, title, parent=None, flags=0):
        Gtk.Dialog.__init__(
            self, title, parent, flags, buttons=(
                Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_APPLY,
                Gtk.ResponseType.APPLY, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_REFRESH, Gtk.ResponseType.REJECT))
        self._tab = objwithgui.create_setup_table()
        vb = self.get_content_area()
        vb.pack_start(self._tab, True, True, 0)
        self.set_response_sensitive(Gtk.ResponseType.APPLY, False)
        self._tabconn = [
            self._tab.connect(
                'changed', lambda t, parname:self.set_response_sensitive(Gtk.ResponseType.APPLY, True)),
            self._tab.connect(
                'apply', lambda t:self.set_response_sensitive(Gtk.ResponseType.APPLY, False)),
            self._tab.connect(
                'revert', lambda t:self.set_response_sensitive(Gtk.ResponseType.APPLY, False)),
        ]
        vb.show_all()

    def do_response(self, respid):
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            self._tab.apply_changes()
        if respid in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.REJECT):
            if respid == Gtk.ResponseType.DELETE_EVENT:
                logger.debug('Delete-event in ObjSetupDialog for %s' %
                             self._tab.objwithgui._get_classname())
            self._tab.revert_changes()
        if respid in (Gtk.ResponseType.APPLY, Gtk.ResponseType.REJECT):
            self.stop_emission('response')

    def do_destroy(self):
        if not hasattr(self, '_tabconn'):
            return
        for c in self._tabconn:
            self._tab.disconnect(c)
        del self._tabconn


class ObjSetupTable(Gtk.Table):
    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'apply': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    'revert': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    'destroy': 'override',
                    }

    def __init__(self, objwithgui, rows=1, columns=1, homogeneous=False):
        Gtk.Table.__init__(self, rows, columns, homogeneous)
        self.objwithgui = objwithgui
        self._entries = {}
        row = 0
        self._changed = set()
        for p in sorted(list(self.objwithgui.props), key=lambda p: self.objwithgui._get_priority(p.name)):
            if p.name in self.objwithgui._OWG_nogui_props:
                continue
            if self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.Bool:
                self._entries[p.name] = Gtk.CheckButton(label=p.blurb)
                self._entries[p.name].set_halign(Gtk.Align.START)
                self._entries[p.name].set_valign(Gtk.Align.CENTER)
                self._entries[p.name].set_active(
                    self.objwithgui.get_property(p.name))
                self._entries[p.name]._connection = self._entries[p.name].connect(
                    'toggled', lambda cb, n: self.emit('changed', n), p.name)
                self.attach(self._entries[p.name], 0, 2, row, row + 1)
            else:
                l = Gtk.Label(label=p.blurb + ':')
                l.set_halign(Gtk.Align.START)
                l.set_valign(Gtk.Align.CENTER)
                self.attach(l, 0, 1, row, row + 1, Gtk.AttachOptions.FILL)
                if self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.String:
                    self._entries[p.name] = Gtk.Entry()
                    self._entries[p.name].set_text(
                        self.objwithgui.get_property(p.name))
                    self._entries[p.name]._connection = self._entries[p.name].connect(
                        'changed', lambda ent, n: self.emit('changed', n), p.name)
                elif self.objwithgui._OWG_entrytypes[p.name] in (OWG_Param_Type.Integer, OWG_Param_Type.Float):
                    self._entries[p.name] = Gtk.SpinButton(adjustment=Gtk.Adjustment(
                        self.objwithgui.get_property(p.name), p.minimum, p.maximum))
                    self._entries[p.name].set_value(
                        self.objwithgui.get_property(p.name))
                    self._entries[p.name].set_width_chars(20)
                    if self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.Integer:
                        self._entries[p.name].set_digits(0)
                    else:
                        self._entries[p.name].set_digits(
                            self.objwithgui._get_OWG_hint(p.name, OWG_Hint_Type.Digits))
                    self._entries[p.name]._connection = self._entries[p.name].connect(
                        'value-changed', lambda sb, n: self.emit('changed', n), p.name)
                elif self.objwithgui._OWG_entrytypes[p.name] in (OWG_Param_Type.File, OWG_Param_Type.Folder):
                    if self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.File:
                        self._entries[p.name] = FileEntryWithButton(
                            dialogtitle='Select file', dialogaction=Gtk.FileChooserAction.OPEN)
                    elif self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.Folder:
                        self._entries[p.name] = FileEntryWithButton(
                            dialogtitle='Select folder', dialogaction=Gtk.FileChooserAction.SELECT_FOLDER)
                    else:
                        raise NotImplementedError
                    self._entries[p.name]._connection = self._entries[p.name].connect(
                        'changed', lambda ent, n: self.emit('changed', n), p.name)
                    self._entries[p.name].set_filename(
                        self.objwithgui.get_property(p.name))
                elif self.objwithgui._OWG_entrytypes[p.name] == OWG_Param_Type.ListOfStrings:
                    if self.objwithgui._get_OWG_hint(p.name, OWG_Hint_Type.Editable):
                        self._entries[
                            p.name] = Gtk.ComboBoxText.new_with_entry()
                    else:
                        self._entries[p.name] = Gtk.ComboBoxText.new()
                    choiceslist = self.objwithgui._get_OWG_hint(
                        p.name, OWG_Hint_Type.ChoicesList)
                    currval = self.objwithgui.get_property(p.name)
                    if currval not in choiceslist:
                        choiceslist.insert(0, currval)
                    for i, ch in enumerate(choiceslist):
                        self._entries[p.name].append_text(ch)
                        if ch == currval:
                            self._entries[p.name].set_active(i)
                    self._entries[p.name]._connection = self._entries[p.name].connect(
                        'changed', lambda ent, n: self.emit('changed', n), p.name)
                else:
                    self._entries[p.name] = Gtk.Entry()
                    self._entries[p.name].set_text(
                        unicode(self.objwithgui.get_property(p.name)))
                    self._entries[p.name]._connection = self._entries[p.name].connect(
                        'changed', lambda ent, n: self.emit('changed', n), p.name)
                    logger.warning('ToDo: the type of this entry (%s) is not yet supported, using simple Gtk.Entry()' %
                                   self.objwithgui._OWG_entrytypes[p.name])
                logger.debug('Initialized entry for property %s: %d' %
                             (p.name, id(self._entries[p.name])))
                self.attach(self._entries[p.name], 1, 2, row, row + 1)
            row += 1
        if self.objwithgui._OWG_parts:
            tab = Gtk.Table()
            self.attach(tab, 0, 2, row, row + 1)
            row += 1
        self._partbuttons = []
        for i, owgp in enumerate(self.objwithgui._OWG_parts):
            b = Gtk.Button(label=owgp._get_classname())
            tab.attach(
                b, i % self.objwithgui._OWG_parttab_cols, i % self.objwithgui._OWG_parttab_cols +
                1,
                i / self.objwithgui._OWG_parttab_cols, i / self.objwithgui._OWG_parttab_cols + 1)
            b._connection = b.connect(
                'clicked', lambda b, part: self._create_owgpart_setupdialog(part), owgp)
            self._partbuttons.append(b)

        self._owgconn = self.objwithgui.connect(
            'notify', self._objwithgui_notify)

    def do_destroy(self):
        logger.debug('Disconnecting')
        if not hasattr(self, '_entries'):
            logger.debug('No need to disconnect.')
            return
        for e in self._entries.values() + self._partbuttons:
            if hasattr(e, '_connection'):
                e.disconnect(e._connection)
                del e._connection
        del self._entries
        del self._partbuttons
        if hasattr(self, '_owgconn'):
            self.objwithgui.disconnect(self._owgconn)
            del self._owgconn
        logger.debug('Disconnecting done.')

    def _create_owgpart_setupdialog(self, owgp):
        dia = owgp.create_setup_dialog(
            parent=self.get_toplevel(), flags=Gtk.DialogFlags.DESTROY_WITH_PARENT)
        while True:
            result = dia.run()
            if result in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
                self.emit('changed', owgp._get_classname())
            if result in (Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
                break
        logger.debug('Destroying dialog!')
        dia.hide()
        dia.destroy()
        del dia

    def _objwithgui_notify(self, owg, prop):
        if prop.name in self._entries:
            logger.debug('ObjWithGUI notify: ' + prop.name)
            self.revert_changes(keep_changed=False)

    def do_changed(self, propname):
        logger.debug('OWG_Table. Changed: ' + propname)
        self._changed.add(propname)

    def revert_changes(self, keep_changed=False):
        logger.debug('OWG-revert-changes(' + str(keep_changed) + ')')
        for pname in self._entries:
            if keep_changed and (pname in self._changed):
                continue
            if isinstance(self._entries[pname], Gtk.CheckButton):
                self._entries[pname].set_active(
                    self.objwithgui.get_property(pname))
            elif isinstance(self._entries[pname], Gtk.SpinButton):
                self._entries[pname].set_value(
                    self.objwithgui.get_property(pname))
            elif isinstance(self._entries[pname], Gtk.Entry):
                self._entries[pname].set_text(
                    self.objwithgui.get_property(pname))
            elif isinstance(self._entries[pname], FileEntryWithButton):
                self._entries[pname].set_filename(
                    self.objwithgui.get_property(pname))
            elif isinstance(self._entries[pname], Gtk.ComboBoxText):
                currval = self.objwithgui.get_property(pname)
                logger.debug('Entry ID: %d' % id(self._entries[pname]))
                for i, ch in enumerate([x[0] for x in self._entries[pname].get_model()]):
                    if ch == currval:
                        self._entries[pname].set_active(i)
                        break
                if ch != currval:
                    self._entries[pname].append_text(currval)
                    self._entries[pname].set_active(i + 1)
            else:
                raise NotImplementedError
            logger.debug('Reverted changes in entry ' + pname)
        self._changed = set()
        self.emit('revert')

    def apply_changes(self):
        logger.debug('OWG-apply-changes')
        with self.objwithgui.freeze_notify():
            for pname in self._entries:
                if isinstance(self._entries[pname], Gtk.CheckButton):
                    value = self._entries[pname].get_active()
                elif isinstance(self._entries[pname], Gtk.SpinButton):
                    value = self._entries[pname].get_value()
                elif isinstance(self._entries[pname], Gtk.Entry):
                    value = self._entries[pname].get_text()
                elif isinstance(self._entries[pname], FileEntryWithButton):
                    value = self._entries[pname].get_filename()
                elif isinstance(self._entries[pname], Gtk.ComboBoxText):
                    value = self._entries[pname].get_active_text()
                else:
                    raise NotImplementedError
                if self.objwithgui.get_property(pname) != value:
                    self.objwithgui.set_property(pname, value)
        self._changed = set()
        self.emit('apply')


class ObjWithGUI(GObject.GObject):
    # a list of the names of properties which should not be represented in the
    # GUI.
    _OWG_nogui_props = None
    # a list of the names of properties of which the values should not be
    # saved or loaded.
    _OWG_nosave_props = None
    # a dict. Keys: property names. Values: entry types of OWG_Param_Type
    _OWG_entrytypes = None
    # a list of parts (attributes to ObjWithGUI) which are also instances of
    # ObjWithGUI.
    _OWG_parts = None
    # In the GUI table these will be represented as buttons which open the appropriate GUI
    # dialog for the part. Changes in these dialogs are not forwarded per se to the parent dialog of
    # the parent ObjWithGUI.
    # a dict of various hints assisting the correct display of entries
    _OWG_hints = None
    # the number of columns in the table for parts in the GUI.
    _OWG_parttab_cols = 5

    def __init__(self):
        GObject.GObject.__init__(self)
        self._OWG_init_lists()
        self._update_entrytypes()

    def _OWG_init_lists(self):
        if self._OWG_nogui_props is None:
            self._OWG_nogui_props = []
        if self._OWG_nosave_props is None:
            self._OWG_nosave_props = []
        if self._OWG_entrytypes is None:
            self._OWG_entrytypes = {}
        if self._OWG_parts is None:
            self._OWG_parts = []
        if self._OWG_hints is None:
            self._OWG_hints = {}
        dic = {'__default__': {OWG_Hint_Type.Digits: 4,
                               OWG_Hint_Type.Editable: False, OWG_Hint_Type.ChoicesList: []}}
        dic.update(self._OWG_hints)
        self._OWG_hints = dic

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

    def loadstate(self, configparser, sectionprefix=''):
        if not configparser.has_section(sectionprefix + self._get_classname()):
            return
        for p in self.props:
            if p.name in self._OWG_nosave_props:
                continue
            if not configparser.has_option(sectionprefix + self._get_classname(), p.name):
                continue
            if p.value_type.name == 'gboolean':
                val = configparser.getboolean(
                    sectionprefix + self._get_classname(), p.name)
            elif p.value_type.name in ['gint', 'guint', 'glong', 'gulong',
                                       'gshort', 'gushort', 'gint8', 'guint8',
                                       'gint16', 'guint16', 'gint32', 'guint32',
                                       'gint64', 'guint64']:
                val = configparser.getint(
                    sectionprefix + self._get_classname(), p.name)
            elif p.value_type.name in ['gfloat', 'gdouble']:
                val = configparser.getfloat(
                    sectionprefix + self._get_classname(), p.name)
            else:
                val = configparser.get(
                    sectionprefix + self._get_classname(), p.name).decode('utf-8')
            if self.get_property(p.name) != val:
                self.set_property(p.name, val)
        for owgp in self._OWG_parts:
            logger.debug('Loading state of OWG part: ' + owgp._get_classname())
            owgp.loadstate(configparser, self._get_classname() + '::')

    def savestate(self, configparser, sectionprefix=''):
        if configparser.has_section(sectionprefix + self._get_classname()):
            configparser.remove_section(sectionprefix + self._get_classname())
        configparser.add_section(sectionprefix + self._get_classname())
        for p in self.props:
            if p.name in self._OWG_nosave_props:
                continue
            value = self.get_property(p.name)
            if isinstance(value, str):
                value = value.decode('utf-8')
            configparser.set(
                sectionprefix + self._get_classname(), p.name, unicode(value).encode('utf-8'))
        for owgp in self._OWG_parts:
            logger.debug('Saving state of OWG part: ' + owgp._get_classname())
            owgp.savestate(configparser, self._get_classname() + '::')

    def _get_classname(self):
        return self.__class__.__name__
