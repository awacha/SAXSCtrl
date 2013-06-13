import weakref
from gi.repository import GObject

class SubSystemError(StandardError):
    pass

class SubSystemException(Exception):
    pass

class SubSystem(GObject.GObject):
    configfile = GObject.property(type=str, default='')
    def __init__(self, credo):
        GObject.GObject.__init__(self)
        self.credo = weakref.ref(credo)
    def _get_classname(self):
        return self.__class__.__name__.replace('SubSystem', '')
    def loadstate(self, configparser):
        if not configparser.has_section(self._get_classname()):
            return
        for p in self.props:
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
            configparser.set(self._get_classname(), p.name, self.get_property(p.name))
    def destroy(self):
        pass
